"""
AgentPlayer - Chess player backed by external agent harnesses.

This module provides the AgentPlayer class which extends LLMPlayer to support
external agent harnesses (MCP, ACP, Webhooks) as chess players.
"""

import asyncio
import json
import os
import time
import uuid
from typing import Any, Optional

import chess
import chess.pgn
import httpx

# Import from parent module
from .registry import AgentRegistry, get_registry
from .memory import MemoryEntry, get_memory_manager
from .skills import AgentSkill, SkillManager, get_skill_extractor


class IllegalMoveForfeit(Exception):
    """Raised when an agent makes too many illegal moves."""
    pass


class AgentConnectionError(Exception):
    """Raised when an agent cannot be connected to."""
    pass


class AgentPlayer:
    """
    A chess player backed by an external agent harness.
    
    Supports multiple agent types:
    - MCP (Model Context Protocol)
    - ACP (Agent Capability Protocol)
    - Webhook (HTTP/JSON)
    - Direct (LLM calls, for backward compatibility)
    
    The AgentPlayer integrates with the existing chess-llm infrastructure
    and can be used in place of LLMPlayer in ChessMatch.
    
    Usage:
        # Create an MCP agent player
        agent = AgentPlayer(
            agent_id="hermes-agent",
            agent_type="mcp",
            endpoint="http://localhost:8081"
        )
        
        # Use in a game
        match = ChessMatch(agent, stockfish_player)
        result = match.play()
    
    Learning:
        The agent automatically saves memories of its moves and can learn
        from completed games. Skills are extracted from memories and can be
        applied in future games.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: Optional[str] = None,
        agent_type: str = "mcp",
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
        use_tools: bool = True,
        temperature: float = 0.3,
        tiny: bool = False,
        reasoning: Optional[str] = None,
        constrain: bool = False,
        learn: bool = True,
        **kwargs
    ):
        """
        Initialize an AgentPlayer.
        
        Args:
            agent_id: Unique identifier for the agent
            name: Display name for the agent
            agent_type: Protocol type ("mcp", "acp", "webhook", "direct")
            endpoint: Endpoint URL (for MCP/Webhook agents)
            model: Model name (for direct/LLM agents)
            api_key: API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for illegal moves
            use_tools: Whether to use tool calling (for direct agents)
            temperature: Generation temperature
            tiny: Use compact prompts
            reasoning: Reasoning level ("low", "medium", "high", "none")
            constrain: Automatically constrain illegal moves
            learn: Whether to enable learning from games
            **kwargs: Additional arguments passed to the underlying client
        """
        self.agent_id = agent_id
        self.name = name or agent_id
        self.agent_type = agent_type.lower()
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_tools = use_tools
        self.temperature = temperature
        self.tiny = tiny
        self.reasoning = reasoning
        self.constrain = constrain
        self.learn = learn
        
        # Runtime state
        self.illegal_count = 0
        self._timeout_count = 0
        self._empty_response_count = 0
        self._game_id: Optional[str] = None
        self._color: Optional[str] = None
        self._move_number: int = 0
        
        # Initialize client based on agent type
        self._client = self._create_client()
        
        # Register agent if not already registered
        self._register_agent()
        
        # Initialize memory and skills
        self._memory_manager = get_memory_manager()
        self._skill_manager = SkillManager(agent_id)
        self._skill_extractor = get_skill_extractor()
    
    def _create_client(self):
        """Create the appropriate client based on agent type."""
        if self.agent_type == "mcp":
            return MCPClient(
                agent_id=self.agent_id,
                endpoint=self.endpoint,
                timeout=self.timeout
            )
        elif self.agent_type == "acp":
            return ACPClient(
                agent_id=self.agent_id,
                endpoint=self.endpoint,
                timeout=self.timeout
            )
        elif self.agent_type == "webhook":
            return WebhookClient(
                agent_id=self.agent_id,
                endpoint=self.endpoint,
                api_key=self.api_key,
                timeout=self.timeout
            )
        elif self.agent_type == "direct":
            return DirectLLMClient(
                agent_id=self.agent_id,
                model=self.model,
                api_key=self.api_key,
                timeout=self.timeout,
                use_tools=self.use_tools,
                temperature=self.temperature,
                tiny=self.tiny,
                reasoning=self.reasoning
            )
        else:
            raise ValueError(f"Unknown agent type: {self.agent_type}")
    
    def _register_agent(self):
        """Register the agent in the global registry."""
        try:
            registry = get_registry()
            existing = registry.get_agent(self.agent_id)
            if not existing:
                registry.register_agent(
                    agent_id=self.agent_id,
                    name=self.name,
                    agent_type=self.agent_type,
                    model=self.model,
                    endpoint=self.endpoint,
                    api_key=self.api_key,
                    timeout=self.timeout,
                    max_retries=self.max_retries,
                    description=f"AgentPlayer: {self.name}"
                )
            else:
                # Update existing registration
                registry.update_state(self.agent_id, status="idle")
        except Exception:
            # Registry might not be available, continue without it
            pass
    
    def check_connectivity(self) -> bool:
        """
        Check if the agent is reachable.
        
        Returns:
            True if agent is reachable, raises exception otherwise
        """
        try:
            # Update state
            try:
                registry = get_registry()
                registry.update_state(
                    self.agent_id,
                    status="connecting",
                    error_message=None
                )
            except:
                pass
            
            # Test connection based on agent type
            if self.agent_type == "mcp":
                # For MCP, we can't easily test without starting a game
                # Just check if endpoint is reachable
                if self.endpoint:
                    asyncio.run(self._test_http_endpoint(self.endpoint))
                return True
            
            elif self.agent_type == "acp":
                # Similar to MCP
                if self.endpoint:
                    asyncio.run(self._test_http_endpoint(self.endpoint))
                return True
            
            elif self.agent_type == "webhook":
                # Test webhook endpoint
                if self.endpoint:
                    asyncio.run(self._test_http_endpoint(self.endpoint))
                return True
            
            elif self.agent_type == "direct":
                # Test LLM connectivity
                return self._client.check_connectivity()
            
            # Update state to connected
            try:
                registry = get_registry()
                registry.update_state(
                    self.agent_id,
                    status="idle",
                    connection_count=1
                )
            except:
                pass
            
            return True
            
        except Exception as e:
            # Update state to error
            try:
                registry = get_registry()
                registry.update_state(
                    self.agent_id,
                    status="error",
                    error_message=str(e)
                )
            except:
                pass
            
            raise AgentConnectionError(f"Cannot connect to agent {self.agent_id}: {e}")
    
    async def _test_http_endpoint(self, url: str):
        """Test if an HTTP endpoint is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{url}/health")
                if response.status_code != 200:
                    raise Exception(f"Health check failed: {response.status_code}")
        except Exception as e:
            # Try without /health
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(url)
                    if response.status_code >= 400:
                        raise Exception(f"Endpoint returned: {response.status_code}")
            except Exception as e2:
                raise Exception(f"Cannot reach endpoint {url}: {e2}") from e
    
    def get_move(self, board: chess.Board, history_text: str) -> chess.Move:
        """
        Get a move from the agent for the current board position.
        
        This is the main method called by ChessMatch. It:
        1. Builds the game state
        2. Sends it to the agent
        3. Receives and validates the move
        4. Saves the experience to memory (if learning enabled)
        5. Returns the move
        
        Args:
            board: Current board state
            history_text: Text representation of move history
            
        Returns:
            A legal chess.Move
            
        Raises:
            IllegalMoveForfeit: If agent makes too many illegal moves
            AgentConnectionError: If agent cannot be reached
        """
        import random as _random
        
        # Determine color
        color = "White" if board.turn == chess.WHITE else "Black"
        self._color = color.lower()
        
        # Build game state
        game_state = self._build_game_state(board, history_text)
        
        # Try to get move from agent
        move = None
        proposed_uci = None
        reasoning = ""
        confidence = 0.5
        
        # Progressive timeout and retry
        current_timeout = self.timeout
        empty_retries = 0
        
        for attempt in range(1, self.max_retries + 1):
            was_retry = attempt > 1
            
            try:
                # Get move from agent
                result = self._client.get_move(
                    game_state=game_state,
                    timeout=current_timeout,
                    retry_attempt=empty_retries
                )
                
                proposed_uci = result.get("move", "").strip()
                reasoning = result.get("reasoning", "")
                confidence = result.get("confidence", 0.5)
                
                # Validate and extract move
                move = self._extract_and_validate_move(
                    proposed_uci, board, attempt, reasoning
                )
                
                if move is not None:
                    # Save to memory if learning enabled
                    if self.learn:
                        self._save_to_memory(
                            board, move, reasoning, confidence, game_state
                        )
                    
                    # Update state
                    try:
                        registry = get_registry()
                        registry.update_state(
                            self.agent_id,
                            status="idle",
                            error_message=None
                        )
                    except:
                        pass
                    
                    return move
                
                # Move was invalid, continue to retry
                
            except TimeoutError as e:
                self._timeout_count += 1
                if attempt < self.max_retries:
                    wait = 2 ** attempt + _random.uniform(0, 1)
                    current_timeout = int(current_timeout * 1.5)
                    print(f"  ⚠ {self.name}: timeout ({e}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                raise IllegalMoveForfeit(
                    f"{self.name} timed out after {self.max_retries} attempts"
                ) from e
                
            except Exception as e:
                # Network error, API error, etc.
                if attempt < self.max_retries:
                    wait = 2 ** attempt + _random.uniform(0, 1)
                    print(f"  ⚠ {self.name}: API error ({e}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                raise IllegalMoveForfeit(
                    f"{self.name} hit persistent errors: {e}"
                ) from e
        
        # Should not reach here, but just in case
        raise IllegalMoveForfeit(f"{self.name} failed to make a move")
    
    def _build_game_state(self, board: chess.Board, history_text: str) -> dict:
        """Build a comprehensive game state for the agent."""
        color = "white" if board.turn == chess.WHITE else "black"
        
        # Get legal moves
        legal_moves = [m.uci() for m in board.legal_moves]
        legal_moves_san = [board.san(m) for m in board.legal_moves]
        
        # Get move history
        move_stack = list(board.move_stack)
        history = [m.uci() for m in move_stack]
        history_san = [board.san(m) for m in move_stack]
        
        # Determine game phase
        phase = self._determine_phase(board, len(move_stack))
        
        # Get opening name if available
        opening = self._get_opening_name(history[:10])
        
        return {
            "game_id": self._game_id or str(uuid.uuid4()),
            "agent_id": self.agent_id,
            "color": color,
            "fen": board.fen(),
            "legal_moves": legal_moves,
            "legal_moves_san": legal_moves_san,
            "move_number": len(move_stack) + 1,
            "history": history,
            "history_san": history_san,
            "phase": phase,
            "opening": opening,
            "board": {
                "piece_placement": board.fen().split()[0],
                "turn": color,
                "castling": board.fen().split()[2],
                "en_passant": board.fen().split()[3],
                "halfmove_clock": board.halfmove_clock,
                "fullmove_number": board.fullmove_number
            },
            "use_tools": self.use_tools,
            "temperature": self.temperature,
            "tiny": self.tiny
        }
    
    def _determine_phase(self, board: chess.Board, move_count: int) -> str:
        """Determine the game phase."""
        if move_count < 10:
            return "opening"
        elif move_count < 30:
            return "middlegame"
        else:
            # Check for endgame
            piece_count = len(board.piece_map())
            if piece_count <= 10:
                return "endgame"
            return "middlegame"
    
    def _get_opening_name(self, moves: list[str]) -> str:
        """Get the opening name from the first few moves."""
        # This is a simplified version
        # In production, use a proper opening database
        
        if len(moves) >= 2:
            if moves[0] == "e2e4" and moves[1] == "e7e5":
                if len(moves) >= 4 and moves[2] == "g1f3" and moves[3] == "b8c6":
                    if len(moves) >= 5 and moves[4] == "f1c4":
                        return "Italian Game"
                    elif len(moves) >= 5 and moves[4] == "f1b5":
                        return "Ruy Lopez"
                return "Open Game"
            elif moves[0] == "d2d4" and moves[1] == "d7d5":
                return "Queen's Gambit Declined"
            elif moves[0] == "e2e4" and moves[1] == "c7c5":
                return "Sicilian Defense"
        
        return ""
    
    def _extract_and_validate_move(
        self,
        proposed_uci: str,
        board: chess.Board,
        attempt: int,
        reasoning: str = ""
    ) -> Optional[chess.Move]:
        """
        Extract and validate a move from the agent's response.
        
        Args:
            proposed_uci: The UCI move string from the agent
            board: Current board state
            attempt: Current attempt number
            reasoning: Agent's reasoning (for error messages)
            
        Returns:
            A valid chess.Move or None if invalid
        """
        if not proposed_uci:
            return None
        
        # Try to parse as UCI
        try:
            move = board.parse_uci(proposed_uci.lower())
            if move in board.legal_moves:
                return move
        except ValueError:
            pass
        
        # Try to parse as SAN
        try:
            move = board.parse_san(proposed_uci)
            if move in board.legal_moves:
                return move
        except ValueError:
            pass
        
        # If constrain mode, find closest legal move
        if self.constrain:
            from chess_llm import _closest_legal_move
            closest = _closest_legal_move(board, proposed_uci)
            print(f"  🔧 {self.name}: '{proposed_uci}' is illegal → constrained to {closest.uci()}")
            return closest
        
        # Move is invalid
        self.illegal_count += 1
        print(f"  ❌ {self.name}: Illegal move '{proposed_uci}' (attempt {attempt}/{self.max_retries})")
        
        return None
    
    def _save_to_memory(
        self,
        board: chess.Board,
        move: chess.Move,
        reasoning: str,
        confidence: float,
        game_state: dict
    ):
        """Save the move experience to memory."""
        try:
            # Get move number
            move_number = len(list(board.move_stack)) + 1
            color = "white" if board.turn == chess.WHITE else "black"
            
            # Save memory
            self._memory_manager.save(
                agent_id=self.agent_id,
                board_state=board.fen(),
                move=move.uci(),
                reasoning=reasoning,
                game_id=game_state.get("game_id", ""),
                move_number=move_number,
                color=color,
                confidence=confidence,
                phase=game_state.get("phase", ""),
                opening=game_state.get("opening", ""),
                tags=["move", f"move-{move_number}"]
            )
            
            # Update state
            try:
                registry = get_registry()
                state = registry.get_state(self.agent_id)
                if state:
                    state.last_activity = datetime.now().isoformat()
            except:
                pass
                
        except Exception as e:
            print(f"  ⚠ {self.name}: Failed to save memory: {e}")
    
    def save_game_result(self, result: str, pgn: str, opponent: str):
        """
        Save the game result and extract lessons.
        
        Args:
            result: Game result ("1-0", "0-1", "1/2-1/2")
            pgn: Game in PGN format
            opponent: Opponent's ID/name
        """
        if not self.learn:
            return
        
        try:
            # Determine outcome from agent's perspective
            if self._color == "white":
                if result == "1-0":
                    outcome = "win"
                elif result == "0-1":
                    outcome = "loss"
                else:
                    outcome = "draw"
            else:  # black
                if result == "0-1":
                    outcome = "win"
                elif result == "1-0":
                    outcome = "loss"
                else:
                    outcome = "draw"
            
            # Update all memories for this game with the outcome
            game_id = self._game_id
            if game_id:
                memories = self._memory_manager.query(
                    agent_id=self.agent_id,
                    game_id=game_id
                )
                
                for memory in memories:
                    memory.outcome = outcome
                    memory.opponent = opponent
                    # Save updated memory
                    self._memory_manager.get_memory(self.agent_id)._save_to_sqlite(memory)
            
            # Extract skills from the game
            self._extract_skills_from_game(pgn, outcome)
            
            # Reset game state
            self._game_id = None
            self._color = None
            self._move_number = 0
            
        except Exception as e:
            print(f"  ⚠ {self.name}: Failed to save game result: {e}")
    
    def _extract_skills_from_game(self, pgn: str, outcome: str):
        """Extract skills from a completed game."""
        try:
            # Parse PGN
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
                
                # Get memory for this move (if it's our move)
                color = "white" if board.turn == chess.BLACK else "black"
                if color == self._color:
                    # This is our move, check if we have a memory for it
                    memories = self._memory_manager.query(
                        agent_id=self.agent_id,
                        game_id=self._game_id,
                        move_number=move_number
                    )
                    
                    for memory in memories:
                        # Extract skills from this memory
                        skills = self._skill_extractor.extract_from_memory(memory)
                        
                        for skill in skills:
                            # Save the skill
                            self._skill_manager.save(skill)
                            
                            # Tag the memory with the skill
                            memory.tags.append(f"skill:{skill.skill_id}")
                            self._memory_manager.get_memory(self.agent_id)._save_to_sqlite(memory)
                
                node = node.variation[0]
            
            # Also extract general game-level skills
            if outcome == "win":
                # Extract winning patterns
                self._extract_winning_patterns(game)
            elif outcome == "loss":
                # Extract lessons from losses
                self._extract_loss_lessons(game)
                
        except Exception as e:
            print(f"  ⚠ {self.name}: Failed to extract skills: {e}")
    
    def _extract_winning_patterns(self, game):
        """Extract patterns from a winning game."""
        # This would analyze the game to find successful patterns
        pass
    
    def _extract_loss_lessons(self, game):
        """Extract lessons from a losing game."""
        # This would analyze the game to find mistakes
        pass
    
    def get_skills(self) -> list[AgentSkill]:
        """Get all skills for this agent."""
        return self._skill_manager.list_skills()
    
    def apply_skills(self, board: chess.Board) -> Optional[chess.Move]:
        """
        Try to apply learned skills to the current position.
        
        Args:
            board: Current board state
            
        Returns:
            A move generated by a skill, or None if no applicable skills
        """
        color = "white" if board.turn == chess.WHITE else "black"
        phase = self._determine_phase(board, len(list(board.move_stack)))
        
        # Find applicable skills
        applicable = self._skill_manager.find_applicable(board, color, phase)
        
        if applicable:
            # Use the most relevant skill
            skill, relevance = applicable[0]
            move = self._skill_manager.apply_skill(skill, board, color)
            
            if move:
                print(f"  🧠 {self.name}: Applied skill '{skill.name}' (relevance: {relevance:.2f})")
                return move
        
        return None
    
    def close(self):
        """Close the agent player and cleanup resources."""
        if hasattr(self._client, "close"):
            self._client.close()
        self._skill_manager.close()


