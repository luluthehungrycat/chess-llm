"""
MCP Server for Chess Agent Integration.

This module provides an MCP (Model Context Protocol) server that allows
external agent harnesses (Hermes, Claude Code, Vibe CLI, custom agents)
to interact with the chess-llm system.

The server exposes tools and resources for:
- Starting and managing chess games
- Making moves as an agent
- Querying game state
- Managing agent memories and skills
- Accessing leaderboards and statistics
"""

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import chess
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

# Try to import MCP library, fall back to simple implementation
try:
    from mcp.server import Server
    from mcp.types import TextContent, Tool, ImageContent, Resource
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from ..registry import get_registry, AgentConfig, AgentState
from ..memory import get_memory_manager, MemoryEntry
from ..skills import get_skill_extractor, AgentSkill, SkillManager
from ..agent_player import AgentPlayer


@dataclass
class GameState:
    """State of a chess game."""
    game_id: str
    white_agent: str
    black_agent: str
    fen: str
    move_history: list[str]
    result: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "in_progress"  # "in_progress", "completed", "abandoned"
    
    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "white_agent": self.white_agent,
            "black_agent": self.black_agent,
            "fen": self.fen,
            "move_history": self.move_history,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status
        }


class GameManager:
    """Manages active chess games."""
    
    def __init__(self):
        self._games: dict[str, GameState] = {}
        self._lock = asyncio.Lock()
    
    async def create_game(
        self,
        white_agent: str,
        black_agent: str,
        initial_fen: str = chess.STARTING_FEN
    ) -> str:
        """Create a new chess game."""
        async with self._lock:
            game_id = str(uuid.uuid4())
            game = GameState(
                game_id=game_id,
                white_agent=white_agent,
                black_agent=black_agent,
                fen=initial_fen,
                move_history=[]
            )
            self._games[game_id] = game
            return game_id
    
    async def get_game(self, game_id: str) -> Optional[GameState]:
        """Get a game by ID."""
        async with self._lock:
            return self._games.get(game_id)
    
    async def update_game(
        self,
        game_id: str,
        fen: Optional[str] = None,
        move_history: Optional[list[str]] = None,
        result: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[GameState]:
        """Update a game."""
        async with self._lock:
            game = self._games.get(game_id)
            if not game:
                return None
            
            if fen is not None:
                game.fen = fen
            if move_history is not None:
                game.move_history = move_history
            if result is not None:
                game.result = result
            if status is not None:
                game.status = status
            
            game.updated_at = datetime.now().isoformat()
            return game
    
    async def make_move(
        self,
        game_id: str,
        agent_id: str,
        move: str
    ) -> dict:
        """Make a move in a game."""
        async with self._lock:
            game = self._games.get(game_id)
            if not game:
                raise ValueError(f"Game {game_id} not found")
            
            # Verify it's this agent's turn
            board = chess.Board(game.fen)
            if board.turn == chess.WHITE:
                expected_agent = game.white_agent
            else:
                expected_agent = game.black_agent
            
            if agent_id != expected_agent:
                raise ValueError(f"It's not {agent_id}'s turn")
            
            # Validate move
            try:
                move_obj = board.parse_uci(move)
                if move_obj not in board.legal_moves:
                    raise ValueError(f"Illegal move: {move}")
                
                board.push(move_obj)
                game.fen = board.fen()
                game.move_history.append(move)
                game.updated_at = datetime.now().isoformat()
                
                # Check for game end
                if board.is_checkmate():
                    if board.turn == chess.WHITE:
                        game.result = "0-1"
                    else:
                        game.result = "1-0"
                    game.status = "completed"
                elif board.is_stalemate() or board.is_insufficient_material():
                    game.result = "1/2-1/2"
                    game.status = "completed"
                elif board.is_seventyfive_moves() or board.is_fivefold_repetition():
                    game.result = "1/2-1/2"
                    game.status = "completed"
                
                return {
                    "status": "success",
                    "game_id": game_id,
                    "move": move,
                    "fen": game.fen,
                    "game_status": game.status,
                    "result": game.result
                }
                
            except ValueError as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "game_id": game_id
                }
    
    async def list_games(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> list[dict]:
        """List games with optional filters."""
        async with self._lock:
            games = list(self._games.values())
            
            if agent_id:
                games = [
                    g for g in games 
                    if g.white_agent == agent_id or g.black_agent == agent_id
                ]
            
            if status:
                games = [g for g in games if g.status == status]
            
            return [g.to_dict() for g in games]
    
    async def delete_game(self, game_id: str) -> bool:
        """Delete a game."""
        async with self._lock:
            if game_id in self._games:
                del self._games[game_id]
                return True
            return False


# Global game manager
_game_manager = GameManager()


def get_game_manager() -> GameManager:
    """Get the global game manager."""
    return _game_manager


class ChessMCPServer:
    """
    MCP Server for chess agent integration.
    
    Provides tools and resources for agents to:
    - Start and manage chess games
    - Make moves
    - Query game state
    - Access memories and skills
    - View leaderboards
    
    Usage:
        # Start the server
        server = ChessMCPServer(port=8081)
        server.start()
        
        # Or run from command line
        # python -m chess_llm.agents.protocols.mcp_server --port 8081
    """
    
    def __init__(
        self,
        port: int = 8081,
        host: str = "0.0.0.0",
        transport: str = "http",
        debug: bool = False
    ):
        """
        Initialize the MCP server.
        
        Args:
            port: Port to listen on
            host: Host to bind to
            transport: Transport type ("http", "stdio", "sse")
            debug: Enable debug logging
        """
        self.port = port
        self.host = host
        self.transport = transport
        self.debug = debug
        self._app = None
        self._server = None
        self._running = False
        
        # Initialize components
        self._registry = get_registry()
        self._memory_manager = get_memory_manager()
        self._game_manager = get_game_manager()
    
    def start(self):
        """Start the MCP server."""
        if self._running:
            return
        
        if self.transport == "http":
            self._start_http_server()
        elif self.transport == "stdio":
            self._start_stdio_server()
        elif self.transport == "sse":
            self._start_sse_server()
        else:
            raise ValueError(f"Unknown transport: {self.transport}")
        
        self._running = True
    
    def stop(self):
        """Stop the MCP server."""
        if not self._running:
            return
        
        if self._server:
            self._server.shutdown()
        
        self._running = False
    
    def _start_http_server(self):
        """Start HTTP-based MCP server."""
        self._app = FastAPI(
            title="Chess LLM MCP Server",
            version="1.0.0",
            description="MCP server for chess agent integration"
        )
        
        # Register endpoints
        self._register_http_endpoints()
        
        # Start FastAPI server
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
        import threading
        self._thread = threading.Thread(target=self._server.run)
        self._thread.daemon = True
        self._thread.start()
        
        # Give it a moment to start
        time.sleep(0.5)
    
    def _start_stdio_server(self):
        """Start stdio-based MCP server."""
        if MCP_AVAILABLE:
            app = Server("chess-llm-mcp")
            
            # Register tools
            self._register_mcp_tools(app)
            
            # Start server
            app.run()
        else:
            # Fallback: simple stdio server
            import sys
            print("MCP Server (stdio) - Chess LLM")
            print("Ready for connections...")
            
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    request = json.loads(line)
                    response = self._handle_stdio_request(request)
                    print(json.dumps(response))
                    sys.stdout.flush()
                except json.JSONDecodeError:
                    print(json.dumps({"error": "Invalid JSON"}))
                    sys.stdout.flush()
                except Exception as e:
                    print(json.dumps({"error": str(e)}))
                    sys.stdout.flush()
    
    def _start_sse_server(self):
        """Start SSE-based MCP server."""
        # Similar to HTTP but with SSE support
        self._start_http_server()
    
    def _register_http_endpoints(self):
        """Register HTTP endpoints for MCP."""
        # MCP endpoints
        @self._app.post("/mcp")
        async def handle_mcp_request(request: Request):
            """Handle MCP requests."""
            try:
                data = await request.json()
                response = await self._handle_mcp_request(data)
                return JSONResponse(content=response)
            except Exception as e:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(e)}
                )
        
        @self._app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "ok", "server": "chess-llm-mcp"}
        
        @self._app.get("/capabilities")
        async def get_capabilities():
            """Get server capabilities."""
            return {
                "name": "chess-llm-mcp",
                "version": "1.0.0",
                "capabilities": {
                    "tools": [
                        "start_game",
                        "get_game_state",
                        "make_move",
                        "get_agent_memory",
                        "save_agent_memory",
                        "get_agent_skills",
                        "get_leaderboard",
                        "list_games",
                        "register_agent",
                        "get_agent_state"
                    ],
                    "resources": [
                        "chess://game/{game_id}",
                        "chess://agent/{agent_id}/memory",
                        "chess://agent/{agent_id}/skills",
                        "chess://leaderboard"
                    ]
                }
            }
        
        # Chess-specific endpoints
        @self._app.post("/tools/start_game")
        async def start_game_endpoint(request: Request):
            data = await request.json()
            return await self._tool_start_game(data.get("arguments", {}))
        
        @self._app.post("/tools/get_game_state")
        async def get_game_state_endpoint(request: Request):
            data = await request.json()
            return await self._tool_get_game_state(data.get("arguments", {}))
        
        @self._app.post("/tools/make_move")
        async def make_move_endpoint(request: Request):
            data = await request.json()
            return await self._tool_make_move(data.get("arguments", {}))
        
        @self._app.post("/tools/get_agent_memory")
        async def get_agent_memory_endpoint(request: Request):
            data = await request.json()
            return await self._tool_get_agent_memory(data.get("arguments", {}))
        
        @self._app.post("/tools/save_agent_memory")
        async def save_agent_memory_endpoint(request: Request):
            data = await request.json()
            return await self._tool_save_agent_memory(data.get("arguments", {}))
        
        @self._app.post("/tools/get_agent_skills")
        async def get_agent_skills_endpoint(request: Request):
            data = await request.json()
            return await self._tool_get_agent_skills(data.get("arguments", {}))
        
        @self._app.post("/tools/get_leaderboard")
        async def get_leaderboard_endpoint(request: Request):
            data = await request.json()
            return await self._tool_get_leaderboard(data.get("arguments", {}))
        
        @self._app.post("/tools/list_games")
        async def list_games_endpoint(request: Request):
            data = await request.json()
            return await self._tool_list_games(data.get("arguments", {}))
        
        @self._app.post("/tools/register_agent")
        async def register_agent_endpoint(request: Request):
            data = await request.json()
            return await self._tool_register_agent(data.get("arguments", {}))
        
        @self._app.post("/tools/get_agent_state")
        async def get_agent_state_endpoint(request: Request):
            data = await request.json()
            return await self._tool_get_agent_state(data.get("arguments", {}))
        
        # Resource endpoints
        @self._app.get("/resources/chess://game/{game_id}")
        async def get_game_resource(game_id: str):
            return await self._resource_get_game(game_id)
        
        @self._app.get("/resources/chess://agent/{agent_id}/memory")
        async def get_agent_memory_resource(agent_id: str):
            return await self._resource_get_agent_memory(agent_id)
        
        @self._app.get("/resources/chess://agent/{agent_id}/skills")
        async def get_agent_skills_resource(agent_id: str):
            return await self._resource_get_agent_skills(agent_id)
        
        @self._app.get("/resources/chess://leaderboard")
        async def get_leaderboard_resource():
            return await self._resource_get_leaderboard()
    
    async def _handle_mcp_request(self, request: dict) -> dict:
        """Handle an MCP request."""
        method = request.get("method", "")
        params = request.get("params", {})
        
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            
            # Route to appropriate tool
            tool_map = {
                "start_game": self._tool_start_game,
                "get_game_state": self._tool_get_game_state,
                "make_move": self._tool_make_move,
                "get_agent_memory": self._tool_get_agent_memory,
                "save_agent_memory": self._tool_save_agent_memory,
                "get_agent_skills": self._tool_get_agent_skills,
                "get_leaderboard": self._tool_get_leaderboard,
                "list_games": self._tool_list_games,
                "register_agent": self._tool_register_agent,
                "get_agent_state": self._tool_get_agent_state
            }
            
            if tool_name in tool_map:
                return await tool_map[tool_name](arguments)
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        
        elif method == "resources/read":
            uri = params.get("uri", "")
            
            # Parse URI
            if uri.startswith("chess://game/"):
                game_id = uri.replace("chess://game/", "")
                return await self._resource_get_game(game_id)
            elif uri.startswith("chess://agent/"):
                parts = uri.replace("chess://agent/", "").split("/")
                if len(parts) >= 2:
                    agent_id = parts[0]
                    resource_type = parts[1]
                    
                    if resource_type == "memory":
                        return await self._resource_get_agent_memory(agent_id)
                    elif resource_type == "skills":
                        return await self._resource_get_agent_skills(agent_id)
            elif uri == "chess://leaderboard":
                return await self._resource_get_leaderboard()
        
        return {"error": f"Unknown method: {method}"}
    
    async def _handle_stdio_request(self, request: dict) -> dict:
        """Handle a stdio MCP request."""
        # Similar to HTTP handler but simpler
        method = request.get("method", "")
        params = request.get("params", {})
        
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            
            tool_map = {
                "start_game": self._tool_start_game,
                "get_game_state": self._tool_get_game_state,
                "make_move": self._tool_make_move,
                "get_agent_memory": self._tool_get_agent_memory,
                "save_agent_memory": self._tool_save_agent_memory,
                "get_agent_skills": self._tool_get_agent_skills,
                "get_leaderboard": self._tool_get_leaderboard,
                "list_games": self._tool_list_games,
                "register_agent": self._tool_register_agent,
                "get_agent_state": self._tool_get_agent_state
            }
            
            if tool_name in tool_map:
                import asyncio
                return asyncio.run(tool_map[tool_name](arguments))
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        
        return {"error": f"Unknown method: {method}"}
    
    # ========================================================================
    # Tool Implementations
    # ========================================================================
    
    async def _tool_start_game(self, arguments: dict) -> dict:
        """Start a new chess game."""
        white_agent = arguments.get("white_agent")
        black_agent = arguments.get("black_agent")
        options = arguments.get("options", {})
        
        if not white_agent or not black_agent:
            return {
                "status": "error",
                "error": "white_agent and black_agent are required"
            }
        
        # Register agents if not already registered
        for agent_id in [white_agent, black_agent]:
            if not self._registry.get_agent(agent_id):
                # Try to extract agent type from ID
                if agent_id.startswith("mcp:"):
                    agent_type = "mcp"
                    endpoint = agent_id[4:]
                elif agent_id.startswith("acp:"):
                    agent_type = "acp"
                    endpoint = agent_id[4:]
                elif agent_id.startswith("webhook:"):
                    agent_type = "webhook"
                    endpoint = agent_id[8:]
                elif agent_id.startswith("direct:"):
                    agent_type = "direct"
                    model = agent_id[7:]
                    endpoint = None
                else:
                    # Default to direct with the agent_id as model
                    agent_type = "direct"
                    model = agent_id
                    endpoint = None
                
                self._registry.register_agent(
                    agent_id=agent_id,
                    name=agent_id,
                    agent_type=agent_type,
                    model=model if agent_type == "direct" else None,
                    endpoint=endpoint if endpoint else None
                )
        
        # Create game
        game_id = await self._game_manager.create_game(
            white_agent=white_agent,
            black_agent=black_agent
        )
        
        # Update agent states
        self._registry.update_state(white_agent, status="playing", current_game=game_id)
        self._registry.update_state(black_agent, status="playing", current_game=game_id)
        
        return {
            "status": "success",
            "game_id": game_id,
            "white_agent": white_agent,
            "black_agent": black_agent
        }
    
    async def _tool_get_game_state(self, arguments: dict) -> dict:
        """Get the state of a game."""
        game_id = arguments.get("game_id")
        
        if not game_id:
            return {"status": "error", "error": "game_id is required"}
        
        game = await self._game_manager.get_game(game_id)
        if not game:
            return {"status": "error", "error": f"Game {game_id} not found"}
        
        return {
            "status": "success",
            "game": game.to_dict()
        }
    
    async def _tool_make_move(self, arguments: dict) -> dict:
        """Make a move in a game."""
        game_id = arguments.get("game_id")
        agent_id = arguments.get("agent_id")
        move = arguments.get("move")
        
        if not game_id or not agent_id or not move:
            return {"status": "error", "error": "game_id, agent_id, and move are required"}
        
        result = await self._game_manager.make_move(game_id, agent_id, move)
        return {"status": "success", "result": result}
    
    async def _tool_get_agent_memory(self, arguments: dict) -> dict:
        """Get memories for an agent."""
        agent_id = arguments.get("agent_id")
        limit = arguments.get("limit", 10)
        game_id = arguments.get("game_id")
        
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}
        
        # Query memories
        memories = self._memory_manager.query(
            agent_id=agent_id,
            game_id=game_id,
            limit=limit
        )
        
        return {
            "status": "success",
            "memories": [m.to_dict() for m in memories]
        }
    
    async def _tool_save_agent_memory(self, arguments: dict) -> dict:
        """Save a memory for an agent."""
        agent_id = arguments.get("agent_id")
        memory_data = arguments.get("memory", {})
        
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}
        
        # Create memory entry
        memory = MemoryEntry(
            agent_id=agent_id,
            **{k: v for k, v in memory_data.items() if k in MemoryEntry.__dataclass_fields__}
        )
        
        memory_id = self._memory_manager.save(
            agent_id=agent_id,
            **memory.to_dict()
        )
        
        return {
            "status": "success",
            "memory_id": memory_id
        }
    
    async def _tool_get_agent_skills(self, arguments: dict) -> dict:
        """Get skills for an agent."""
        agent_id = arguments.get("agent_id")
        skill_type = arguments.get("skill_type")
        
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}
        
        # Get skill manager for this agent
        skill_manager = SkillManager(agent_id)
        skills = skill_manager.list_skills(skill_type=skill_type)
        
        return {
            "status": "success",
            "skills": [s.to_dict() for s in skills]
        }
    
    async def _tool_get_leaderboard(self, arguments: dict) -> dict:
        """Get the ELO leaderboard."""
        limit = arguments.get("limit", 20)
        
        # Get ELO tracker
        from chess_llm.elo import EloTracker
        
        try:
            # Try to load from default location
            tracker = EloTracker("ratings.json")
            leaderboard = tracker.leaderboard()
            
            return {
                "status": "success",
                "leaderboard": leaderboard[:limit]
            }
        except Exception as e:
            # Fallback: return agent registry info
            agents = self._registry.list_agents()
            leaderboard = []
            
            for agent in agents:
                state = self._registry.get_state(agent.agent_id)
                leaderboard.append({
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "agent_type": agent.agent_type,
                    "status": state.status if state else "unknown",
                    "rating": 1200  # Default rating
                })
            
            return {
                "status": "success",
                "leaderboard": leaderboard[:limit],
                "note": "ELO ratings not available"
            }
    
    async def _tool_list_games(self, arguments: dict) -> dict:
        """List games."""
        agent_id = arguments.get("agent_id")
        status = arguments.get("status")
        
        games = await self._game_manager.list_games(
            agent_id=agent_id,
            status=status
        )
        
        return {
            "status": "success",
            "games": games
        }
    
    async def _tool_register_agent(self, arguments: dict) -> dict:
        """Register a new agent."""
        agent_id = arguments.get("agent_id")
        name = arguments.get("name", agent_id)
        agent_type = arguments.get("agent_type", "direct")
        model = arguments.get("model")
        endpoint = arguments.get("endpoint")
        api_key = arguments.get("api_key")
        
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}
        
        try:
            config = self._registry.register_agent(
                agent_id=agent_id,
                name=name,
                agent_type=agent_type,
                model=model,
                endpoint=endpoint,
                api_key=api_key
            )
            
            return {
                "status": "success",
                "agent": config.to_dict()
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _tool_get_agent_state(self, arguments: dict) -> dict:
        """Get the state of an agent."""
        agent_id = arguments.get("agent_id")
        
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}
        
        config = self._registry.get_agent(agent_id)
        state = self._registry.get_state(agent_id)
        
        if not config:
            return {"status": "error", "error": f"Agent {agent_id} not found"}
        
        return {
            "status": "success",
            "config": config.to_dict(),
            "state": state.to_dict() if state else None
        }
    
    # ========================================================================
    # Resource Implementations
    # ========================================================================
    
    async def _resource_get_game(self, game_id: str) -> dict:
        """Get game resource."""
        game = await self._game_manager.get_game(game_id)
        if not game:
            return {"status": "error", "error": f"Game {game_id} not found"}
        
        return {
            "uri": f"chess://game/{game_id}",
            "mimeType": "application/json",
            "text": json.dumps(game.to_dict())
        }
    
    async def _resource_get_agent_memory(self, agent_id: str) -> dict:
        """Get agent memory resource."""
        memories = self._memory_manager.query(agent_id=agent_id)
        
        return {
            "uri": f"chess://agent/{agent_id}/memory",
            "mimeType": "application/json",
            "text": json.dumps([m.to_dict() for m in memories])
        }
    
    async def _resource_get_agent_skills(self, agent_id: str) -> dict:
        """Get agent skills resource."""
        skill_manager = SkillManager(agent_id)
        skills = skill_manager.list_skills()
        
        return {
            "uri": f"chess://agent/{agent_id}/skills",
            "mimeType": "application/json",
            "text": json.dumps([s.to_dict() for s in skills])
        }
    
    async def _resource_get_leaderboard(self) -> dict:
        """Get leaderboard resource."""
        result = await self._tool_get_leaderboard({})
        
        return {
            "uri": "chess://leaderboard",
            "mimeType": "application/json",
            "text": json.dumps(result.get("leaderboard", []))
        }


# ============================================================================
# Standalone Server Entry Point
# ============================================================================

import time


def main():
    """Main entry point for running the MCP server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chess LLM MCP Server")
    parser.add_argument("--port", type=int, default=8081, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--transport", type=str, default="http", 
                        choices=["http", "stdio", "sse"], help="Transport type")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Create and start server
    server = ChessMCPServer(
        port=args.port,
        host=args.host,
        transport=args.transport,
        debug=args.debug
    )
    
    print(f"Starting Chess LLM MCP Server on {args.host}:{args.port} ({args.transport})")
    
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
