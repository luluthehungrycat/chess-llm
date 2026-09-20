"""
ACP Skills for Chess Agent Integration.

This module provides ACP (Agent Capability Protocol) skills for Hermes Agent
and other ACP-compatible agent harnesses. These skills enable agents to:
- Play chess moves
- Analyze games
- Develop and apply skills
- Learn from experience
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import chess
import chess.pgn

# Try to import Hermes Agent, fall back to mock implementation
try:
    from hermes_agent import AgentOS, skill
    HERMES_AVAILABLE = True
except ImportError:
    HERMES_AVAILABLE = False
    
    # Mock implementation for testing without Hermes
    class AgentOS:
        @staticmethod
        def skill():
            def decorator(func):
                return func
            return decorator


from ..memory import MemoryEntry, get_memory_manager
from ..skills import AgentSkill, SkillManager, get_skill_extractor


class ChessSkills:
    """
    ACP skills for chess agents.
    
    This class provides a set of skills that can be registered with
    Hermes Agent or other ACP-compatible systems.
    
    Usage with Hermes Agent:
        from hermes_agent import AgentOS
        from chess_llm.agents.protocols.acp_skills import ChessSkills
        
        agent = AgentOS()
        chess_skills = ChessSkills()
        agent.register_skills(chess_skills)
    """
    
    def __init__(self):
        self._memory_manager = get_memory_manager()
        self._skill_extractor = get_skill_extractor()
    
    @AgentOS.skill()
    async def play_chess_move(
        self,
        game_state: dict,
        agent_context: Optional[dict] = None
    ) -> dict:
        """
        Analyze the current board position and return the best move.
        
        This is the primary skill for playing chess. The agent receives
        the current game state and should return a move in UCI notation.
        
        Args:
            game_state: Dictionary containing:
                - board: FEN string
                - legal_moves: List of legal UCI moves
                - history: List of previous moves (UCI)
                - color: "white" or "black"
                - move_number: Current move number
                - phase: "opening", "middlegame", or "endgame"
                - opening: Opening name (if known)
                - use_tools: Whether tool calling is enabled
                - temperature: Generation temperature
                - tiny: Whether to use compact prompts
            agent_context: Optional agent-specific context
            
        Returns:
            Dictionary containing:
                - move: UCI move string (required)
                - reasoning: Thought process (optional)
                - confidence: Confidence score (0.0-1.0, optional)
                - alternatives: List of alternative moves with evaluations (optional)
                - evaluation: Position evaluation score (optional)
        """
        try:
            # Parse game state
            board = chess.Board(game_state.get("board", chess.STARTING_FEN))
            color = game_state.get("color", "white")
            legal_moves = game_state.get("legal_moves", [])
            move_number = game_state.get("move_number", 0)
            phase = game_state.get("phase", "opening")
            opening = game_state.get("opening", "")
            
            # Get agent ID from context
            agent_id = agent_context.get("agent_id", "default") if agent_context else "default"
            
            # Try to apply learned skills first
            skill_manager = SkillManager(agent_id)
            applicable_skills = skill_manager.find_applicable(board, color, phase)
            
            if applicable_skills:
                # Use the most relevant skill
                skill, relevance = applicable_skills[0]
                move_obj = skill_manager.apply_skill(skill, board, color)
                
                if move_obj:
                    move_uci = move_obj.uci()
                    move_san = board.san(move_obj)
                    
                    return {
                        "move": move_uci,
                        "reasoning": f"Applied learned skill: {skill.name} (relevance: {relevance:.2f})",
                        "confidence": min(0.9, 0.5 + skill.success_rate * 0.4),
                        "alternatives": [],
                        "evaluation": None
                    }
            
            # No applicable skills, use LLM to generate move
            # This would be the agent's own reasoning
            # For now, return a simple move
            
            if legal_moves:
                # Simple strategy: pick the first legal move
                # In production, this would use the agent's LLM
                move_uci = legal_moves[0]
                move_obj = board.parse_uci(move_uci)
                move_san = board.san(move_obj)
                
                reasoning = f"Move {move_number}: {move_san}. "
                reasoning += f"Phase: {phase}. "
                if opening:
                    reasoning += f"Opening: {opening}. "
                reasoning += f"{len(legal_moves)} legal moves available."
                
                return {
                    "move": move_uci,
                    "reasoning": reasoning,
                    "confidence": 0.5,
                    "alternatives": [
                        {"move": m, "eval": 0.0} for m in legal_moves[1:5]
                    ],
                    "evaluation": None
                }
            else:
                # No legal moves - game must be over
                return {
                    "move": None,
                    "reasoning": "No legal moves available - game is over",
                    "confidence": 0.0,
                    "alternatives": [],
                    "evaluation": None
                }
                
        except Exception as e:
            # Fallback: return first legal move
            try:
                board = chess.Board(game_state.get("board", chess.STARTING_FEN))
                legal_moves = [m.uci() for m in board.legal_moves]
                if legal_moves:
                    return {
                        "move": legal_moves[0],
                        "reasoning": f"Error in analysis, fallback: {e}",
                        "confidence": 0.2,
                        "alternatives": [],
                        "evaluation": None
                    }
            except:
                pass
            
            return {
                "move": None,
                "reasoning": f"Error: {e}",
                "confidence": 0.0,
                "alternatives": [],
                "evaluation": None
            }
    
    @AgentOS.skill()
    async def analyze_game(
        self,
        pgn: str,
        agent_id: str,
        agent_context: Optional[dict] = None
    ) -> dict:
        """
        Analyze a completed game and extract lessons.
        
        This skill is called when a game is completed to extract
        lessons and improve the agent's future performance.
        
        Args:
            pgn: Game in PGN format
            agent_id: ID of the agent to learn from
            agent_context: Optional agent-specific context
            
        Returns:
            Dictionary containing:
                - lessons: List of lesson strings
                - critical_moves: List of critical moves with analysis
                - opening: Detected opening
                - outcome: Game result ("win", "loss", "draw")
                - summary: Overall game summary
        """
        try:
            # Parse PGN
            import io
            pgn_file = io.StringIO(pgn)
            game = chess.pgn.read_game(pgn_file)
            
            if not game:
                return {
                    "lessons": [],
                    "critical_moves": [],
                    "opening": "",
                    "outcome": "unknown",
                    "summary": "Failed to parse PGN"
                }
            
            # Extract basic info
            outcome = "draw"
            if game.headers.get("Result") == "1-0":
                outcome = "win"
            elif game.headers.get("Result") == "0-1":
                outcome = "loss"
            
            opening = game.headers.get("Opening", "")
            
            # Analyze the game
            board = game.board()
            node = game
            move_number = 0
            lessons = []
            critical_moves = []
            
            while node.variations:
                move_number += 1
                next_node = node.variation[0]
                move = next_node.move
                board.push(move)
                
                # Analyze this move
                move_analysis = self._analyze_move(board, move, move_number)
                
                if move_analysis:
                    if move_analysis.get("is_critical"):
                        critical_moves.append({
                            "move": move_number,
                            "san": board.san(move.move),
                            "uci": move.move.uci(),
                            "eval": move_analysis.get("eval", "neutral"),
                            "lesson": move_analysis.get("lesson", "")
                        })
                    
                    if move_analysis.get("lesson"):
                        lessons.append(move_analysis["lesson"])
                
                node = node.variation[0]
            
            # Generate summary
            summary = self._generate_summary(
                pgn, outcome, opening, lessons, critical_moves
            )
            
            # Save lessons to memory
            self._save_lessons_to_memory(agent_id, pgn, lessons, critical_moves, outcome)
            
            return {
                "lessons": lessons,
                "critical_moves": critical_moves,
                "opening": opening,
                "outcome": outcome,
                "summary": summary
            }
            
        except Exception as e:
            return {
                "lessons": [f"Analysis failed: {e}"],
                "critical_moves": [],
                "opening": "",
                "outcome": "unknown",
                "summary": f"Error analyzing game: {e}"
            }
    
    def _analyze_move(
        self,
        board: chess.Board,
        move: chess.Move,
        move_number: int
    ) -> Optional[dict]:
        """
        Analyze a single move for potential lessons.
        
        Args:
            board: Board state after the move
            move: The move that was made
            move_number: Move number
            
        Returns:
            Dictionary with analysis or None if no lesson
        """
        try:
            # Check for blunders (move that loses significant material)
            if self._is_blunder(board, move):
                return {
                    "is_critical": True,
                    "eval": "blunder",
                    "lesson": self._generate_blunder_lesson(board, move)
                }
            
            # Check for missed opportunities
            if self._has_better_move(board, move):
                better_move = self._find_better_move(board)
                if better_move:
                    return {
                        "is_critical": True,
                        "eval": "missed_opportunity",
                        "lesson": self._generate_opportunity_lesson(board, move, better_move)
                    }
            
            # Check for good moves
            if self._is_good_move(board, move):
                return {
                    "is_critical": False,
                    "eval": "good_move",
                    "lesson": self._generate_good_move_lesson(board, move)
                }
            
            # Check for tactical patterns
            pattern = self._detect_tactical_pattern(board, move)
            if pattern:
                return {
                    "is_critical": True,
                    "eval": "tactical_pattern",
                    "lesson": f"Recognized {pattern} pattern"
                }
            
            return None
            
        except Exception:
            return None
    
    def _is_blunder(self, board: chess.Board, move: chess.Move) -> bool:
        """Check if a move is a blunder."""
        # Simple heuristic: check if the move leaves a piece en prise
        # or loses significant material
        
        # Check if the moved piece is now under attack
        if board.is_attacked_by(not board.turn, move.to_square):
            piece = board.piece_at(move.to_square)
            if piece and piece.piece_type != chess.PAWN:
                # Piece is under attack - might be a blunder
                return True
        
        # More sophisticated analysis would use evaluation
        return False
    
    def _has_better_move(self, board: chess.Board) -> bool:
        """Check if there's a significantly better move."""
        # Simple heuristic: always return False for now
        # In production, this would use evaluation
        return False
    
    def _find_better_move(self, board: chess.Board) -> Optional[chess.Move]:
        """Find a better move than the one played."""
        # For now, just return None
        return None
    
    def _is_good_move(self, board: chess.Board, move: chess.Move) -> bool:
        """Check if a move is particularly good."""
        # Simple heuristic: check if the move captures a piece
        piece_at_to = board.piece_at(move.to_square)
        if piece_at_to and piece_at_to.color != board.turn:
            return True
        
        # Check if the move gives check
        board_copy = board.copy()
        board_copy.push(move)
        if board_copy.is_check():
            return True
        
        return False
    
    def _detect_tactical_pattern(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> Optional[str]:
        """Detect tactical patterns in a move."""
        # Check for common tactical patterns
        
        # Fork: move attacks multiple pieces
        attacked_squares = board.attackers(board.turn, move.to_square)
        if len(attacked_squares) >= 2:
            return "fork"
        
        # Pin: move pins a piece
        if board.is_pinned(not board.turn, move.to_square):
            return "pin"
        
        # Skewer: move creates a skewer
        # (simplified detection)
        return None
    
    def _generate_blunder_lesson(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> str:
        """Generate a lesson for a blunder."""
        piece = board.piece_at(move.to_square)
        if piece:
            return f"Avoid moving {piece.symbol()} to {chess.square_name(move.to_square)} where it's under attack"
        return "Avoid leaving pieces en prise"
    
    def _generate_opportunity_lesson(
        self,
        board: chess.Board,
        move: chess.Move,
        better_move: chess.Move
    ) -> str:
        """Generate a lesson for a missed opportunity."""
        return f"Consider {board.san(better_move)} instead of {board.san(move)} in similar positions"
    
    def _generate_good_move_lesson(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> str:
        """Generate a lesson for a good move."""
        piece_at_to = board.piece_at(move.to_square)
        if piece_at_to and piece_at_to.color != board.turn:
            return f"Good capture: {board.san(move)} wins material"
        
        board_copy = board.copy()
        board_copy.push(move)
        if board_copy.is_check():
            return f"Good check: {board.san(move)} puts opponent in check"
        
        return f"Good move: {board.san(move)}"
    
    def _generate_summary(
        self,
        pgn: str,
        outcome: str,
        opening: str,
        lessons: list[str],
        critical_moves: list[dict]
    ) -> str:
        """Generate a summary of the game analysis."""
        summary = f"Game result: {outcome}. "
        if opening:
            summary += f"Opening: {opening}. "
        
        summary += f"Found {len(lessons)} lessons and {len(critical_moves)} critical moves. "
        
        if critical_moves:
            summary += "Key moments: "
            for cm in critical_moves[:3]:  # Top 3 critical moves
                summary += f"move {cm['move']} ({cm['eval']}), "
            summary = summary.rstrip(", ") + ". "
        
        return summary
    
    def _save_lessons_to_memory(
        self,
        agent_id: str,
        pgn: str,
        lessons: list[str],
        critical_moves: list[dict],
        outcome: str
    ):
        """Save extracted lessons to the agent's memory."""
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
                
                # Find lessons for this move
                move_lessons = []
                for cm in critical_moves:
                    if cm["move"] == move_number:
                        move_lessons.append(cm["lesson"])
                
                # Add general lessons
                move_lessons.extend(lessons)
                
                # Save memory
                self._memory_manager.save(
                    agent_id=agent_id,
                    board_state=board.fen(),
                    move=move.uci(),
                    reasoning=f"Move {move_number}: {board.san(move)}",
                    game_id="",
                    move_number=move_number,
                    color="white" if board.turn == chess.BLACK else "black",
                    confidence=0.5,
                    outcome=outcome,
                    lessons=move_lessons,
                    tags=["analysis", f"move-{move_number}"]
                )
                
                node = next_node
                
        except Exception as e:
            print(f"Failed to save lessons to memory: {e}")
    
    @AgentOS.skill()
    async def develop_skill(
        self,
        memories: list[dict],
        skill_type: str,
        agent_id: str,
        agent_context: Optional[dict] = None
    ) -> dict:
        """
        Develop a new skill from agent memories.
        
        This skill clusters similar memories and extracts a reusable
        pattern or strategy.
        
        Args:
            memories: List of memory dictionaries
            skill_type: Type of skill to develop ("opening", "tactic", "endgame", "pattern")
            agent_id: ID of the agent
            agent_context: Optional agent-specific context
            
        Returns:
            Dictionary containing:
                - skill: The created AgentSkill
                - memories_used: IDs of memories used to create the skill
                - coverage: Percentage of memories covered by this skill
        """
        try:
            # Convert memory dicts to MemoryEntry objects
            memory_entries = [
                MemoryEntry.from_dict(m) for m in memories
            ]
            
            # Use skill extractor to create skills
            skill_extractor = get_skill_extractor()
            skills = []
            
            for memory in memory_entries:
                skills.extend(skill_extractor.extract_from_memory(memory))
            
            # Filter by skill type
            if skill_type:
                skills = [s for s in skills if s.skill_type == skill_type]
            
            if not skills:
                return {
                    "skill": None,
                    "memories_used": [],
                    "coverage": 0.0,
                    "error": "No skills extracted from memories"
                }
            
            # For now, just return the first skill
            skill = skills[0]
            
            # Save the skill
            skill_manager = SkillManager(agent_id)
            skill_id = skill_manager.save(skill)
            skill.skill_id = skill_id
            
            return {
                "skill": skill.to_dict(),
                "memories_used": [m.memory_id for m in memory_entries],
                "coverage": 1.0
            }
            
        except Exception as e:
            return {
                "skill": None,
                "memories_used": [],
                "coverage": 0.0,
                "error": str(e)
            }
    
    @AgentOS.skill()
    async def get_agent_state(
        self,
        agent_id: str,
        agent_context: Optional[dict] = None
    ) -> dict:
        """
        Get the current state of an agent.
        
        Args:
            agent_id: ID of the agent
            agent_context: Optional agent-specific context
            
        Returns:
            Dictionary containing:
                - agent_id: Agent ID
                - status: Current status
                - current_game: Current game ID (if playing)
                - last_activity: Last activity timestamp
                - games_played: Number of games played
                - skills_learned: Number of skills learned
                - memories_count: Number of memories stored
        """
        try:
            from ..registry import get_registry
            from ..memory import get_memory_manager
            from ..skills import SkillManager
            
            registry = get_registry()
            memory_manager = get_memory_manager()
            
            config = registry.get_agent(agent_id)
            state = registry.get_state(agent_id)
            
            if not config:
                return {
                    "error": f"Agent {agent_id} not found"
                }
            
            # Get memory count
            memories = memory_manager.query(agent_id=agent_id)
            memory_count = len(memories)
            
            # Get skill count
            skill_manager = SkillManager(agent_id)
            skills = skill_manager.list_skills()
            skill_count = len(skills)
            
            return {
                "agent_id": agent_id,
                "status": state.status if state else "unknown",
                "current_game": state.current_game if state else None,
                "last_activity": state.last_activity if state else None,
                "games_played": 0,  # Would track this in production
                "skills_learned": skill_count,
                "memories_count": memory_count
            }
            
        except Exception as e:
            return {
                "error": str(e)
            }
    
    @AgentOS.skill()
    async def query_memories(
        self,
        agent_id: str,
        query: dict,
        agent_context: Optional[dict] = None
    ) -> dict:
        """
        Query an agent's memories.
        
        Args:
            agent_id: ID of the agent
            query: Query parameters (board_state, game_id, opening, phase, tag, limit)
            agent_context: Optional agent-specific context
            
        Returns:
            Dictionary containing:
                - memories: List of matching memories
                - count: Total number of matching memories
        """
        try:
            memory_manager = get_memory_manager()
            
            memories = memory_manager.query(
                agent_id=agent_id,
                **query
            )
            
            return {
                "memories": [m.to_dict() for m in memories],
                "count": len(memories)
            }
            
        except Exception as e:
            return {
                "memories": [],
                "count": 0,
                "error": str(e)
            }
    
    @AgentOS.skill()
    async def get_leaderboard(
        self,
        limit: int = 20,
        agent_context: Optional[dict] = None
    ) -> dict:
        """
        Get the ELO leaderboard.
        
        Args:
            limit: Maximum number of entries to return
            agent_context: Optional agent-specific context
            
        Returns:
            Dictionary containing:
                - leaderboard: List of entries with agent_id, name, rating, etc.
        """
        try:
            from chess_llm.elo import EloTracker
            
            try:
                tracker = EloTracker("ratings.json")
                leaderboard = tracker.leaderboard()
                
                return {
                    "leaderboard": leaderboard[:limit]
                }
            except Exception:
                # Fallback to agent registry
                from ..registry import get_registry
                registry = get_registry()
                agents = registry.list_agents()
                
                leaderboard = []
                for agent in agents:
                    state = registry.get_state(agent.agent_id)
                    leaderboard.append({
                        "agent_id": agent.agent_id,
                        "name": agent.name,
                        "agent_type": agent.agent_type,
                        "status": state.status if state else "unknown",
                        "rating": 1200  # Default rating
                    })
                
                return {
                    "leaderboard": leaderboard[:limit],
                    "note": "ELO ratings not available"
                }
                
        except Exception as e:
            return {
                "leaderboard": [],
                "error": str(e)
            }


# ============================================================================
# Helper Functions
# ============================================================================

class ChessACPHandler:
    """
    Handler for ACP-based chess operations.
    
    This class provides methods for handling ACP requests from Hermes Agent
    or other ACP-compatible systems.
    """
    
    def __init__(self):
        self._chess_skills = ChessSkills()
    
    async def handle_skill_call(self, skill_name: str, arguments: dict) -> dict:
        """
        Handle a skill call from an ACP client.
        
        Args:
            skill_name: Name of the skill to call
            arguments: Arguments for the skill
            
        Returns:
            Result of the skill call
        """
        skill_map = {
            "play_chess_move": self._chess_skills.play_chess_move,
            "analyze_game": self._chess_skills.analyze_game,
            "develop_skill": self._chess_skills.develop_skill,
            "get_agent_state": self._chess_skills.get_agent_state,
            "query_memories": self._chess_skills.query_memories,
            "get_leaderboard": self._chess_skills.get_leaderboard
        }
        
        if skill_name in skill_map:
            # Call the skill
            import asyncio
            result = await skill_map[skill_name](**arguments)
            return result
        else:
            return {"error": f"Unknown skill: {skill_name}"}


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "ChessSkills",
    "ChessACPHandler"
]