# ============================================================================
# Client Implementations
# ============================================================================

class BaseAgentClient:
    """Base class for agent clients."""
    
    def __init__(self, agent_id: str, timeout: int = 120):
        self.agent_id = agent_id
        self.timeout = timeout
    
    def get_move(self, game_state: dict, timeout: int, retry_attempt: int = 0) -> dict:
        """Get a move from the agent."""
        raise NotImplementedError
    
    def check_connectivity(self) -> bool:
        """Check if the agent is reachable."""
        return True
    
    def close(self):
        """Close the client."""
        pass


class MCPClient(BaseAgentClient):
    """
    MCP (Model Context Protocol) client for communicating with agents.
    
    This client connects to an MCP server and uses the chess tools to get moves.
    """
    
    def __init__(self, agent_id: str, endpoint: Optional[str] = None, timeout: int = 120):
        super().__init__(agent_id, timeout)
        self.endpoint = endpoint
        self._client = None
        self._connected = False
    
    def get_move(self, game_state: dict, timeout: int, retry_attempt: int = 0) -> dict:
        """Get a move from the MCP agent."""
        # For now, use a simple HTTP-based MCP implementation
        # In production, use the official MCP client library
        
        if not self._connected:
            self._connect()
        
        # Build MCP request
        request = {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "play_chess_move",
                "arguments": {
                    "game_state": game_state,
                    "agent_id": self.agent_id
                }
            }
        }
        
        # For now, use HTTP POST to the endpoint
        # This is a simplified implementation
        try:
            import httpx
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self.endpoint}/mcp",
                    json=request
                )
                response.raise_for_status()
                result = response.json()
                
                # Extract move from response
                if "result" in result:
                    return result["result"]
                return result
                
        except Exception as e:
            # Fallback: try to use the move from game_state if it's a simple agent
            # This is for testing purposes
            if retry_attempt == 0:
                # Try to extract a move from the game state
                legal_moves = game_state.get("legal_moves", [])
                if legal_moves:
                    import random
                    return {
                        "move": random.choice(legal_moves),
                        "reasoning": f"Random move from {len(legal_moves)} options",
                        "confidence": 0.3
                    }
            raise
    
    def _connect(self):
        """Connect to the MCP server."""
        # For HTTP-based MCP, just verify the endpoint
        if self.endpoint:
            try:
                import httpx
                with httpx.Client(timeout=5) as client:
                    response = client.get(f"{self.endpoint}/health")
                    if response.status_code == 200:
                        self._connected = True
            except:
                self._connected = False
        else:
            # Stdio-based MCP would be handled differently
            self._connected = True
    
    def check_connectivity(self) -> bool:
        """Check if the MCP agent is reachable."""
        if not self._connected:
            self._connect()
        return self._connected


