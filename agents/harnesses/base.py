"""
Base Agent Harness for LLM Chess

This module provides the base class and interface for all agent harnesses.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import chess
import httpx


class AgentHarnessError(Exception):
    """Base exception for agent harness errors."""
    pass


class AgentConnectionError(AgentHarnessError):
    """Raised when an agent harness cannot be connected to."""
    pass


class AgentTimeoutError(AgentHarnessError):
    """Raised when an agent harness times out."""
    pass


class AgentIllegalMoveError(AgentHarnessError):
    """Raised when an agent makes an illegal move."""
    pass


@dataclass
class AgentResponse:
    """Response from an agent harness."""
    move: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.5
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    error: Optional[str] = None
    
    def is_valid(self) -> bool:
        """Check if the response contains a valid move."""
        return self.move is not None and not self.error


@dataclass
class GameState:
    """Current game state for agent decision making."""
    fen: str
    legal_moves: List[str]
    legal_moves_san: List[str]
    move_number: int
    history: List[str]
    history_san: List[str]
    color: str  # 'white' or 'black'
    phase: str = "opening"  # 'opening', 'middlegame', 'endgame'
    opening: str = ""
    game_id: str = ""
    agent_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "fen": self.fen,
            "legal_moves": self.legal_moves,
            "legal_moves_san": self.legal_moves_san,
            "move_number": self.move_number,
            "history": self.history,
            "history_san": self.history_san,
            "color": self.color,
            "phase": self.phase,
            "opening": self.opening,
            "game_id": self.game_id,
            "agent_id": self.agent_id,
        }
    
    @classmethod
    def from_board(cls, board: chess.Board, agent_id: str, game_id: str = "") -> 'GameState':
        """Create GameState from a chess board."""
        color = "white" if board.turn == chess.WHITE else "black"
        move_stack = list(board.move_stack)
        
        # Determine phase
        move_count = len(move_stack)
        if move_count < 10:
            phase = "opening"
        elif move_count < 30:
            phase = "middlegame"
        else:
            piece_count = len(board.piece_map())
            phase = "endgame" if piece_count <= 10 else "middlegame"
        
        # Try to determine opening (simplified)
        opening = cls._get_opening_name([m.uci() for m in move_stack[:10]])
        
        # For history_san, we need to replay the moves on a fresh board to get correct SAN
        temp_board = chess.Board()
        history_san = []
        for move in move_stack:
            # Get SAN representation before pushing the move
            san_move = temp_board.san(move)
            temp_board.push(move)
            history_san.append(san_move)
        
        return cls(
            fen=board.fen(),
            legal_moves=[m.uci() for m in board.legal_moves],
            legal_moves_san=[board.san(m) for m in board.legal_moves],
            move_number=len(move_stack) + 1,
            history=[m.uci() for m in move_stack],
            history_san=history_san,
            color=color,
            phase=phase,
            opening=opening,
            game_id=game_id,
            agent_id=agent_id,
        )
    
    @staticmethod
    def _get_opening_name(moves: List[str]) -> str:
        """Get opening name from move sequence (simplified)."""
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
            elif moves[0] == "d2d4" and moves[1] == "g8f6":
                return "Indian Defense"
        return ""


class BaseAgentHarness(ABC):
    """
    Base class for all agent harnesses.
    
    Agent harnesses are external systems that can play chess autonomously.
    They can communicate via various protocols (MCP, ACP, Webhooks, CLI).
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
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
        Initialize the agent harness.
        
        Args:
            model: Model to use with the harness
            name: Display name for the harness
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for illegal moves
            use_tools: Whether to use tool calling
            temperature: Generation temperature
            tiny: Use compact prompts
            reasoning: Reasoning level
            constrain: Automatically constrain illegal moves
            **kwargs: Additional harness-specific arguments
        """
        self.model = model
        self.name = name or f"{self.harness_name}:{model}" if model else self.harness_name
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
        
        # Initialize the harness
        self._initialize(**kwargs)
    
    @property
    @abstractmethod
    def harness_name(self) -> str:
        """Name of the harness (e.g., 'opencode', 'hermes', 'vibe-cli')."""
        pass
    
    @property
    @abstractmethod 
    def harness_type(self) -> str:
        """Type of harness (e.g., 'mcp', 'acp', 'webhook', 'cli')."""
        pass
    
    @abstractmethod
    def _initialize(self, **kwargs):
        """Initialize the harness with specific configuration."""
        pass
    
    @abstractmethod
    def check_connectivity(self) -> bool:
        """
        Check if the agent harness is reachable and ready.
        
        Returns:
            True if harness is reachable
            
        Raises:
            AgentConnectionError: If harness cannot be connected to
        """
        pass
    
    @abstractmethod
    async def get_move_async(self, game_state: GameState, timeout: int, retry_attempt: int = 0) -> AgentResponse:
        """
        Get a move from the agent harness (async version).
        
        Args:
            game_state: Current game state
            timeout: Timeout in seconds
            retry_attempt: Current retry attempt number
            
        Returns:
            AgentResponse with the move and metadata
        """
        pass
    
    def get_move(self, game_state: GameState, timeout: int, retry_attempt: int = 0) -> AgentResponse:
        """
        Get a move from the agent harness (sync version).
        
        Args:
            game_state: Current game state
            timeout: Timeout in seconds
            retry_attempt: Current retry attempt number
            
        Returns:
            AgentResponse with the move and metadata
        """
        return asyncio.run(self.get_move_async(game_state, timeout, retry_attempt))
    
    def extract_move(self, response: AgentResponse, board: chess.Board) -> Optional[chess.Move]:
        """
        Extract and validate a move from an agent response.
        
        Args:
            response: Agent response containing the move
            board: Current board state
            
        Returns:
            Valid chess.Move or None if invalid
        """
        if not response.is_valid() or not response.move:
            return None
        
        proposed_uci = response.move.strip()
        
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
            return self._find_closest_legal_move(board, proposed_uci)
        
        return None
    
    def _find_closest_legal_move(self, board: chess.Board, proposed_uci: str) -> chess.Move:
        """Find the closest legal move to the proposed move."""
        import random
        
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            raise ValueError("No legal moves available")
        
        # Simple implementation: return random legal move
        # In a more sophisticated implementation, this would find the move
        # with the closest from/to squares
        return random.choice(legal_moves)
    
    def build_prompt(self, game_state: GameState) -> str:
        """
        Build the prompt to send to the agent.
        
        Args:
            game_state: Current game state
            
        Returns:
            Formatted prompt string
        """
        if self.tiny:
            return self._build_tiny_prompt(game_state)
        else:
            return self._build_full_prompt(game_state)
    
    def _build_full_prompt(self, game_state: GameState) -> str:
        """Build a full prompt with all game information."""
        color = "White" if game_state.color == "white" else "Black"
        legal_moves = game_state.legal_moves[:50]
        suffix = f" ... and {len(game_state.legal_moves) - 50} more" if len(game_state.legal_moves) > 50 else ""
        
        prompt = f"""You are playing chess as **{color}**. Pick the best legal move.

