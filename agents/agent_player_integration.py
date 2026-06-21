"""
Agent Player Integration for LLM Chess

This module provides the AgentHarnessPlayer class which integrates agent harnesses
(OpenCode, Hermes, Vibe CLI) with the existing chess_llm.py infrastructure.

Usage:
    from agents.agent_player_integration import AgentHarnessPlayer
    from agents.harnesses import get_harness
    
    # Create an agent harness player
    harness = get_harness('hermes', 'qwen3.5-27B')
    player = AgentHarnessPlayer(harness)
    
    # Use in a game
    match = ChessMatch(player, stockfish_player)
    result = match.play()
"""

import os
import re
import time
from typing import Any, Optional

import chess

from .harnesses import get_harness, BaseAgentHarness, GameState
from .harnesses.base import AgentResponse, AgentConnectionError, AgentIllegalMoveError


class AgentHarnessPlayer:
    """
    A chess player backed by an external agent harness.
    
    This class adapts the BaseAgentHarness to work with the existing
    ChessMatch infrastructure in chess_llm.py.
    
    It provides the same interface as LLMPlayer (get_move method) but
    uses an agent harness for move generation.
    """
    
    def __init__(
        self,
        harness: BaseAgentHarness,
        name: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
        use_tools: bool = True,
        temperature: float = 0.3,
        tiny: bool = False,
        reasoning: Optional[str] = None,
        constrain: bool = False,
        **kwargs
    ):
        """
        Initialize an AgentHarnessPlayer.
        
        Args:
            harness: The agent harness to use for move generation
            name: Display name for the player
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for illegal moves
            use_tools: Whether to use tool calling
            temperature: Generation temperature
            tiny: Use compact prompts
            reasoning: Reasoning level
            constrain: Automatically constrain illegal moves
        """
        self.harness = harness
        self.name = name or harness.name
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_tools = use_tools
        self.temperature = temperature
        self.tiny = tiny
        self.reasoning = reasoning
        self.constrain = constrain
        
        # Runtime state
        self.illegal_count = 0
        self._timeout_count = 0
        self._empty_response_count = 0
        self._game_id: Optional[str] = None
        self._color: Optional[str] = None
        
        # Update harness settings from player settings
        harness.use_tools = use_tools
        harness.temperature = temperature
        harness.tiny = tiny
        harness.reasoning = reasoning
        harness.constrain = constrain
        harness.timeout = timeout
        harness.max_retries = max_retries
    
    def check_connectivity(self) -> bool:
        """
        Check if the agent harness is reachable.
        
        Returns:
            True if harness is reachable
            
        Raises:
            AgentConnectionError: If harness cannot be connected to
        """
        return self.harness.check_connectivity()
    
    def get_move(self, board: chess.Board, history_text: str) -> chess.Move:
        """
        Get a move from the agent harness for the current board position.
        
        This is the main method called by ChessMatch. It:
        1. Builds the game state
        2. Sends it to the agent harness
        3. Receives and validates the move
        4. Returns the move
        
        Args:
            board: Current board state
            history_text: Text representation of move history
            
        Returns:
            A legal chess.Move
            
        Raises:
            AgentIllegalMoveError: If agent makes too many illegal moves
            AgentConnectionError: If agent cannot be reached
        """
        import random as _random
        
        # Determine color
        color = "White" if board.turn == chess.WHITE else "Black"
        self._color = color.lower()
        
        # Build game state
        game_state = GameState.from_board(
            board, 
            agent_id=self.harness.agent_id if hasattr(self.harness, 'agent_id') else self.name,
            game_id=self._game_id or "game-1"
        )
        
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
                # Get move from agent harness
                result = self.harness.get_move(
                    game_state=game_state,
                    timeout=current_timeout,
                    retry_attempt=empty_retries
                )
                
                proposed_uci = result.move
                reasoning = result.reasoning
                confidence = result.confidence
                
                # Validate and extract move
                move = self._extract_and_validate_move(
                    proposed_uci, board, attempt, reasoning
                )
                
                if move is not None:
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
                raise AgentIllegalMoveError(
                    f"{self.name} timed out after {self.max_retries} attempts"
                ) from e
                
            except Exception as e:
                # Network error, API error, etc.
                if attempt < self.max_retries:
                    wait = 2 ** attempt + _random.uniform(0, 1)
                    print(f"  ⚠ {self.name}: API error ({e}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                raise AgentIllegalMoveError(
                    f"{self.name} hit persistent errors: {e}"
                ) from e
        
        # Should not reach here, but just in case
        raise AgentIllegalMoveError(f"{self.name} failed to make a move")
    
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
            closest = self._find_closest_legal_move(board, proposed_uci)
            print(f"  🔧 {self.name}: '{proposed_uci}' is illegal → constrained to {closest.uci()}")
            return closest
        
        # Move is invalid
        self.illegal_count += 1
        print(f"  ❌ {self.name}: Illegal move '{proposed_uci}' (attempt {attempt}/{self.max_retries})")
        
        return None
    
    def _find_closest_legal_move(self, board: chess.Board, proposed_uci: str) -> chess.Move:
        """Find the closest legal move to the proposed move."""
        import random
        import re
        
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            raise ValueError("No legal moves available")
        
        # Parse UCI manually — board.parse_uci() rejects moves that aren't even
        # pseudo-legal, but we need the from/to squares even for illegal moves.
        # Handle both standard UCI (e2e4) and UCI with promotion (e7e8q)
        m = re.match(r'^([a-h][1-8])([a-h][1-8])([nbrq]?)$', proposed_uci.lower().strip())
        if not m:
            # Try to extract any UCI-like pattern from the string
            uci_match = re.search(r'([a-h][1-8][a-h][1-8][nbrq]?)', proposed_uci.lower())
            if uci_match:
                return self._find_closest_legal_move(board, uci_match.group(1))
            return random.choice(legal_moves)
        
        try:
            from_sq = chess.parse_square(m.group(1))
            to_sq = chess.parse_square(m.group(2))
            promotion = m.group(3) or ''
        except ValueError:
            return random.choice(legal_moves)
        
        # If the from-square actually has one of our pieces, find the closest
        # legal destination among moves from that piece.
        piece = board.piece_at(from_sq)
        if piece is not None and piece.color == board.turn:
            piece_moves = [m for m in legal_moves if m.from_square == from_sq]
            if piece_moves:
                # Filter by promotion piece if specified
                if promotion:
                    piece_moves = [m for m in piece_moves if m.promotion and chess.piece_symbol(m.promotion).lower() == promotion.lower()]
                if piece_moves:
                    def _sq_dist(m: chess.Move) -> int:
                        return (
                            abs(chess.square_file(to_sq) - chess.square_file(m.to_square))
                            + abs(chess.square_rank(to_sq) - chess.square_rank(m.to_square))
                        )
                    return min(piece_moves, key=_sq_dist)
        
        # Strategy 2: Try to find moves to the proposed to-square from any of our pieces
        to_square_moves = [m for m in legal_moves if m.to_square == to_sq]
        if to_square_moves:
            # Find the move from the piece closest to the proposed from-square
            def _from_sq_dist(m: chess.Move) -> int:
                return (
                    abs(chess.square_file(from_sq) - chess.square_file(m.from_square))
                    + abs(chess.square_rank(from_sq) - chess.square_rank(m.from_square))
                )
            return min(to_square_moves, key=_from_sq_dist)
        
        # Last resort
        return random.choice(legal_moves)
    
    def close(self):
        """Close the agent harness player."""
        if hasattr(self.harness, 'close'):
            self.harness.close()
    
    def __repr__(self) -> str:
        return f"AgentHarnessPlayer({self.name})"