class ACPClient(BaseAgentClient):
    """
    ACP (Agent Capability Protocol) client for Hermes Agent.
    
    This client communicates with Hermes Agent using ACP.
    """
    
    def __init__(self, agent_id: str, endpoint: Optional[str] = None, timeout: int = 120):
        super().__init__(agent_id, timeout)
        self.endpoint = endpoint
        self._connected = False
    
    def get_move(self, game_state: dict, timeout: int, retry_attempt: int = 0) -> dict:
        """Get a move from the ACP agent."""
        # For now, use HTTP POST to the Hermes endpoint
        try:
            import httpx
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self.endpoint}/acp/play_chess_move",
                    json={
                        "game_state": game_state,
                        "agent_id": self.agent_id
                    }
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            # Fallback
            if retry_attempt == 0:
                legal_moves = game_state.get("legal_moves", [])
                if legal_moves:
                    import random
                    return {
                        "move": random.choice(legal_moves),
                        "reasoning": f"Fallback random move",
                        "confidence": 0.2
                    }
            raise
    
    def check_connectivity(self) -> bool:
        """Check if the ACP agent is reachable."""
        try:
            import httpx
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.endpoint}/health")
                return response.status_code == 200
        except:
            return False


class WebhookClient(BaseAgentClient):
    """
    Webhook client for agents that expose HTTP endpoints.
    """
    
    def __init__(self, agent_id: str, endpoint: Optional[str] = None, api_key: Optional[str] = None, timeout: int = 120):
        super().__init__(agent_id, timeout)
        self.endpoint = endpoint
        self.api_key = api_key
        self._connected = False
    
    def get_move(self, game_state: dict, timeout: int, retry_attempt: int = 0) -> dict:
        """Get a move from the webhook agent."""
        try:
            import httpx
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self.endpoint}/chess/move",
                    json={
                        "agent_id": self.agent_id,
                        "game_id": game_state.get("game_id", ""),
                        "game_state": game_state
                    },
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            # Fallback
            if retry_attempt == 0:
                legal_moves = game_state.get("legal_moves", [])
                if legal_moves:
                    import random
                    return {
                        "move": random.choice(legal_moves),
                        "reasoning": f"Webhook fallback",
                        "confidence": 0.2
                    }
            raise
    
    def check_connectivity(self) -> bool:
        """Check if the webhook agent is reachable."""
        try:
            import httpx
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.endpoint}/health")
                return response.status_code == 200
        except:
            return False