## Legal UCI moves (use one of these)
{', '.join(legal_moves)}{suffix}

## Board position (FEN — for reference)
{game_state.fen}

## Recent moves
{game_state.history_san[-10:] if game_state.history_san else '(opening)'}

## Instructions
Pick a move from the legal list above. {'Call the make_move tool with your chosen UCI.' if self.use_tools else 'Respond with ONLY the UCI string, nothing else.'}
UCI format: from-square to-square, e.g. e2e4, g1f3, e7e8q (promotion)."""
        
        return prompt
    
    def _build_tiny_prompt(self, game_state: GameState) -> str:
        """Build a compact prompt for smaller models."""
        color = "White" if game_state.color == "white" else "Black"
        legal_moves = game_state.legal_moves[:30]
        
        prompt = f"""You are {color} in a chess game.
Pick ONE UCI move from the list below.
Do NOT guess from memory — the board may have changed.

Legal UCI moves: {', '.join(legal_moves)}

{'Call the make_move tool with your chosen UCI.' if self.use_tools else 'Output exactly: MOVE: <uci>'}

{'Example: MOVE: ' + legal_moves[0] if legal_moves else ''}

Nothing else. No explanation."""
        
        return prompt
    
    def close(self):
        """Close the harness and cleanup resources."""
        pass
    
    def __repr__(self) -> str:
        return f"{self.harness_name}:{self.model}" if self.model else self.harness_name