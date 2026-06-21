"""
Webhook Server for Chess Agent Integration.

This module provides an HTTP API for agents that don't support MCP or ACP.
Agents can register webhook endpoints to receive move requests and game
notifications.

The server provides endpoints for:
- Receiving moves from agents
- Notifying agents of game start/completion
- Querying agent state
- Managing agent memories and skills
"""

import asyncio
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import chess
import chess.pgn
import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..registry import get_registry, AgentConfig, AgentState
from ..memory import get_memory_manager, MemoryEntry
from ..skills import AgentSkill, SkillManager, get_skill_extractor
from ..agent_player import AgentPlayer


# ============================================================================
# Data Models
# ============================================================================

class MoveRequest(BaseModel):
    """Request to make a move."""
    agent_id: str
    game_id: str
    game_state: dict
    move: Optional[str] = None  # Agent can provide move directly
    

class MoveResponse(BaseModel):
    """Response with a move."""
    status: str  # "accepted", "rejected", "error"
    move: Optional[str] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    error: Optional[str] = None
    game_state: Optional[dict] = None


class GameStartRequest(BaseModel):
    """Request to notify agent of game start."""
    agent_id: str
    game_id: str
    color: str  # "white" or "black"
    opponent: str
    initial_fen: str = chess.STARTING_FEN


class GameCompleteRequest(BaseModel):
    """Request to notify agent of game completion."""
    agent_id: str
    game_id: str
    pgn: str
    result: str  # "1-0", "0-1", "1/2-1/2"
    opponent: str


class AgentStateResponse(BaseModel):
    """Response with agent state."""
    agent_id: str
    status: str
    current_game: Optional[str] = None
    last_activity: Optional[str] = None
    error_message: Optional[str] = None
    connection_count: int = 0


class MemoryRequest(BaseModel):
    """Request to save a memory."""
    agent_id: str
    board_state: str
    move: str
    reasoning: str = ""
    game_id: str = ""
    move_number: int = 0
    color: str = ""
    confidence: float = 0.0
    outcome: str = "unknown"
    lessons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class SkillRequest(BaseModel):
    """Request to save a skill."""
    agent_id: str
    name: str
    skill_type: str
    description: str = ""
    data: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


# ============================================================================
# Webhook Server
# ============================================================================