class DirectLLMClient(BaseAgentClient):
    """
    Direct LLM client for agents that use direct LLM calls.
    
    This is essentially a wrapper around the existing LLMPlayer functionality.
    """
    
    def __init__(
        self,
        agent_id: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
        use_tools: bool = True,
        temperature: float = 0.3,
        tiny: bool = False,
        reasoning: Optional[str] = None
    ):
        super().__init__(agent_id, timeout)
        self.model = model or "big-pickle"
        self.api_key = api_key
        self.use_tools = use_tools
        self.temperature = temperature
        self.tiny = tiny
        self.reasoning = reasoning
        self._connected = False
    
    def get_move(self, game_state: dict, timeout: int, retry_attempt: int = 0) -> dict:
        """Get a move using direct LLM call."""
        # Import here to avoid circular imports
        from chess_llm import _call_llm, _extract_move, _TOOLS
        
        board = chess.Board(game_state["fen"])
        
        # Build system prompt
        system = self._build_system(board, game_state.get("history_text", ""))
        
        # Call LLM
        try:
            result = _call_llm(
                model=self.model,
                system=system,
                messages=[],
                tools=_TOOLS if self.use_tools else None,
                temperature=self.temperature,
                api_base=None,
                api_key=self.api_key,
                timeout=timeout,
                reasoning=self.reasoning,
                tiny=self.tiny,
                retry_attempt=retry_attempt
            )
            
            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])
            
            # Extract move
            proposed_uci = None
            if tool_calls:
                tc = tool_calls[0]
                if tc["name"] == "make_move":
                    proposed_uci = tc["arguments"].get("move", "")
            else:
                proposed_uci = _extract_move(content, board)
            
            if proposed_uci:
                return {
                    "move": proposed_uci,
                    "reasoning": content,
                    "confidence": 0.7
                }
            else:
                # Fallback: return first legal move
                legal_moves = list(board.legal_moves)
                if legal_moves:
                    return {
                        "move": legal_moves[0].uci(),
                        "reasoning": "Fallback to first legal move",
                        "confidence": 0.3
                    }
                
        except Exception as e:
            # Fallback
            legal_moves = list(board.legal_moves)
            if legal_moves:
                import random
                return {
                    "move": random.choice(legal_moves).uci(),
                    "reasoning": f"LLM error, fallback: {e}",
                    "confidence": 0.2
                }
            
        raise
    
    def _build_system(self, board: chess.Board, history_text: str) -> str:
        """Build system prompt for the LLM."""
        import textwrap
        
        color = "White" if board.turn == chess.WHITE else "Black"
        legal_uci = [m.uci() for m in board.legal_moves]
        capped = legal_uci[:50]
        suffix = f" ... and {len(legal_uci) - 50} more" if len(legal_uci) > 50 else ""
        
        if self.tiny:
            return textwrap.dedent(f"""\
            You are {color} in a chess game.
            Pick ONE UCI move from the list below.
            Do NOT guess from memory — the board may have changed.
            
            Legal UCI moves: {', '.join(capped)}{suffix}
            
            {'Call the make_move tool with your chosen UCI.' if self.use_tools else 'Output exactly: MOVE: <uci>'}
            """)
        else:
            return textwrap.dedent(f"""\
            You are playing chess as **{color}**. Pick the best legal move.
            
            ## Legal UCI moves (use one of these)
            {', '.join(capped)}{suffix}
            
            ## Board position (FEN — for reference)
            {board.fen()}
            
            ## Recent moves
            {history_text if history_text else "(opening)"}
            
            ## Instructions
            Pick a move from the legal list above. {'Call the make_move tool with your chosen UCI.' if self.use_tools else 'Respond with ONLY the UCI string, nothing else.'}
            UCI format: from-square to-square, e.g. e2e4, g1f3, e7e8q (promotion).""")
    
    def check_connectivity(self) -> bool:
        """Check if the LLM is reachable."""
        from chess_llm import _call_llm
        
        try:
            _call_llm(
                model=self.model,
                system="Respond with exactly the word 'ok'.",
                messages=[],
                temperature=0,
                max_tokens=5,
                timeout=10,
                api_base=None,
                api_key=self.api_key
            )
            self._connected = True
            return True
        except Exception as e:
            self._connected = False
            raise AgentConnectionError(f"Cannot connect to LLM: {e}")


# ============================================================================
# Factory Function
# ============================================================================

class IllegalMoveForfeit(Exception):
    """Raised when an agent makes too many illegal moves."""
    pass


class AgentConnectionError(Exception):
    """Raised when an agent cannot be connected to."""
    pass


# Re-export for convenience
__all__ = [
    "AgentPlayer",
    "BaseAgentClient",
    "MCPClient",
    "ACPClient", 
    "WebhookClient",
    "DirectLLMClient",
    "IllegalMoveForfeit",
    "AgentConnectionError",
]
