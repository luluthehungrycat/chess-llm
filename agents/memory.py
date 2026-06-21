"""
Agent Memory System - Experience storage and retrieval for chess agents.

This module provides a system for agents to store, retrieve, and learn from
their chess experiences. Memories include game states, moves, reasoning,
and extracted lessons.
"""

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import chess


@dataclass
class MemoryEntry:
    """A single memory/experience entry for an agent."""
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    game_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Game context
    board_state: str = ""  # FEN string
    move_number: int = 0
    color: str = ""  # "white" or "black"
    
    # Move information
    move: str = ""  # UCI notation
    move_san: str = ""  # SAN notation
    
    # Agent's thought process
    reasoning: str = ""
    confidence: float = 0.0
    
    # Outcome and evaluation
    outcome: str = "unknown"  # "win", "loss", "draw", "unknown"
    evaluation: Optional[float] = None  # Evaluation score (if available)
    
    # Extracted lessons
    lessons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    # Metadata
    opponent: str = ""
    opening: str = ""
    phase: str = ""  # "opening", "middlegame", "endgame"
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "MemoryEntry":
        return cls.from_dict(json.loads(json_str))


class AgentMemory:
    """
    Memory management for a single agent.
    
    Provides storage, retrieval, and querying of memories for a specific agent.
    Supports multiple storage backends (SQLite, JSON files, in-memory).
    
    Usage:
        memory = AgentMemory("hermes-agent")
        
        # Save a memory
        memory.save(MemoryEntry(
            agent_id="hermes-agent",
            game_id="game-123",
            board_state=board.fen(),
            move="e2e4",
            reasoning="Controls the center",
            outcome="win"
        ))
        
        # Query memories
        memories = memory.query(board_state=board.fen())
        similar = memory.find_similar(board.fen())
    """
    
    def __init__(
        self,
        agent_id: str,
        storage_path: str = "agents",
        use_sqlite: bool = True,
        max_entries: int = 1000
    ):
        """
        Initialize memory for an agent.
        
        Args:
            agent_id: ID of the agent
            storage_path: Path for storage
            use_sqlite: Whether to use SQLite
            max_entries: Maximum number of entries to keep
        """
        self.agent_id = agent_id
        self.storage_path = Path(storage_path)
        self.use_sqlite = use_sqlite
        self.max_entries = max_entries
        self._entries: dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()
        
        # Initialize storage
        if use_sqlite:
            self._db_path = self.storage_path / "agents.db"
            self._init_sqlite()
        else:
            self._memory_dir = self.storage_path / agent_id / "memory"
            self._memory_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_files()
    
    def _init_sqlite(self):
        """Initialize SQLite database."""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                board_state TEXT NOT NULL,
                move_number INTEGER DEFAULT 0,
                color TEXT NOT NULL,
                move TEXT NOT NULL,
                move_san TEXT NOT NULL,
                reasoning TEXT DEFAULT '',
                confidence REAL DEFAULT 0.0,
                outcome TEXT DEFAULT 'unknown',
                evaluation REAL,
                lessons TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                opponent TEXT DEFAULT '',
                opening TEXT DEFAULT '',
                phase TEXT DEFAULT '',
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_board ON memories(board_state)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_game ON memories(game_id)
        """)
        
        self._conn.commit()
        self._load_from_sqlite()
    
    def _load_from_sqlite(self):
        """Load memories from SQLite."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE agent_id = ?", (self.agent_id,))
        
        for row in cursor.fetchall():
            entry = MemoryEntry(
                memory_id=row["memory_id"],
                agent_id=row["agent_id"],
                game_id=row["game_id"],
                timestamp=row["timestamp"],
                board_state=row["board_state"],
                move_number=row["move_number"],
                color=row["color"],
                move=row["move"],
                move_san=row["move_san"],
                reasoning=row["reasoning"],
                confidence=row["confidence"],
                outcome=row["outcome"],
                evaluation=row["evaluation"],
                lessons=json.loads(row["lessons"]),
                tags=json.loads(row["tags"]),
                opponent=row["opponent"],
                opening=row["opening"],
                phase=row["phase"]
            )
            self._entries[entry.memory_id] = entry
    
    def _load_from_files(self):
        """Load memories from JSON files."""
        if self._memory_dir.exists():
            for memory_file in self._memory_dir.glob("*.json"):
                with open(memory_file) as f:
                    data = json.load(f)
                    entry = MemoryEntry.from_dict(data)
                    self._entries[entry.memory_id] = entry
    
    def _save_to_sqlite(self, entry: MemoryEntry):
        """Save a memory to SQLite."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO memories VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            entry.memory_id,
            entry.agent_id,
            entry.game_id,
            entry.timestamp,
            entry.board_state,
            entry.move_number,
            entry.color,
            entry.move,
            entry.move_san,
            entry.reasoning,
            entry.confidence,
            entry.outcome,
            entry.evaluation,
            json.dumps(entry.lessons),
            json.dumps(entry.tags),
            entry.opponent,
            entry.opening,
            entry.phase
        ))
        self._conn.commit()
    
    def _save_to_file(self, entry: MemoryEntry):
        """Save a memory to JSON file."""
        memory_file = self._memory_dir / f"{entry.memory_id}.json"
        with open(memory_file, "w") as f:
            json.dump(entry.to_dict(), f, indent=2)
    
    def save(self, entry: MemoryEntry) -> str:
        """
        Save a memory entry.
        
        Args:
            entry: MemoryEntry to save
            
        Returns:
            The memory_id of the saved entry
        """
        with self._lock:
            # Ensure entry has required fields
            entry.agent_id = self.agent_id
            if not entry.memory_id:
                entry.memory_id = str(uuid.uuid4())
            if not entry.timestamp:
                entry.timestamp = datetime.now().isoformat()
            
            self._entries[entry.memory_id] = entry
            
            # Persist
            if self.use_sqlite:
                self._save_to_sqlite(entry)
            else:
                self._save_to_file(entry)
            
            # Enforce max entries
            if len(self._entries) > self.max_entries:
                self._prune_old_entries()
            
            return entry.memory_id
    
    def _prune_old_entries(self):
        """Remove oldest entries if over max_entries."""
        # Sort by timestamp and remove oldest
        sorted_entries = sorted(
            self._entries.values(), 
            key=lambda e: e.timestamp
        )
        
        to_remove = len(sorted_entries) - self.max_entries
        for entry in sorted_entries[:to_remove]:
            del self._entries[entry.memory_id]
            
            if self.use_sqlite:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM memories WHERE memory_id = ?",
                    (entry.memory_id,)
                )
                self._conn.commit()
            else:
                memory_file = self._memory_dir / f"{entry.memory_id}.json"
                if memory_file.exists():
                    memory_file.unlink()
    
    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get a memory by ID."""
        with self._lock:
            return self._entries.get(memory_id)
    
    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        with self._lock:
            if memory_id not in self._entries:
                return False
            
            del self._entries[memory_id]
            
            if self.use_sqlite:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM memories WHERE memory_id = ?",
                    (memory_id,)
                )
                self._conn.commit()
            else:
                memory_file = self._memory_dir / f"{memory_id}.json"
                if memory_file.exists():
                    memory_file.unlink()
            
            return True
    
    def query(
        self,
        board_state: Optional[str] = None,
        game_id: Optional[str] = None,
        outcome: Optional[str] = None,
        opening: Optional[str] = None,
        phase: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100
    ) -> list[MemoryEntry]:
        """
        Query memories with filters.
        
        Args:
            board_state: Filter by FEN (exact or partial match)
            game_id: Filter by game ID
            outcome: Filter by outcome
            opening: Filter by opening
            phase: Filter by game phase
            tag: Filter by tag
            limit: Maximum number of results
            
        Returns:
            List of matching MemoryEntry objects
        """
        with self._lock:
            results = []
            
            for entry in self._entries.values():
                if game_id and entry.game_id != game_id:
                    continue
                if outcome and entry.outcome != outcome:
                    continue
                if opening and entry.opening != opening:
                    continue
                if phase and entry.phase != phase:
                    continue
                if tag and tag not in entry.tags:
                    continue
                if board_state:
                    # Support partial FEN matching (first N characters)
                    if not entry.board_state.startswith(board_state):
                        continue
                
                results.append(entry)
                if len(results) >= limit:
                    break
            
            return results
    
    def find_similar(
        self,
        board_state: str,
        threshold: float = 0.8,
        limit: int = 10
    ) -> list[tuple[MemoryEntry, float]]:
        """
        Find memories with similar board states.
        
        Uses simple FEN similarity (character match percentage).
        For more advanced similarity, consider using board features.
        
        Args:
            board_state: FEN string to compare against
            threshold: Minimum similarity score (0.0-1.0)
            limit: Maximum number of results
            
        Returns:
            List of (MemoryEntry, similarity_score) tuples
        """
        with self._lock:
            results = []
            
            for entry in self._entries.values():
                # Simple similarity: compare FEN strings
                similarity = self._fen_similarity(board_state, entry.board_state)
                if similarity >= threshold:
                    results.append((entry, similarity))
            
            # Sort by similarity (descending)
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]
    
    def _fen_similarity(self, fen1: str, fen2: str) -> float:
        """
        Calculate similarity between two FEN strings.
        
        Uses character-level similarity for simplicity.
        More advanced implementations could use board features.
        """
        # Split FEN into parts
        parts1 = fen1.split()
        parts2 = fen2.split()
        
        if len(parts1) < 1 or len(parts2) < 1:
            return 0.0
        
        # Compare piece placement (first part of FEN)
        piece_placement1 = parts1[0]
        piece_placement2 = parts2[0]
        
        # Count matching characters
        matches = sum(
            1 for c1, c2 in zip(piece_placement1, piece_placement2) 
            if c1 == c2
        )
        
        max_len = max(len(piece_placement1), len(piece_placement2))
        if max_len == 0:
            return 1.0
        
        return matches / max_len
    
    def get_by_game(self, game_id: str) -> list[MemoryEntry]:
        """Get all memories for a specific game."""
        return self.query(game_id=game_id)
    
    def get_recent(self, limit: int = 10) -> list[MemoryEntry]:
        """Get most recent memories."""
        with self._lock:
            sorted_entries = sorted(
                self._entries.values(),
                key=lambda e: e.timestamp,
                reverse=True
            )
            return sorted_entries[:limit]
    
    def count(self) -> int:
        """Get total number of memories."""
        with self._lock:
            return len(self._entries)
    
    def clear(self):
        """Clear all memories for this agent."""
        with self._lock:
            self._entries.clear()
            
            if self.use_sqlite:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM memories WHERE agent_id = ?",
                    (self.agent_id,)
                )
                self._conn.commit()
            else:
                if self._memory_dir.exists():
                    import shutil
                    shutil.rmtree(self._memory_dir)
                    self._memory_dir.mkdir(parents=True, exist_ok=True)
    
    def close(self):
        """Close the memory system."""
        if self.use_sqlite and hasattr(self, "_conn"):
            self._conn.close()