def parse_agent_harness_spec(spec: str) -> tuple[str, str, dict]:
    """
    Parse an agent harness specification string.
    
    The spec format is: "harness-name:model-name" or "harness-name"
    For Hermes, you can also specify a profile: "hermes:profile:model" or "hermes:profile"
    
    Examples:
        "hermes:qwen3.5-27B" -> harness='hermes', model='qwen3.5-27B'
        "hermes:chess-profile:qwen3.5-27B" -> harness='hermes', model='qwen3.5-27B', profile='chess-profile'
        "hermes:chess-profile" -> harness='hermes', model=None, profile='chess-profile'
        "hermes:qwen3.5-27B?profile=chess" -> harness='hermes', model='qwen3.5-27B', profile='chess'
        "opencode-agent:deepseek-v4-flash-free" -> harness='opencode-agent', model='deepseek-v4-flash-free'
        "vibe-cli" -> harness='vibe-cli', model=None
    
    Args:
        spec: The specification string
        
    Returns:
        Tuple of (harness_name, model_name, extra_kwargs)
    """
    spec = spec.strip()
    
    # Special handling for Hermes profiles (hermes:profile:model or hermes:profile)
    if spec.startswith("hermes:") or spec.startswith("hermes-agent:"):
        # First, check for query parameters anywhere in the spec
        query_params = {}
        base_spec = spec
        if '?' in spec:
            base_spec, query_string = spec.split('?', 1)
            for param_pair in query_string.split('&'):
                if '=' in param_pair:
                    key, value = param_pair.split('=', 1)
                    query_params[key] = value
        
        # Now parse the base spec
        parts = base_spec.split(':', 2)  # Split into max 3 parts
        harness_name = parts[0].strip()
        
        if len(parts) == 3:
            # hermes:profile:model format
            profile_name = parts[1].strip()
            model_name = parts[2].strip()
            extra_kwargs = {"profile": profile_name}
            
            # Merge query parameters
            extra_kwargs.update(query_params)
            
            return harness_name, model_name, extra_kwargs
        elif len(parts) == 2:
            # Could be hermes:model or hermes:profile
            second_part = parts[1].strip()
            
            # Check if second part looks like a profile name or model name
            # Profile names typically don't contain dots, slashes, or multiple hyphens
            # Model names typically contain dots, slashes, or hyphens
            is_profile = (
                '/' not in second_part and 
                '.' not in second_part and 
                second_part.count('-') <= 1  # Allow simple profile names like "chess-profile"
            )
            
            if is_profile:
                # This is hermes:profile format
                extra_kwargs = {"profile": second_part}
                extra_kwargs.update(query_params)
                return harness_name, None, extra_kwargs
            else:
                # This is hermes:model format
                extra_kwargs = query_params
                return harness_name, second_part, extra_kwargs
        else:
            # Just harness name
            extra_kwargs = query_params
            return harness_name, None, extra_kwargs
    
    # Check for the harness:model pattern (non-Hermes)
    if ':' in spec:
        parts = spec.split(':', 1)
        harness_name = parts[0].strip()
        model_part = parts[1].strip()
        
        # Check if model part contains additional parameters
        model_name = model_part
        extra_kwargs = {}
        
        # Handle query parameters (e.g., "model?timeout=60")
        if '?' in model_part:
            model_name, query_string = model_part.split('?', 1)
            # Parse query parameters
            for param_pair in query_string.split('&'):
                if '=' in param_pair:
                    key, value = param_pair.split('=', 1)
                    extra_kwargs[key] = value
        
        return harness_name, model_name, extra_kwargs
    else:
        # Just harness name, no model specified
        return spec, None, {}