class WebhookServer:
    """
    HTTP server for webhook-based agent integration.
    
    This server provides REST endpoints for agents to:
    - Receive move requests
    - Send move responses
    - Receive game notifications
    - Query and manage memories and skills
    
    Usage:
        # Start the server
        server = WebhookServer(port=8082)
        server.start()
        
        # Or run from command line
        # python -m chess_llm.agents.protocols.webhook_server --port 8082
    """
    
    def __init__(
        self,
        port: int = 8082,
        host: str = "0.0.0.0",
        api_key: Optional[str] = None,
        debug: bool = False
    ):
        """
        Initialize the webhook server.
        
        Args:
            port: Port to listen on
            host: Host to bind to
            api_key: Optional API key for authentication
            debug: Enable debug logging
        """
        self.port = port
        self.host = host
        self.api_key = api_key
        self.debug = debug
        self._app = None
        self._server = None
        self._running = False
        self._thread = None
        
        # Initialize components
        self._registry = get_registry()
        self._memory_manager = get_memory_manager()
        
        # Pending move requests (for async responses)
        self._pending_requests: dict[str, asyncio.Event] = {}
        self._pending_responses: dict[str, dict] = {}
        self._lock = asyncio.Lock()
    
    def start(self):
        """Start the webhook server."""
        if self._running:
            return
        
        # Create FastAPI app
        self._app = FastAPI(
            title="Chess LLM Webhook Server",
            version="1.0.0",
            description="Webhook server for chess agent integration"
        )
        
        # Register endpoints
        self._register_endpoints()
        
        # Start server
        import uvicorn
        self._server = uvicorn.Server(
            config=uvicorn.Config(
                app=self._app,
                host=self.host,
                port=self.port,
                log_level="debug" if self.debug else "info"
            )
        )
        
        # Run in a thread
        self._thread = threading.Thread(target=self._server.run)
        self._thread.daemon = True
        self._thread.start()
        
        # Give it a moment to start
        import time
        time.sleep(0.5)
        
        self._running = True
    
    def stop(self):
        """Stop the webhook server."""
        if not self._running:
            return
        
        if self._server:
            self._server.shutdown()
        
        self._running = False
    
    def _register_endpoints(self):
        """Register all HTTP endpoints."""
        # Health check
        @self._app.get("/health")
        async def health_check():
            return {"status": "ok", "server": "chess-llm-webhook"}
        
        # Capabilities
        @self._app.get("/capabilities")
        async def get_capabilities():
            return {
                "name": "chess-llm-webhook",
                "version": "1.0.0",
                "endpoints": [
                    {"method": "POST", "path": "/chess/move", "description": "Submit a move"},
                    {"method": "POST", "path": "/chess/game-start", "description": "Game started notification"},
                    {"method": "POST", "path": "/chess/game-complete", "description": "Game completed notification"},
                    {"method": "GET", "path": "/chess/agent-state/{agent_id}", "description": "Get agent state"},
                    {"method": "GET", "path": "/chess/agent-memory/{agent_id}", "description": "Get agent memories"},
                    {"method": "POST", "path": "/chess/agent-memory/{agent_id}", "description": "Save agent memory"},
                    {"method": "GET", "path": "/chess/agent-skills/{agent_id}", "description": "Get agent skills"},
                    {"method": "POST", "path": "/chess/agent-skills/{agent_id}", "description": "Save agent skill"},
                    {"method": "POST", "path": "/chess/register", "description": "Register an agent"},
                    {"method": "GET", "path": "/chess/leaderboard", "description": "Get leaderboard"}
                ]
            }
        
        # Move endpoint
        @self._app.post("/chess/move", response_model=MoveResponse)
        async def receive_move(request: MoveRequest, background_tasks: BackgroundTasks):
            """Receive a move from an agent."""
            # Verify API key if configured
            if self.api_key:
                api_key = request.headers.get("X-API-Key")
                if api_key != self.api_key:
                    raise HTTPException(status_code=401, detail="Invalid API key")
            
            # Process the move
            try:
                # If agent provided a move, validate it
                if request.move:
                    board = chess.Board(request.game_state["fen"])
                    try:
                        move_obj = board.parse_uci(request.move)
                        if move_obj not in board.legal_moves:
                            return MoveResponse(
                                status="rejected",
                                error=f"Illegal move: {request.move}",
                                game_state=request.game_state
                            )
                    except ValueError as e:
                        return MoveResponse(
                            status="rejected",
                            error=f"Invalid move: {e}",
                            game_state=request.game_state
                        )
                    
                    # Move is valid
                    return MoveResponse(
                        status="accepted",
                        move=request.move,
                        reasoning="Move accepted",
                        confidence=1.0,
                        game_state=request.game_state
                    )
                else:
                    # Agent needs to generate a move
                    # Store the request and wait for async response
                    request_id = str(uuid.uuid4())
                    
                    async with self._lock:
                        self._pending_requests[request_id] = asyncio.Event()
                        self._pending_responses[request_id] = None
                    
                    # Return request ID, agent should use this to respond
                    return MoveResponse(
                        status="pending",
                        game_state={
                            **request.game_state,
                            "request_id": request_id
                        }
                    )
                    
            except Exception as e:
                return MoveResponse(
                    status="error",
                    error=str(e),
                    game_state=request.game_state
                )
        
        # Async move response endpoint
        @self._app.post("/chess/move/{request_id}/response")
        async def receive_move_response(request_id: str, response: MoveResponse):
            """Receive an async move response from an agent."""
            async with self._lock:
                if request_id in self._pending_requests:
                    self._pending_responses[request_id] = response.dict()
                    self._pending_requests[request_id].set()
            
            return {"status": "received"}
        
        # Game start notification
        @self._app.post("/chess/game-start")
        async def game_start_notification(request: GameStartRequest):
            """Notify agent of game start."""
            # Update agent state
            self._registry.update_state(
                request.agent_id,
                status="playing",
                current_game=request.game_id
            )
            
            # Try to notify the agent via its endpoint
            agent = self._registry.get_agent(request.agent_id)
            if agent and agent.endpoint:
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.post(
                            f"{agent.endpoint}/chess/game-start",
                            json=request.dict()
                        )
                except Exception as e:
                    print(f"Failed to notify agent {request.agent_id}: {e}")
            
            return {"status": "notified"}
        
        # Game complete notification
        @self._app.post("/chess/game-complete")
        async def game_complete_notification(request: GameCompleteRequest, background_tasks: BackgroundTasks):
            """Notify agent of game completion."""
            # Update agent state
            self._registry.update_state(
                request.agent_id,
                status="idle",
                current_game=None
            )
            
            # Save game result to memory
            background_tasks.add_task(
                self._save_game_to_memory,
                request.agent_id,
                request.pgn,
                request.result,
                request.opponent
            )
            
            # Try to notify the agent via its endpoint
            agent = self._registry.get_agent(request.agent_id)
            if agent and agent.endpoint:
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.post(
                            f"{agent.endpoint}/chess/game-complete",
                            json=request.dict()
                        )
                except Exception as e:
                    print(f"Failed to notify agent {request.agent_id}: {e}")
            
            return {"status": "notified"}
        
        # Agent state endpoint
        @self._app.get("/chess/agent-state/{agent_id}", response_model=AgentStateResponse)
        async def get_agent_state(agent_id: str):
            """Get the state of an agent."""
            config = self._registry.get_agent(agent_id)
            if not config:
                raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
            
            state = self._registry.get_state(agent_id)
            if not state:
                raise HTTPException(status_code=404, detail=f"State for agent {agent_id} not found")
            
            return AgentStateResponse(
                agent_id=agent_id,
                status=state.status,
                current_game=state.current_game,
                last_activity=state.last_activity,
                error_message=state.error_message,
                connection_count=state.connection_count
            )
        
        # Agent memory endpoints
        @self._app.get("/chess/agent-memory/{agent_id}")
        async def get_agent_memory(agent_id: str, limit: int = 10, game_id: Optional[str] = None):
            """Get memories for an agent."""
            memories = self._memory_manager.query(
                agent_id=agent_id,
                game_id=game_id,
                limit=limit
            )
            
            return {
                "agent_id": agent_id,
                "memories": [m.to_dict() for m in memories]
            }
        
        @self._app.post("/chess/agent-memory/{agent_id}")
        async def save_agent_memory(agent_id: str, request: MemoryRequest):
            """Save a memory for an agent."""
            memory_id = self._memory_manager.save(
                agent_id=agent_id,
                board_state=request.board_state,
                move=request.move,
                reasoning=request.reasoning,
                game_id=request.game_id,
                move_number=request.move_number,
                color=request.color,
                confidence=request.confidence,
                outcome=request.outcome,
                lessons=request.lessons,
                tags=request.tags
            )
            
            return {
                "status": "success",
                "memory_id": memory_id
            }
        
        # Agent skills endpoints
        @self._app.get("/chess/agent-skills/{agent_id}")
        async def get_agent_skills(agent_id: str, skill_type: Optional[str] = None):
            """Get skills for an agent."""
            skill_manager = SkillManager(agent_id)
            skills = skill_manager.list_skills(skill_type=skill_type)
            
            return {
                "agent_id": agent_id,
                "skills": [s.to_dict() for s in skills]
            }
        
        @self._app.post("/chess/agent-skills/{agent_id}")
        async def save_agent_skill(agent_id: str, request: SkillRequest):
            """Save a skill for an agent."""
            skill_manager = SkillManager(agent_id)
            
            skill = AgentSkill(
                agent_id=agent_id,
                name=request.name,
                skill_type=request.skill_type,
                description=request.description,
                data=request.data,
                tags=request.tags
            )
            
            skill_id = skill_manager.save(skill)
            
            return {
                "status": "success",
                "skill_id": skill_id
            }
        
        # Agent registration
        @self._app.post("/chess/register")
        async def register_agent(request: AgentConfig):
            """Register a new agent."""
            try:
                config = self._registry.register_agent(
                    agent_id=request.agent_id,
                    name=request.name,
                    agent_type=request.agent_type,
                    model=request.model,
                    endpoint=request.endpoint,
                    api_key=request.api_key,
                    timeout=request.timeout,
                    max_retries=request.max_retries,
                    description=request.description
                )
                
                return {
                    "status": "success",
                    "agent": config.to_dict()
                }
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        # Leaderboard
        @self._app.get("/chess/leaderboard")
        async def get_leaderboard(limit: int = 20):
            """Get the ELO leaderboard."""
            try:
                from chess_llm.elo import EloTracker
                tracker = EloTracker("ratings.json")
                leaderboard = tracker.leaderboard()
                
                return {
                    "leaderboard": leaderboard[:limit]
                }
            except Exception as e:
                # Fallback
                agents = self._registry.list_agents()
                leaderboard = []
                
                for agent in agents:
                    state = self._registry.get_state(agent.agent_id)
                    leaderboard.append({
                        "agent_id": agent.agent_id,
                        "name": agent.name,
                        "agent_type": agent.agent_type,
                        "status": state.status if state else "unknown",
                        "rating": 1200
                    })
                
                return {
                    "leaderboard": leaderboard[:limit],
                    "note": "ELO ratings not available"
                }
        
        # List all agents
        @self._app.get("/chess/agents")
        async def list_agents(agent_type: Optional[str] = None):
            """List all registered agents."""
            agents = self._registry.list_agents(agent_type=agent_type)
            
            return {
                "agents": [a.to_dict() for a in agents]
            }
    
    async def _save_game_to_memory(
        self,
        agent_id: str,
        pgn: str,
        result: str,
        opponent: str
    ):
        """Save a completed game to the agent's memory."""
        try:
            # Parse PGN to extract moves
            import io
            pgn_file = io.StringIO(pgn)
            game = chess.pgn.read_game(pgn_file)
            
            if not game:
                return
            
            board = game.board()
            node = game
            move_number = 0
            
            # Process each move
            while node.variations:
                move_number += 1
                next_node = node.variation[0]
                move = next_node.move
                board.push(move)
                
                # Determine if this is our move
                color = "white" if board.turn == chess.BLACK else "black"
                
                # For simplicity, assume we're the agent
                # In production, we'd need to track which moves are ours
                
                # Save memory for each move
                self._memory_manager.save(
                    agent_id=agent_id,
                    board_state=board.fen(),
                    move=move.uci(),
                    reasoning=f"Move {move_number}: {board.san(move)}",
                    game_id="",  # Would be set in actual game
                    move_number=move_number,
                    color=color,
                    confidence=0.5,
                    outcome=result,
                    tags=["game", f"move-{move_number}"]
                )
                
                node = node.variation[0]
            
        except Exception as e:
            print(f"Failed to save game to memory: {e}")


# ============================================================================
# Standalone Server Entry Point
# ============================================================================

import time


def main():
    """Main entry point for running the webhook server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chess LLM Webhook Server")
    parser.add_argument("--port", type=int, default=8082, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--api-key", type=str, default=None, help="Optional API key for authentication")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Create and start server
    server = WebhookServer(
        port=args.port,
        host=args.host,
        api_key=args.api_key,
        debug=args.debug
    )
    
    print(f"Starting Chess LLM Webhook Server on {args.host}:{args.port}")
    
    try:
        server.start()
        print(f"Server started. Press Ctrl+C to stop.")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Shutting down...")
        server.stop()
    except Exception as e:
        print(f"Error: {e}")
        server.stop()
        raise


if __name__ == "__main__":
    main()