class MemoryManager:
    """
    Global memory manager for all agents.
    
    Provides a centralized interface for managing memories across all agents.
    """
    
    def __init__(
        self,
        storage_path: str = "agents",
        use_sqlite: bool = True,
        max_entries_per_agent: int = 1000
    ):
        """
        Initialize the memory manager.
        
        Args:
            storage_path: Path for storage
            use_sqlite: Whether to use SQLite
            max_entries_per_agent: Max entries per agent
        """
        self.storage_path = Path(storage_path)
        self.use_sqlite = use_sqlite
        self.max_entries_per_agent = max_entries_per_agent
        self._agent_memories: dict[str, AgentMemory] = {}
        self._lock = threading.RLock()
    
    def get_memory(self, agent_id: str) -> AgentMemory:
        """Get or create memory for an agent."""
        with self._lock:
            if agent_id not in self._agent_memories:
                self._agent_memories[agent_id] = AgentMemory(
                    agent_id=agent_id,
                    storage_path=self.storage_path,
                    use_sqlite=self.use_sqlite,
                    max_entries=self.max_entries_per_agent
                )
            return self._agent_memories[agent_id]
    
    def save(
        self,
        agent_id: str,
        board_state: str,
        move: str,
        reasoning: str = "",
        game_id: str = "",
        move_number: int = 0,
        color: str = "",
        confidence: float = 0.0,
        outcome: str = "unknown",
        lessons: list[str] = None,
        tags: list[str] = None,
        **kwargs
    ) -> str:
        """
        Save a memory for an agent.
        
        Convenience method that creates a MemoryEntry and saves it.
        
        Args:
            agent_id: ID of the agent
            board_state: FEN string
            move: UCI move
            reasoning: Agent's reasoning
            game_id: Game ID
            move_number: Move number
            color: Color to move
            confidence: Confidence score
            outcome: Game outcome
            lessons: Extracted lessons
            tags: Tags for categorization
            **kwargs: Additional MemoryEntry fields
            
        Returns:
            The memory_id of the saved entry
        """
        memory = self.get_memory(agent_id)
        
        # Create board to get SAN notation
        try:
            board = chess.Board(board_state)
            move_obj = board.parse_uci(move)
            move_san = board.san(move_obj)
        except Exception:
            move_san = move
        
        entry = MemoryEntry(
            agent_id=agent_id,
            game_id=game_id,
            board_state=board_state,
            move_number=move_number,
            color=color,
            move=move,
            move_san=move_san,
            reasoning=reasoning,
            confidence=confidence,
            outcome=outcome,
            lessons=lessons or [],
            tags=tags or [],
            **kwargs
        )
        
        return memory.save(entry)
    
    def query(
        self,
        agent_id: Optional[str] = None,
        board_state: Optional[str] = None,
        game_id: Optional[str] = None,
        **kwargs
    ) -> list[MemoryEntry]:
        """
        Query memories across all agents.
        
        Args:
            agent_id: Filter by agent ID
            board_state: Filter by FEN
            game_id: Filter by game ID
            **kwargs: Additional query parameters
            
        Returns:
            List of matching MemoryEntry objects
        """
        if agent_id:
            memory = self.get_memory(agent_id)
            return memory.query(board_state=board_state, game_id=game_id, **kwargs)
        
        # Query across all agents
        results = []
        with self._lock:
            for agent_id, memory in self._agent_memories.items():
                results.extend(memory.query(
                    board_state=board_state,
                    game_id=game_id,
                    **kwargs
                ))
        
        return results
    
    def clear(self):
        """Clear all memories for all agents."""
        with self._lock:
            for memory in self._agent_memories.values():
                memory.clear()
            self._agent_memories.clear()
    
    def close(self):
        """Close the memory manager."""
        with self._lock:
            for memory in self._agent_memories.values():
                memory.close()
            self._agent_memories.clear()


# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def reset_memory_manager():
    """Reset the global memory manager (for testing)."""
    global _memory_manager
    if _memory_manager is not None:
        _memory_manager.close()
        _memory_manager = None
