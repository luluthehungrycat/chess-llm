"""
Agent Skills System - Skill development and application for chess agents.

This module provides a system for agents to develop, store, and apply
learned chess skills. Skills are extracted from agent memories and can
be reused in future games.
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


@dataclass
class AgentSkill:
    """A learned chess skill for an agent."""
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    name: str = ""
    skill_type: str = ""  # "opening", "tactic", "endgame", "pattern", "strategy"
    description: str = ""
    
    # Skill data (type-specific)
    data: dict = field(default_factory=dict)
    
    # Performance metrics
    success_rate: float = 0.0
    usage_count: int = 0
    last_used: Optional[str] = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentSkill":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "AgentSkill":
        return cls.from_dict(json.loads(json_str))


class SkillManager:
    """
    Manager for agent skills.
    
    Provides storage, retrieval, and application of skills for agents.
    Skills are organized by type and can be queried based on game context.
    
    Usage:
        skill_manager = SkillManager("hermes-agent")
        
        # Create and save a skill
        skill = AgentSkill(
            agent_id="hermes-agent",
            name="Italian Game",
            skill_type="opening",
            description="Response to 1. e4 e5 with 2. Nf3 Nc6 3. Bc4",
            data={"moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]}
        )
        skill_manager.save(skill)
        
        # Find applicable skills
        board = chess.Board()
        applicable = skill_manager.find_applicable(board, "white")
    """
    
    def __init__(
        self,
        agent_id: str,
        storage_path: str = "agents",
        use_sqlite: bool = True
    ):
        """
        Initialize skill manager for an agent.
        
        Args:
            agent_id: ID of the agent
            storage_path: Path for storage
            use_sqlite: Whether to use SQLite
        """
        self.agent_id = agent_id
        self.storage_path = Path(storage_path)
        self.use_sqlite = use_sqlite
        self._skills: dict[str, AgentSkill] = {}
        self._lock = threading.RLock()
        
        # Initialize storage
        if use_sqlite:
            self._db_path = self.storage_path / "agents.db"
            self._init_sqlite()
        else:
            self._skills_dir = self.storage_path / agent_id / "skills"
            self._skills_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_files()
    
    def _init_sqlite(self):
        """Initialize SQLite database."""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                skill_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                name TEXT NOT NULL,
                skill_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                data TEXT DEFAULT '{}',
                success_rate REAL DEFAULT 0.0,
                usage_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_skills_agent ON skills(agent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_skills_type ON skills(skill_type)
        """)
        
        self._conn.commit()
        self._load_from_sqlite()
    
    def _load_from_sqlite(self):
        """Load skills from SQLite."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM skills WHERE agent_id = ?", (self.agent_id,))
        
        for row in cursor.fetchall():
            skill = AgentSkill(
                skill_id=row["skill_id"],
                agent_id=row["agent_id"],
                name=row["name"],
                skill_type=row["skill_type"],
                description=row["description"],
                data=json.loads(row["data"]),
                success_rate=row["success_rate"],
                usage_count=row["usage_count"],
                last_used=row["last_used"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                tags=json.loads(row["tags"])
            )
            self._skills[skill.skill_id] = skill
    
    def _load_from_files(self):
        """Load skills from JSON files."""
        if self._skills_dir.exists():
            for skill_file in self._skills_dir.glob("*.json"):
                with open(skill_file) as f:
                    data = json.load(f)
                    skill = AgentSkill.from_dict(data)
                    self._skills[skill.skill_id] = skill
    
    def _save_to_sqlite(self, skill: AgentSkill):
        """Save a skill to SQLite."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO skills VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            skill.skill_id,
            skill.agent_id,
            skill.name,
            skill.skill_type,
            skill.description,
            json.dumps(skill.data),
            skill.success_rate,
            skill.usage_count,
            skill.last_used,
            skill.created_at,
            skill.updated_at,
            json.dumps(skill.tags)
        ))
        self._conn.commit()
    
    def _save_to_file(self, skill: AgentSkill):
        """Save a skill to JSON file."""
        skill_file = self._skills_dir / f"{skill.skill_id}.json"
        with open(skill_file, "w") as f:
            json.dump(skill.to_dict(), f, indent=2)
    
    def save(self, skill: AgentSkill) -> str:
        """
        Save a skill.
        
        Args:
            skill: AgentSkill to save
            
        Returns:
            The skill_id of the saved skill
        """
        with self._lock:
            # Ensure skill has required fields
            skill.agent_id = self.agent_id
            if not skill.skill_id:
                skill.skill_id = str(uuid.uuid4())
            if not skill.created_at:
                skill.created_at = datetime.now().isoformat()
            skill.updated_at = datetime.now().isoformat()
            
            self._skills[skill.skill_id] = skill
            
            # Persist
            if self.use_sqlite:
                self._save_to_sqlite(skill)
            else:
                self._save_to_file(skill)
            
            return skill.skill_id
    
    def get(self, skill_id: str) -> Optional[AgentSkill]:
        """Get a skill by ID."""
        with self._lock:
            return self._skills.get(skill_id)
    
    def delete(self, skill_id: str) -> bool:
        """Delete a skill by ID."""
        with self._lock:
            if skill_id not in self._skills:
                return False
            
            del self._skills[skill_id]
            
            if self.use_sqlite:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM skills WHERE skill_id = ?",
                    (skill_id,)
                )
                self._conn.commit()
            else:
                skill_file = self._skills_dir / f"{skill_id}.json"
                if skill_file.exists():
                    skill_file.unlink()
            
            return True
    
    def list_skills(
        self,
        skill_type: Optional[str] = None,
        tag: Optional[str] = None
    ) -> list[AgentSkill]:
        """
        List all skills for this agent.
        
        Args:
            skill_type: Filter by skill type
            tag: Filter by tag
            
        Returns:
            List of AgentSkill objects
        """
        with self._lock:
            skills = list(self._skills.values())
            
            if skill_type:
                skills = [s for s in skills if s.skill_type == skill_type]
            if tag:
                skills = [s for s in skills if tag in s.tags]
            
            return skills
    
    def find_applicable(
        self,
        board: chess.Board,
        color: str,
        phase: Optional[str] = None
    ) -> list[tuple[AgentSkill, float]]:
        """
        Find skills applicable to the current board position.
        
        Args:
            board: Current board state
            color: Color to move ("white" or "black")
            phase: Game phase ("opening", "middlegame", "endgame")
            
        Returns:
            List of (skill, relevance_score) tuples
        """
        with self._lock:
            results = []
            
            for skill in self._skills.values():
                relevance = self._calculate_relevance(skill, board, color, phase)
                if relevance > 0:
                    results.append((skill, relevance))
            
            # Sort by relevance (descending)
            results.sort(key=lambda x: x[1], reverse=True)
            return results
    
    def _calculate_relevance(
        self,
        skill: AgentSkill,
        board: chess.Board,
        color: str,
        phase: Optional[str]
    ) -> float:
        """
        Calculate how relevant a skill is to the current position.
        
        Args:
            skill: The skill to evaluate
            board: Current board state
            color: Color to move
            phase: Current game phase
            
        Returns:
            Relevance score (0.0-1.0)
        """
        score = 0.0
        
        # Phase matching
        if phase and skill.skill_type == phase:
            score += 0.4
        elif skill.skill_type in ["opening", "middlegame", "endgame"]:
            # Penalize if phase doesn't match
            if phase and skill.skill_type != phase:
                return 0.0
        
        # Type-specific matching
        if skill.skill_type == "opening":
            # Check if we're in the opening phase
            move_count = len(list(board.move_stack))
            if move_count < 10:  # First 10 moves are opening
                # Check if the skill's opening moves match
                skill_moves = skill.data.get("moves", [])
                if skill_moves:
                    board_moves = [m.uci() for m in board.move_stack]
                    # Check if the skill's moves are a prefix of the game
                    if board_moves[:len(skill_moves)] == skill_moves[:len(board_moves)]:
                        score += 0.6
                    else:
                        # Partial match
                        matches = sum(
                            1 for sm, bm in zip(skill_moves, board_moves)
                            if sm == bm
                        )
                        score += 0.3 * (matches / max(len(skill_moves), 1))
            else:
                return 0.0
                
        elif skill.skill_type == "tactic":
            # Check if the tactical pattern exists on the board
            pattern = skill.data.get("pattern")
            if pattern:
                if self._pattern_exists(board, pattern):
                    score += 0.7
                else:
                    return 0.0
            else:
                score += 0.3  # Generic tactic
                
        elif skill.skill_type == "endgame":
            # Check if we're in endgame
            if self._is_endgame(board):
                score += 0.5
            else:
                return 0.0
                
        elif skill.skill_type == "pattern":
            # Check if the pattern exists
            pattern = skill.data.get("pattern")
            if pattern and self._pattern_exists(board, pattern):
                score += 0.8
            else:
                return 0.0
        
        # Color matching
        skill_color = skill.data.get("color")
        if skill_color and skill_color != color:
            score *= 0.5  # Reduce score if color doesn't match
        
        # Success rate bonus
        score += skill.success_rate * 0.1
        
        # Usage count bonus (more used = more reliable)
        if skill.usage_count > 10:
            score += 0.1
        elif skill.usage_count > 5:
            score += 0.05
        
        return min(score, 1.0)
    
    def _pattern_exists(self, board: chess.Board, pattern: dict) -> bool:
        """
        Check if a tactical pattern exists on the board.
        
        Args:
            board: Current board state
            pattern: Pattern definition
            
        Returns:
            True if pattern exists
        """
        # Pattern format:
        # {
        #   "type": "fork" | "pin" | "skewer" | "discovered_attack",
        #   "piece": "N" | "B" | "R" | "Q" | "K",
        #   "targets": ["square1", "square2"],
        #   "squares": ["square1", "square2"]
        # }
        
        pattern_type = pattern.get("type")
        piece = pattern.get("piece", "").upper()
        targets = pattern.get("targets", [])
        squares = pattern.get("squares", [])
        
        if pattern_type == "fork":
            # Check if a piece attacks multiple targets
            for square_name in squares:
                try:
                    square = chess.parse_square(square_name)
                    piece_on_square = board.piece_at(square)
                    if piece_on_square and piece_on_square.symbol().upper() == piece:
                        # Check if this piece attacks the targets
                        attackers = board.attackers(chess.WHITE if piece_on_square.color == chess.WHITE else chess.BLACK, square)
                        # Simplified: check if piece attacks target squares
                        attacked = 0
                        for target in targets:
                            try:
                                target_sq = chess.parse_square(target)
                                if board.is_attacked_by(piece_on_square.color, target_sq):
                                    attacked += 1
                            except:
                                pass
                        if attacked >= 2:
                            return True
                except:
                    pass
                    
        elif pattern_type == "pin":
            # Check if a piece is pinned
            for square_name in squares:
                try:
                    square = chess.parse_square(square_name)
                    piece_on_square = board.piece_at(square)
                    if piece_on_square and piece_on_square.symbol().upper() == piece:
                        # Check if piece is pinned
                        if board.is_pinned(chess.WHITE if piece_on_square.color == chess.WHITE else chess.BLACK, square):
                            return True
                except:
                    pass
                    
        # Add more pattern types as needed
        
        return False
    
    def _is_endgame(self, board: chess.Board) -> bool:
        """Check if the position is an endgame."""
        # Simple heuristic: few pieces remaining
        piece_count = len(board.piece_map())
        
        # Also check for endgame material
        queens = len([p for p in board.piece_map().values() if p.piece_type == chess.QUEEN])
        rooks = len([p for p in board.piece_map().values() if p.piece_type == chess.ROOK])
        
        # Endgame if:
        # - Less than 10 pieces total, OR
        # - No queens and less than 15 pieces, OR
        # - Only kings and pawns
        if piece_count <= 10:
            return True
        if queens == 0 and piece_count <= 15:
            return True
        
        # Check for K+P vs K+P endgames
        white_pieces = [p for p in board.piece_map().values() if p.color == chess.WHITE]
        black_pieces = [p for p in board.piece_map().values() if p.color == chess.BLACK]
        
        if len(white_pieces) <= 2 and len(black_pieces) <= 2:
            return True
        
        return False
    
    def apply_skill(
        self,
        skill: AgentSkill,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """
        Apply a skill to generate a move.
        
        Args:
            skill: The skill to apply
            board: Current board state
            color: Color to move
            
        Returns:
            A chess.Move if the skill can generate one, None otherwise
        """
        with self._lock:
            # Update usage stats
            skill.usage_count += 1
            skill.last_used = datetime.now().isoformat()
            skill.updated_at = datetime.now().isoformat()
            
            # Save updated skill
            if self.use_sqlite:
                self._save_to_sqlite(skill)
            else:
                self._save_to_file(skill)
            
            # Apply skill based on type
            if skill.skill_type == "opening":
                return self._apply_opening_skill(skill, board, color)
            elif skill.skill_type == "tactic":
                return self._apply_tactic_skill(skill, board, color)
            elif skill.skill_type == "endgame":
                return self._apply_endgame_skill(skill, board, color)
            elif skill.skill_type == "pattern":
                return self._apply_pattern_skill(skill, board, color)
            
            return None
    
    def _apply_opening_skill(
        self,
        skill: AgentSkill,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply an opening skill."""
        moves = skill.data.get("moves", [])
        if not moves:
            return None
        
        # Find the next move in the opening sequence
        board_moves = [m.uci() for m in board.move_stack]
        
        # Find where we are in the sequence
        for i, skill_move in enumerate(moves):
            if i >= len(board_moves):
                # This is the next move
                try:
                    return board.parse_uci(skill_move)
                except:
                    return None
            elif skill_move != board_moves[i]:
                # Sequence doesn't match
                return None
        
        # If we've matched all moves in the skill, return None (opening complete)
        return None
    
    def _apply_tactic_skill(
        self,
        skill: AgentSkill,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply a tactic skill."""
        # Tactic skills typically specify a target square or piece
        target_square = skill.data.get("target_square")
        target_piece = skill.data.get("target_piece")
        
        if target_square:
            try:
                square = chess.parse_square(target_square)
                # Find moves to this square
                for move in board.legal_moves:
                    if move.to_square == square:
                        return move
            except:
                pass
        
        if target_piece:
            # Find moves that capture the target piece
            for move in board.legal_moves:
                piece_at_to = board.piece_at(move.to_square)
                if piece_at_to and piece_at_to.symbol().upper() == target_piece.upper():
                    return move
        
        # Fallback: return the first legal move
        if board.legal_moves:
            return list(board.legal_moves)[0]
        
        return None
    
    def _apply_endgame_skill(
        self,
        skill: AgentSkill,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply an endgame skill."""
        # Endgame skills are more complex and may require tablebase lookups
        # For now, implement basic endgame patterns
        
        endgame_type = skill.data.get("type")
        
        if endgame_type == "kq_vs_k":
            # King + Queen vs King
            return self._apply_kq_vs_k(board, color)
        elif endgame_type == "kr_vs_k":
            # King + Rook vs King
            return self._apply_kr_vs_k(board, color)
        elif endgame_type == "kp_vs_k":
            # King + Pawn vs King
            return self._apply_kp_vs_k(board, color)
        
        # Fallback
        if board.legal_moves:
            return list(board.legal_moves)[0]
        
        return None
    
    def _apply_kq_vs_k(
        self,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply King + Queen vs King endgame skill."""
        # Simple strategy: drive the enemy king to the edge
        enemy_king_square = board.king(not board.turn)
        
        # Find moves that reduce the enemy king's mobility
        best_move = None
        best_distance = float('inf')
        
        for move in board.legal_moves:
            board_copy = board.copy()
            board_copy.push(move)
            
            new_enemy_king_square = board_copy.king(not board.turn)
            
            # Calculate distance to edge
            file = chess.square_file(new_enemy_king_square)
            rank = chess.square_rank(new_enemy_king_square)
            distance_to_edge = min(file, 7 - file, rank, 7 - rank)
            
            if distance_to_edge < best_distance:
                best_distance = distance_to_edge
                best_move = move
        
        return best_move
    
    def _apply_kr_vs_k(
        self,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply King + Rook vs King endgame skill."""
        # Simple strategy: use rook to cut off enemy king
        if board.legal_moves:
            # Prefer rook moves
            for move in board.legal_moves:
                piece = board.piece_at(move.from_square)
                if piece and piece.piece_type == chess.ROOK:
                    return move
            
            # Fallback to any move
            return list(board.legal_moves)[0]
        
        return None
    
    def _apply_kp_vs_k(
        self,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply King + Pawn vs King endgame skill."""
        # Simple strategy: advance the pawn
        for move in board.legal_moves:
            piece = board.piece_at(move.from_square)
            if piece and piece.piece_type == chess.PAWN:
                # Prefer pawn advances
                if chess.square_rank(move.to_square) > chess.square_rank(move.from_square):
                    return move
        
        # Fallback
        if board.legal_moves:
            return list(board.legal_moves)[0]
        
        return None
    
    def _apply_pattern_skill(
        self,
        skill: AgentSkill,
        board: chess.Board,
        color: str
    ) -> Optional[chess.Move]:
        """Apply a pattern skill."""
        # Pattern skills specify a move to make when the pattern is detected
        move_uci = skill.data.get("move")
        if move_uci:
            try:
                return board.parse_uci(move_uci)
            except:
                pass
        
        # Fallback
        if board.legal_moves:
            return list(board.legal_moves)[0]
        
        return None
    
    def update_success(self, skill_id: str, success: bool):
        """
        Update a skill's success rate based on move outcome.
        
        Args:
            skill_id: ID of the skill
            success: Whether the move was successful
        """
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                return
            
            # Update success rate using exponential moving average
            alpha = 0.1  # Learning rate
            if success:
                new_rate = skill.success_rate + alpha * (1.0 - skill.success_rate)
            else:
                new_rate = skill.success_rate + alpha * (0.0 - skill.success_rate)
            
            skill.success_rate = new_rate
            skill.updated_at = datetime.now().isoformat()
            
            # Persist
            if self.use_sqlite:
                self._save_to_sqlite(skill)
            else:
                self._save_to_file(skill)
    
    def clear(self):
        """Clear all skills for this agent."""
        with self._lock:
            self._skills.clear()
            
            if self.use_sqlite:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM skills WHERE agent_id = ?",
                    (self.agent_id,)
                )
                self._conn.commit()
            else:
                if self._skills_dir.exists():
                    import shutil
                    shutil.rmtree(self._skills_dir)
                    self._skills_dir.mkdir(parents=True, exist_ok=True)
    
    def close(self):
        """Close the skill manager."""
        if self.use_sqlite and hasattr(self, "_conn"):
            self._conn.close()


class SkillExtractor:
    """
    Extract skills from agent memories.
    
    Analyzes agent memories to identify patterns and create reusable skills.
    """
    
    def __init__(self):
        self._pattern_database = self._load_pattern_database()
    
    def _load_pattern_database(self) -> dict:
        """Load the tactical pattern database."""
        # This would be a comprehensive database of chess patterns
        # For now, return a simple set of patterns
        return {
            "forks": [
                {"name": "Knight Fork", "piece": "N", "targets": ["K", "Q"]},
                {"name": "Bishop Fork", "piece": "B", "targets": ["K", "R"]},
                {"name": "Queen Fork", "piece": "Q", "targets": ["K", "R"]},
            ],
            "pins": [
                {"name": "Absolute Pin", "piece": "B", "pinned_piece": "N", "king_square": "e8"},
            ],
            "openings": [
                {
                    "name": "Italian Game",
                    "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"],
                    "eco": "C50"
                },
                {
                    "name": "Ruy Lopez",
                    "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"],
                    "eco": "C60"
                },
            ],
            "endgames": [
                {"name": "K+Q vs K", "type": "kq_vs_k"},
                {"name": "K+R vs K", "type": "kr_vs_k"},
                {"name": "K+P vs K", "type": "kp_vs_k"},
            ]
        }
    
    def extract_from_memory(self, memory: "MemoryEntry") -> list[AgentSkill]:
        """
        Extract potential skills from a memory.
        
        Args:
            memory: MemoryEntry to analyze
            
        Returns:
            List of extracted AgentSkill objects
        """
        skills = []
        
        # Try to extract opening skills
        skills.extend(self._extract_opening_skills(memory))
        
        # Try to extract tactic skills
        skills.extend(self._extract_tactic_skills(memory))
        
        # Try to extract endgame skills
        skills.extend(self._extract_endgame_skills(memory))
        
        return skills
    
    def _extract_opening_skills(self, memory: "MemoryEntry") -> list[AgentSkill]:
        """Extract opening skills from a memory."""
        skills = []
        
        # Check if this is an opening move (early in the game)
        if memory.move_number < 15:
            # Check if the move sequence matches any known opening
            board = chess.Board(memory.board_state)
            moves = [m.uci() for m in board.move_stack]
            
            for opening in self._pattern_database.get("openings", []):
                opening_moves = opening.get("moves", [])
                
                # Check if the current position matches the opening
                if moves[:len(opening_moves)] == opening_moves[:len(moves)]:
                    # Create a skill for this opening
                    skill = AgentSkill(
                        agent_id=memory.agent_id,
                        name=opening.get("name", "Unknown Opening"),
                        skill_type="opening",
                        description=f"Opening: {opening.get('name', 'Unknown')} (ECO: {opening.get('eco', '???')})",
                        data={
                            "moves": opening_moves,
                            "eco": opening.get("eco", "???"),
                            "name": opening.get("name", "Unknown")
                        },
                        tags=["opening", opening.get("eco", "???")]
                    )
                    skills.append(skill)
                    break
        
        return skills
    
    def _extract_tactic_skills(self, memory: "MemoryEntry") -> list[AgentSkill]:
        """Extract tactic skills from a memory."""
        skills = []
        
        # Analyze the board position for tactical patterns
        try:
            board = chess.Board(memory.board_state)
            
            # Check for forks
            for fork in self._pattern_database.get("forks", []):
                if self._detect_fork(board, fork):
                    skill = AgentSkill(
                        agent_id=memory.agent_id,
                        name=fork.get("name", "Fork"),
                        skill_type="tactic",
                        description=f"Fork pattern: {fork.get('piece', '?')} forking {', '.join(fork.get('targets', []))}",
                        data={
                            "type": "fork",
                            "piece": fork.get("piece", "?"),
                            "targets": fork.get("targets", []),
                            "pattern": fork
                        },
                        tags=["tactic", "fork", fork.get("piece", "?")]
                    )
                    skills.append(skill)
            
            # Check for pins
            for pin in self._pattern_database.get("pins", []):
                if self._detect_pin(board, pin):
                    skill = AgentSkill(
                        agent_id=memory.agent_id,
                        name=pin.get("name", "Pin"),
                        skill_type="tactic",
                        description=f"Pin pattern: {pin.get('piece', '?')} pinning {pin.get('pinned_piece', '?')}",
                        data={
                            "type": "pin",
                            "piece": pin.get("piece", "?"),
                            "pinned_piece": pin.get("pinned_piece", "?"),
                            "pattern": pin
                        },
                        tags=["tactic", "pin", pin.get("piece", "?")]
                    )
                    skills.append(skill)
        
        except Exception as e:
            # Failed to analyze, skip
            pass
        
        return skills
    
    def _detect_fork(self, board: chess.Board, fork: dict) -> bool:
        """Detect if a fork pattern exists on the board."""
        piece = fork.get("piece", "").upper()
        targets = fork.get("targets", [])
        
        # Find pieces of the specified type
        for square, piece_on_square in board.piece_map().items():
            if piece_on_square.symbol().upper() == piece:
                # Check if this piece attacks the target types
                attacked_targets = 0
                for target in targets:
                    # Find pieces of target type
                    for target_square, target_piece in board.piece_map().items():
                        if target_piece.symbol().upper() == target.upper():
                            # Check if our piece attacks this target
                            if board.is_attacked_by(piece_on_square.color, target_square):
                                attacked_targets += 1
                                break
                
                if attacked_targets >= 2:
                    return True
        
        return False
    
    def _detect_pin(self, board: chess.Board, pin: dict) -> bool:
        """Detect if a pin pattern exists on the board."""
        # Simplified pin detection
        color = chess.WHITE if board.turn == chess.BLACK else chess.BLACK
        
        for square in board.piece_map():
            if board.is_pinned(color, square):
                return True
        
        return False
    
    def _extract_endgame_skills(self, memory: "MemoryEntry") -> list[AgentSkill]:
        """Extract endgame skills from a memory."""
        skills = []
        
        try:
            board = chess.Board(memory.board_state)
            
            # Check if this is an endgame position
            if self._is_endgame(board):
                # Determine the endgame type
                piece_count = len(board.piece_map())
                
                # Check for K+Q vs K
                queens = [p for p in board.piece_map().values() if p.piece_type == chess.QUEEN]
                if len(queens) == 1 and piece_count <= 4:
                    skill = AgentSkill(
                        agent_id=memory.agent_id,
                        name="K+Q vs K",
                        skill_type="endgame",
                        description="King and Queen vs King endgame",
                        data={"type": "kq_vs_k"},
                        tags=["endgame", "kq_vs_k"]
                    )
                    skills.append(skill)
                
                # Check for K+R vs K
                rooks = [p for p in board.piece_map().values() if p.piece_type == chess.ROOK]
                if len(rooks) == 1 and len(queens) == 0 and piece_count <= 4:
                    skill = AgentSkill(
                        agent_id=memory.agent_id,
                        name="K+R vs K",
                        skill_type="endgame",
                        description="King and Rook vs King endgame",
                        data={"type": "kr_vs_k"},
                        tags=["endgame", "kr_vs_k"]
                    )
                    skills.append(skill)
                
                # Check for K+P vs K
                pawns = [p for p in board.piece_map().values() if p.piece_type == chess.PAWN]
                if len(pawns) == 1 and len(queens) == 0 and len(rooks) == 0 and piece_count <= 4:
                    skill = AgentSkill(
                        agent_id=memory.agent_id,
                        name="K+P vs K",
                        skill_type="endgame",
                        description="King and Pawn vs King endgame",
                        data={"type": "kp_vs_k"},
                        tags=["endgame", "kp_vs_k"]
                    )
                    skills.append(skill)
        
        except Exception:
            pass
        
        return skills
    
    def _is_endgame(self, board: chess.Board) -> bool:
        """Check if the position is an endgame."""
        piece_count = len(board.piece_map())
        return piece_count <= 10


# Global skill extractor instance
_skill_extractor: Optional[SkillExtractor] = None


def get_skill_extractor() -> SkillExtractor:
    """Get the global skill extractor instance."""
    global _skill_extractor
    if _skill_extractor is None:
        _skill_extractor = SkillExtractor()
    return _skill_extractor
