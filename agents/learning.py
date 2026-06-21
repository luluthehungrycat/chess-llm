"""
Learning System for Chess Agents.

This module provides the learning infrastructure for chess agents, including:
- Lesson extraction from games
- Skill development from memories
- Performance tracking
- Adaptive learning strategies
"""

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import chess
import chess.pgn

from .memory import MemoryEntry, get_memory_manager
from .skills import AgentSkill, SkillManager, get_skill_extractor


@dataclass
class Lesson:
    """A lesson extracted from a chess game."""
    lesson_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    game_id: str = ""
    move_number: int = 0
    
    # Lesson content
    lesson_type: str = ""  # "blunder", "missed_opportunity", "good_move", "tactical", "strategic"
    title: str = ""
    description: str = ""
    
    # Context
    board_state: str = ""  # FEN
    move: str = ""  # UCI
    move_san: str = ""  # SAN
    color: str = ""  # "white" or "black"
    
    # Severity/importance
    severity: str = "medium"  # "low", "medium", "high"
    priority: float = 0.5  # 0.0-1.0
    
    # Metadata
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_reviewed: Optional[str] = None
    review_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Lesson":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PerformanceMetric:
    """Performance metric for an agent."""
    metric_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    metric_type: str = ""  # "elo", "win_rate", "move_quality", "response_time"
    value: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    game_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PerformanceMetric":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class LessonExtractor:
    """
    Extracts lessons from chess games and memories.
    
    This class analyzes completed games to identify:
    - Blunders (moves that lose material or position)
    - Missed opportunities (better moves were available)
    - Good moves (captures, checks, tactical patterns)
    - Strategic insights (positional improvements)
    
    Usage:
        extractor = LessonExtractor()
        lessons = extractor.extract_from_pgn(pgn, agent_id, agent_color)
        
        for lesson in lessons:
            print(f"{lesson.lesson_type}: {lesson.title}")
            print(f"  {lesson.description}")
    """
    
    def __init__(self):
        self._skill_extractor = get_skill_extractor()
    
    def extract_from_pgn(
        self,
        pgn: str,
        agent_id: str,
        agent_color: str = "white"
    ) -> list[Lesson]:
        """
        Extract lessons from a PGN game.
        
        Args:
            pgn: Game in PGN format
            agent_id: ID of the agent
            agent_color: Color the agent was playing ("white" or "black")
            
        Returns:
            List of extracted Lesson objects
        """
        lessons = []
        
        try:
            # Parse PGN
            import io
            pgn_file = io.StringIO(pgn)
            game = chess.pgn.read_game(pgn_file)
            
            if not game:
                return lessons
            
            # Get game result
            result = game.headers.get("Result", "*")
            
            # Determine if agent won
            if agent_color == "white":
                agent_won = result == "1-0"
                agent_lost = result == "0-1"
            else:
                agent_won = result == "0-1"
                agent_lost = result == "1-0"
            
            # Process each move
            board = game.board()
            node = game
            move_number = 0
            
            while node.variations:
                move_number += 1
                next_node = node.variation[0]
                move = next_node.move
                board.push(move)
                
                # Determine if this is the agent's move
                color = "white" if board.turn == chess.BLACK else "black"
                is_agent_move = (color == agent_color)
                
                # Analyze the move
                if is_agent_move:
                    move_lessons = self._analyze_move(
                        board, move, move_number, agent_won, agent_lost
                    )
                    lessons.extend(move_lessons)
                
                node = next_node
            
            # Add game-level lessons
            game_lessons = self._extract_game_level_lessons(
                game, agent_id, agent_color, result
            )
            lessons.extend(game_lessons)
            
        except Exception as e:
            print(f"Error extracting lessons: {e}")
        
        return lessons
    
    def extract_from_memory(
        self,
        memory: MemoryEntry
    ) -> list[Lesson]:
        """
        Extract lessons from a single memory.
        
        Args:
            memory: MemoryEntry to analyze
            
        Returns:
            List of extracted Lesson objects
        """
        lessons = []
        
        try:
            board = chess.Board(memory.board_state)
            
            # Try to parse the move
            try:
                move = board.parse_uci(memory.move)
            except:
                try:
                    move = board.parse_san(memory.move)
                except:
                    return lessons
            
            # Analyze the move
            move_lessons = self._analyze_move(
                board, move, memory.move_number, False, False
            )
            lessons.extend(move_lessons)
            
        except Exception as e:
            print(f"Error extracting lessons from memory: {e}")
        
        return lessons
    
    def _analyze_move(
        self,
        board: chess.Board,
        move: chess.Move,
        move_number: int,
        agent_won: bool,
        agent_lost: bool
    ) -> list[Lesson]:
        """
        Analyze a single move for potential lessons.
        
        Args:
            board: Board state after the move
            move: The move that was made
            move_number: Move number
            agent_won: Whether the agent won the game
            agent_lost: Whether the agent lost the game
            
        Returns:
            List of Lesson objects
        """
        lessons = []
        
        try:
            # Check for blunders
            if self._is_blunder(board, move):
                lesson = Lesson(
                    agent_id="",  # Will be set by caller
                    move_number=move_number,
                    lesson_type="blunder",
                    title=f"Blunder on move {move_number}",
                    description=self._generate_blunder_description(board, move),
                    board_state=board.fen(),
                    move=move.uci(),
                    move_san=board.san(move),
                    color="white" if board.turn == chess.BLACK else "black",
                    severity="high",
                    priority=0.9,
                    tags=["blunder", "tactical", "safety"]
                )
                lessons.append(lesson)
            
            # Check for missed opportunities
            better_move = self._find_better_move(board, move)
            if better_move:
                lesson = Lesson(
                    agent_id="",
                    move_number=move_number,
                    lesson_type="missed_opportunity",
                    title=f"Missed opportunity on move {move_number}",
                    description=self._generate_opportunity_description(board, move, better_move),
                    board_state=board.fen(),
                    move=move.uci(),
                    move_san=board.san(move),
                    color="white" if board.turn == chess.BLACK else "black",
                    severity="medium",
                    priority=0.7,
                    tags=["opportunity", "tactical", "improvement"]
                )
                lessons.append(lesson)
            
            # Check for good moves
            if self._is_good_move(board, move):
                lesson = Lesson(
                    agent_id="",
                    move_number=move_number,
                    lesson_type="good_move",
                    title=f"Good move on move {move_number}",
                    description=self._generate_good_move_description(board, move),
                    board_state=board.fen(),
                    move=move.uci(),
                    move_san=board.san(move),
                    color="white" if board.turn == chess.BLACK else "black",
                    severity="low",
                    priority=0.5,
                    tags=["good_move", "positive"]
                )
                lessons.append(lesson)
            
            # Check for tactical patterns
            pattern = self._detect_tactical_pattern(board, move)
            if pattern:
                lesson = Lesson(
                    agent_id="",
                    move_number=move_number,
                    lesson_type="tactical",
                    title=f"Tactical pattern on move {move_number}: {pattern}",
                    description=self._generate_pattern_description(pattern, board, move),
                    board_state=board.fen(),
                    move=move.uci(),
                    move_san=board.san(move),
                    color="white" if board.turn == chess.BLACK else "black",
                    severity="high",
                    priority=0.8,
                    tags=["tactical", pattern, "pattern"]
                )
                lessons.append(lesson)
            
            # Check for strategic insights
            strategic = self._detect_strategic_insight(board, move)
            if strategic:
                lesson = Lesson(
                    agent_id="",
                    move_number=move_number,
                    lesson_type="strategic",
                    title=f"Strategic insight on move {move_number}",
                    description=strategic,
                    board_state=board.fen(),
                    move=move.uci(),
                    move_san=board.san(move),
                    color="white" if board.turn == chess.BLACK else "black",
                    severity="medium",
                    priority=0.6,
                    tags=["strategic", "positional"]
                )
                lessons.append(lesson)
            
        except Exception as e:
            print(f"Error analyzing move: {e}")
        
        return lessons
    
    def _extract_game_level_lessons(
        self,
        game,
        agent_id: str,
        agent_color: str,
        result: str
    ) -> list[Lesson]:
        """Extract game-level lessons."""
        lessons = []
        
        try:
            # Check for opening mistakes
            opening = game.headers.get("Opening", "")
            if opening and "?" in opening:
                lessons.append(Lesson(
                    agent_id=agent_id,
                    lesson_type="opening",
                    title="Opening error",
                    description=f"Opening played: {opening}. Consider learning standard opening theory.",
                    severity="medium",
                    priority=0.7,
                    tags=["opening", "theory"]
                ))
            
            # Check for time trouble (if move times are available)
            # This would require PGN with move times
            
            # Check for endgame mistakes
            if result != "1/2-1/2" and result != "*":
                # Game was decisive
                if (agent_color == "white" and result == "0-1") or \
                   (agent_color == "black" and result == "1-0"):
                    # Agent lost
                    lessons.append(Lesson(
                        agent_id=agent_id,
                        lesson_type="endgame",
                        title="Lost game",
                        description="Review the endgame to understand what went wrong.",
                        severity="high",
                        priority=0.8,
                        tags=["endgame", "review"]
                    ))
            
        except Exception as e:
            print(f"Error extracting game-level lessons: {e}")
        
        return lessons
    
    def _is_blunder(self, board: chess.Board, move: chess.Move) -> bool:
        """Check if a move is a blunder."""
        # Check if the moved piece is now under attack by a pawn or minor piece
        if board.is_attacked_by(not board.turn, move.to_square):
            piece = board.piece_at(move.to_square)
            if piece and piece.piece_type != chess.PAWN:
                # Piece is under attack - might be a blunder
                # Check if the attacker is a pawn or minor piece
                attackers = board.attackers(not board.turn, move.to_square)
                for attacker_sq in attackers:
                    attacker = board.piece_at(attacker_sq)
                    if attacker and attacker.piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP]:
                        return True
        
        # Check if the move leaves a piece en prise
        # (more sophisticated analysis would use evaluation)
        return False
    
    def _find_better_move(self, board: chess.Board, move: chess.Move) -> Optional[chess.Move]:
        """Find a better move than the one played."""
        # For now, just return None
        # In production, this would use evaluation
        return None
    
    def _is_good_move(self, board: chess.Board, move: chess.Move) -> bool:
        """Check if a move is particularly good."""
        # Check if the move captures a piece
        piece_at_to = board.piece_at(move.to_square)
        if piece_at_to and piece_at_to.color != board.turn:
            # Captures are generally good
            return True
        
        # Check if the move gives check
        board_copy = board.copy()
        board_copy.push(move)
        if board_copy.is_check():
            return True
        
        # Check if the move develops a piece
        if move.from_square in [
            chess.A1, chess.B1, chess.C1, chess.F1, chess.G1, chess.H1,
            chess.A8, chess.B8, chess.C8, chess.F8, chess.G8, chess.H8
        ]:
            # Moving a back-rank piece
            piece = board.piece_at(move.from_square)
            if piece and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                return True
        
        return False
    
    def _detect_tactical_pattern(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> Optional[str]:
        """Detect tactical patterns in a move."""
        # Check for fork
        attacked_squares = []
        for square in chess.SQUARES:
            if board.is_attacked_by(board.turn, square):
                attacked_squares.append(square)
        
        # Check if the move creates a fork
        piece = board.piece_at(move.to_square)
        if piece and piece.color == board.turn:
            # Count how many enemy pieces this piece attacks
            enemy_attacked = 0
            for square in chess.SQUARES:
                square_piece = board.piece_at(square)
                if square_piece and square_piece.color != board.turn:
                    if board.is_attacked_by(board.turn, square):
                        enemy_attacked += 1
            
            if enemy_attacked >= 2:
                return "fork"
        
        # Check for pin
        if board.is_pinned(not board.turn, move.to_square):
            return "pin"
        
        # Check for skewer
        # (simplified detection)
        
        # Check for discovered attack
        # (simplified detection)
        
        return None
    
    def _detect_strategic_insight(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> Optional[str]:
        """Detect strategic insights from a move."""
        # Check for central control
        center_squares = [chess.D4, chess.E4, chess.D5, chess.E5]
        if move.to_square in center_squares:
            return "Move controls the center"
        
        # Check for king safety
        if board.turn == chess.WHITE:
            king_square = board.king(chess.WHITE)
        else:
            king_square = board.king(chess.BLACK)
        
        # Check if move improves king safety
        # (simplified)
        
        # Check for pawn structure improvement
        if board.piece_at(move.from_square) and \
           board.piece_at(move.from_square).piece_type == chess.PAWN:
            # Pawn move
            if move.to_square == move.from_square:
                return "Pawn push improves position"
        
        return None
    
    def _generate_blunder_description(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> str:
        """Generate description for a blunder."""
        piece = board.piece_at(move.to_square)
        if piece:
            attackers = board.attackers(not board.turn, move.to_square)
            if attackers:
                attacker = board.piece_at(attackers[0])
                if attacker:
                    return (f"Moving {piece.symbol()} to {chess.square_name(move.to_square)} "
                            f"where it's attacked by {attacker.symbol()} on "
                            f"{chess.square_name(attackers[0])}")
        
        return "Leaving a piece under attack"
    
    def _generate_opportunity_description(
        self,
        board: chess.Board,
        move: chess.Move,
        better_move: chess.Move
    ) -> str:
        """Generate description for a missed opportunity."""
        return (f"Consider {board.san(better_move)} instead of {board.san(move)}. "
                f"{board.san(better_move)} would have been stronger in this position.")
    
    def _generate_good_move_description(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> str:
        """Generate description for a good move."""
        piece_at_to = board.piece_at(move.to_square)
        if piece_at_to and piece_at_to.color != board.turn:
            return f"Good capture: {board.san(move)} wins {piece_at_to.symbol()}"
        
        board_copy = board.copy()
        board_copy.push(move)
        if board_copy.is_check():
            return f"Good check: {board.san(move)} puts opponent in check"
        
        # Check for development
        if move.from_square in [
            chess.A1, chess.B1, chess.C1, chess.F1, chess.G1, chess.H1,
            chess.A8, chess.B8, chess.C8, chess.F8, chess.G8, chess.H8
        ]:
            piece = board.piece_at(move.from_square)
            if piece and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                return f"Good development: {board.san(move)} develops {piece.symbol()}"
        
        return f"Good move: {board.san(move)}"
    
    def _generate_pattern_description(
        self,
        pattern: str,
        board: chess.Board,
        move: chess.Move
    ) -> str:
        """Generate description for a tactical pattern."""
        descriptions = {
            "fork": f"Fork pattern: {board.san(move)} attacks multiple pieces",
            "pin": f"Pin pattern: {board.san(move)} pins an opponent piece",
            "skewer": f"Skewer pattern: {board.san(move)} creates a skewer",
            "discovered_attack": f"Discovered attack: {board.san(move)} reveals an attack"
        }
        
        return descriptions.get(pattern, f"Tactical pattern: {pattern}")


class LearningSystem:
    """
    Complete learning system for chess agents.
    
    This class coordinates all learning activities:
    - Lesson extraction
    - Skill development
    - Performance tracking
    - Adaptive learning strategies
    
    Usage:
        learning_system = LearningSystem()
        
        # After a game
        learning_system.learn_from_game(pgn, agent_id, agent_color, result)
        
        # Get learning statistics
        stats = learning_system.get_stats(agent_id)
    """
    
    def __init__(self):
        self._lesson_extractor = LessonExtractor()
        self._memory_manager = get_memory_manager()
        self._skill_extractor = get_skill_extractor()
        self._lock = threading.RLock()
    
    def learn_from_game(
        self,
        pgn: str,
        agent_id: str,
        agent_color: str = "white",
        result: Optional[str] = None
    ) -> dict:
        """
        Learn from a completed game.
        
        This method:
        1. Extracts lessons from the game
        2. Saves lessons to memory
        3. Develops new skills from the lessons
        4. Updates performance metrics
        
        Args:
            pgn: Game in PGN format
            agent_id: ID of the agent
            agent_color: Color the agent was playing
            result: Game result (optional, extracted from PGN if not provided)
            
        Returns:
            Dictionary with learning results:
                - lessons_extracted: Number of lessons extracted
                - skills_developed: Number of new skills developed
                - memories_saved: Number of memories saved
                - performance_update: Performance metrics update
        """
        with self._lock:
            # Extract lessons
            lessons = self._lesson_extractor.extract_from_pgn(
                pgn, agent_id, agent_color
            )
            
            # Save lessons to memory
            memories_saved = 0
            for lesson in lessons:
                lesson.agent_id = agent_id
                memory_id = self._memory_manager.save(
                    agent_id=agent_id,
                    board_state=lesson.board_state,
                    move=lesson.move,
                    reasoning=lesson.description,
                    game_id="",  # Would be set in actual game
                    move_number=lesson.move_number,
                    color=lesson.color,
                    confidence=0.5,
                    outcome="win" if (agent_color == "white" and result == "1-0") or \
                              (agent_color == "black" and result == "0-1") else \
                              "loss" if (agent_color == "white" and result == "0-1") or \
                                       (agent_color == "black" and result == "1-0") else "draw",
                    lessons=[lesson.description],
                    tags=lesson.tags + ["lesson", f"lesson-{lesson.lesson_type}"]
                )
                memories_saved += 1
            
            # Develop skills from lessons
            skills_developed = 0
            skill_manager = SkillManager(agent_id)
            
            # Group lessons by type
            for lesson_type in ["opening", "tactic", "endgame", "pattern"]:
                type_lessons = [l for l in lessons if l.lesson_type == lesson_type]
                if type_lessons:
                    # For now, just develop one skill per type
                    # In production, would cluster lessons
                    skill = self._create_skill_from_lessons(
                        type_lessons, lesson_type, agent_id
                    )
                    if skill:
                        skill_manager.save(skill)
                        skills_developed += 1
            
            # Update performance metrics
            performance_update = self._update_performance(
                agent_id, pgn, result, agent_color
            )
            
            return {
                "lessons_extracted": len(lessons),
                "skills_developed": skills_developed,
                "memories_saved": memories_saved,
                "performance_update": performance_update
            }
    
    def _create_skill_from_lessons(
        self,
        lessons: list[Lesson],
        skill_type: str,
        agent_id: str
    ) -> Optional[AgentSkill]:
        """Create a skill from a set of lessons."""
        if not lessons:
            return None
        
        # Create a skill based on the lessons
        if skill_type == "opening":
            # Extract common opening moves
            moves = []
            for lesson in lessons:
                try:
                    board = chess.Board(lesson.board_state)
                    move_stack = list(board.move_stack)
                    if len(move_stack) > len(moves):
                        moves = [m.uci() for m in move_stack]
                except:
                    pass
            
            if moves:
                return AgentSkill(
                    agent_id=agent_id,
                    name=f"Opening: {lessons[0].title}",
                    skill_type="opening",
                    description=lessons[0].description,
                    data={"moves": moves},
                    tags=["opening"] + lessons[0].tags
                )
        
        elif skill_type == "tactic":
            # Create a tactical skill
            return AgentSkill(
                agent_id=agent_id,
                name=f"Tactic: {lessons[0].title}",
                skill_type="tactic",
                description=lessons[0].description,
                data={"pattern": lessons[0].lesson_type},
                tags=["tactic"] + lessons[0].tags
            )
        
        elif skill_type == "endgame":
            # Create an endgame skill
            return AgentSkill(
                agent_id=agent_id,
                name=f"Endgame: {lessons[0].title}",
                skill_type="endgame",
                description=lessons[0].description,
                data={"type": "basic_endgame"},
                tags=["endgame"] + lessons[0].tags
            )
        
        elif skill_type == "pattern":
            # Create a pattern skill
            return AgentSkill(
                agent_id=agent_id,
                name=f"Pattern: {lessons[0].title}",
                skill_type="pattern",
                description=lessons[0].description,
                data={"pattern": lessons[0].lesson_type},
                tags=["pattern"] + lessons[0].tags
            )
        
        return None
    
    def _update_performance(
        self,
        agent_id: str,
        pgn: str,
        result: Optional[str],
        agent_color: str
    ) -> dict:
        """Update performance metrics for an agent."""
        # This would track various performance metrics
        # For now, just return a simple update
        
        return {
            "agent_id": agent_id,
            "metrics_updated": ["games_played"],
            "new_rating": 1200  # Would calculate actual rating
        }
    
    def get_stats(self, agent_id: str) -> dict:
        """
        Get learning statistics for an agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Dictionary with learning statistics
        """
        with self._lock:
            # Get memory count
            memories = self._memory_manager.query(agent_id=agent_id)
            memory_count = len(memories)
            
            # Get skill count
            skill_manager = SkillManager(agent_id)
            skills = skill_manager.list_skills()
            skill_count = len(skills)
            
            # Get lesson count
            lesson_count = sum(
                len(m.lessons) for m in memories
            )
            
            # Calculate average confidence
            if memories:
                avg_confidence = sum(m.confidence for m in memories) / len(memories)
            else:
                avg_confidence = 0.0
            
            return {
                "agent_id": agent_id,
                "memories_count": memory_count,
                "skills_count": skill_count,
                "lessons_count": lesson_count,
                "average_confidence": avg_confidence,
                "last_activity": memories[0].timestamp if memories else None
            }
    
    def get_recommendations(self, agent_id: str, limit: int = 5) -> list[dict]:
        """
        Get learning recommendations for an agent.
        
        Args:
            agent_id: ID of the agent
            limit: Maximum number of recommendations
            
        Returns:
            List of recommendation dictionaries
        """
        with self._lock:
            # Get agent's weaknesses
            memories = self._memory_manager.query(agent_id=agent_id)
            
            # Count lessons by type
            lesson_types = {}
            for memory in memories:
                for lesson in memory.lessons:
                    # Extract lesson type from tags or content
                    lesson_type = "general"
                    if "blunder" in lesson.lower():
                        lesson_type = "blunder"
                    elif "opportunity" in lesson.lower():
                        lesson_type = "opportunity"
                    elif "tactical" in lesson.lower():
                        lesson_type = "tactical"
                    elif "strategic" in lesson.lower():
                        lesson_type = "strategic"
                    
                    lesson_types[lesson_type] = lesson_types.get(lesson_type, 0) + 1
            
            # Generate recommendations based on weaknesses
            recommendations = []
            
            # Sort by count (descending)
            sorted_types = sorted(lesson_types.items(), key=lambda x: x[1], reverse=True)
            
            for lesson_type, count in sorted_types[:limit]:
                if lesson_type == "blunder":
                    recommendations.append({
                        "type": "study",
                        "topic": "Tactical awareness",
                        "description": f"You've made {count} blunders. Study tactical patterns to avoid leaving pieces en prise.",
                        "priority": "high",
                        "resources": [
                            "https://lichess.org/learn#tactics",
                            "https://www.chess.com/lessons"
                        ]
                    })
                elif lesson_type == "opportunity":
                    recommendations.append({
                        "type": "study",
                        "topic": "Tactical vision",
                        "description": f"You've missed {count} opportunities. Practice calculating variations to see better moves.",
                        "priority": "high",
                        "resources": [
                            "https://lichess.org/training/puzzles",
                            "https://www.chess.com/puzzles"
                        ]
                    })
                elif lesson_type == "tactical":
                    recommendations.append({
                        "type": "practice",
                        "topic": "Tactical patterns",
                        "description": f"You've encountered {count} tactical situations. Practice recognizing common patterns.",
                        "priority": "medium",
                        "resources": [
                            "https://lichess.org/training/puzzles",
                            "https://www.chess.com/puzzles"
                        ]
                    })
                elif lesson_type == "strategic":
                    recommendations.append({
                        "type": "study",
                        "topic": "Strategic planning",
                        "description": f"You've made {count} strategic moves. Study positional chess to improve planning.",
                        "priority": "medium",
                        "resources": [
                            "https://lichess.org/learn#strategy",
                            "https://www.chess.com/article/view/strategic-chess"
                        ]
                    })
            
            # Add general recommendations
            if len(recommendations) < limit:
                recommendations.append({
                    "type": "play",
                    "topic": "More games",
                    "description": "Play more games to gain experience and improve your skills.",
                    "priority": "medium",
                    "resources": []
                })
            
            if len(recommendations) < limit:
                recommendations.append({
                    "type": "analyze",
                    "topic": "Game review",
                    "description": "Review your completed games to understand your mistakes and successes.",
                    "priority": "medium",
                    "resources": []
                })
            
            return recommendations[:limit]
    
    def review_memory(
        self,
        memory_id: str,
        agent_id: str,
        feedback: Optional[str] = None
    ) -> bool:
        """
        Review a memory and update its priority.
        
        Args:
            memory_id: ID of the memory to review
            agent_id: ID of the agent
            feedback: Optional feedback on the memory
            
        Returns:
            True if memory was updated
        """
        with self._lock:
            memory_manager = get_memory_manager()
            memory = memory_manager.get(memory_id)
            
            if not memory or memory.agent_id != agent_id:
                return False
            
            # Update memory
            memory.last_reviewed = datetime.now().isoformat()
            memory.review_count += 1
            
            # Adjust priority based on feedback
            if feedback:
                # Simple sentiment analysis
                if any(word in feedback.lower() for word in ["useful", "helpful", "good", "great"]):
                    memory.priority = min(1.0, memory.priority + 0.1)
                elif any(word in feedback.lower() for word in ["useless", "bad", "wrong", "incorrect"]):
                    memory.priority = max(0.0, memory.priority - 0.2)
            
            # Save updated memory
            memory_manager.get_memory(agent_id)._save_to_sqlite(memory)
            
            return True


# ============================================================================
# Global Instance
# ============================================================================

_learning_system: Optional[LearningSystem] = None


def get_learning_system() -> LearningSystem:
    """Get the global learning system instance."""
    global _learning_system
    if _learning_system is None:
        _learning_system = LearningSystem()
    return _learning_system


def reset_learning_system():
    """Reset the global learning system (for testing)."""
    global _learning_system
    _learning_system = None


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "Lesson",
    "PerformanceMetric",
    "LessonExtractor",
    "LearningSystem",
    "get_learning_system",
    "reset_learning_system"
]