def create_agent_harness_player(
    spec: str,
    color: str = "White",
    timeout: int = 120,
    max_retries: int = 3,
    use_tools: bool = True,
    temperature: float = 0.3,
    tiny: bool = False,
    reasoning: Optional[str] = None,
    constrain: bool = False,
    **kwargs
) -> AgentHarnessPlayer:
    """
    Create an AgentHarnessPlayer from a specification string.
    
    Args:
        spec: Agent harness specification (e.g., "hermes:qwen3.5-27B")
        color: Color the player will play (for display purposes)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries for illegal moves
        use_tools: Whether to use tool calling
        temperature: Generation temperature
        tiny: Use compact prompts
        reasoning: Reasoning level
        constrain: Automatically constrain illegal moves
        **kwargs: Additional arguments passed to the harness
        
    Returns:
        Configured AgentHarnessPlayer
    """
    # Parse the specification
    harness_name, model, extra_kwargs = parse_agent_harness_spec(spec)
    
    # Merge kwargs
    all_kwargs = {**kwargs, **extra_kwargs}
    
    # Create the harness
    try:
        harness = get_harness(
            harness_name,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
            use_tools=use_tools,
            temperature=temperature,
            tiny=tiny,
            reasoning=reasoning,
            constrain=constrain,
            **all_kwargs
        )
    except ValueError as e:
        # Try to create a direct LLM player as fallback
        from chess_llm import LLMPlayer
        return LLMPlayer(
            model=spec,  # Treat the whole spec as a model name
            name=f"{spec} ({color})",
            timeout=timeout,
            max_retries=max_retries,
            use_tools=use_tools,
            temperature=temperature,
            tiny=tiny,
            reasoning=reasoning,
            constrain=constrain,
        )
    
    # Create the player
    player = AgentHarnessPlayer(
        harness=harness,
        name=f"{harness.name} ({color})",
        timeout=timeout,
        max_retries=max_retries,
        use_tools=use_tools,
        temperature=temperature,
        tiny=tiny,
        reasoning=reasoning,
        constrain=constrain,
    )
    
    return player


def is_agent_harness_spec(spec: str) -> bool:
    """
    Check if a player specification is an agent harness spec.
    
    Args:
        spec: The specification string
        
    Returns:
        True if the spec appears to be an agent harness specification
    """
    spec = spec.strip().lower()
    
    # Known agent harness names (exact matches or with :model)
    agent_harnesses = [
        'hermes', 'hermes-agent',
        'opencode-agent',  # Note: 'opencode' alone might be ambiguous
        'vibe', 'vibe-cli', 'vibe_cli',
    ]
    
    # Check for exact harness names or harness:model pattern
    for harness in agent_harnesses:
        # Exact match
        if spec == harness:
            return True
        # Harness:model pattern
        if spec.startswith(harness + ':'):
            return True
    
    # Handle opencode specifically (but not opencode-go, opencode-zen, etc.)
    if spec == 'opencode' or spec.startswith('opencode:'):
        # Make sure it's not opencode-go or opencode-zen (which are provider shortcuts)
        if '/' not in spec:
            return True
    
    # Check for protocol prefixes
    protocol_prefixes = ['mcp:', 'acp:', 'webhook:']
    for prefix in protocol_prefixes:
        if spec.startswith(prefix):
            return True
    
    return False