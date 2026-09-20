"""
Agent Registry - Central management for all chess agents.

This module provides a central registry for managing agent states, connections,
and lifecycle. It supports multiple agent types (MCP, ACP, Webhook, Direct) and
provides a unified interface for agent operations.
"""

import asyncio
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
class AgentConfig:
    """Configuration for a registered agent."""
    agent_id: str
    name: str
    agent_type: str  # "mcp", "acp", "webhook", "direct"
    model: Optional[str] = None  # For direct/LLM agents
    endpoint: Optional[str] = None  # For MCP/Webhook agents
    api_key: Optional[str] = None
    timeout: int = 120
    max_retries: int = 3
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AgentState:
    """Runtime state of an agent."""
    agent_id: str
    status: str = "idle"  # "idle", "thinking", "playing", "error", "disconnected"
    current_game: Optional[str] = None
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    error_message: Optional[str] = None
    connection_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AgentRegistry:
    """
    Central registry for managing chess agents.
    
    Supports multiple storage backends:
    - JSON files (default, for development)
    - SQLite (recommended, for production)
    - In-memory (for testing)
    
    Usage:
        registry = AgentRegistry()
        
        # Register an agent
        registry.register_agent(
            agent_id="hermes-chess",
            name="Hermes Chess Agent",
            agent_type="mcp",
            endpoint="http://localhost:8081"
        )
        
        # Get agent config
        config = registry.get_agent("hermes-chess")
        
        # Update agent state
        registry.update_state("hermes-chess", status="playing", current_game="game-123")
    """
    
    def __init__(
        self,
        storage_path: str = "agents",
        db_url: Optional[str] = None,
        use_sqlite: bool = True
    ):
        """
        Initialize the agent registry.
        
        Args:
            storage_path: Path for JSON file storage (if not using SQLite)
            db_url: SQLite database URL (e.g., "sqlite:///agents.db")
            use_sqlite: Whether to use SQLite as the primary storage
        """
        self.storage_path = Path(storage_path)
        self.use_sqlite = use_sqlite
        self._agents: dict[str, AgentConfig] = {}
        self._states: dict[str, AgentState] = {}
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        
        # Initialize storage
        if use_sqlite:
            self._db_url = db_url or f"sqlite:///{self.storage_path / 'agents.db'}"
            self._init_sqlite()
        else:
            self._storage_path = self.storage_path / "agents"
            self._storage_path.mkdir(parents=True, exist_ok=True)
            self._load_from_files()
    
    def _init_sqlite(self):
        """Initialize SQLite database."""
        self._conn = sqlite3.connect(self._db_url.replace("sqlite:///", ""))
        self._conn.row_factory = sqlite3.Row
        
        # Create tables
        cursor = self._conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                model TEXT,
                endpoint TEXT,
                api_key TEXT,
                timeout INTEGER DEFAULT 120,
                max_retries INTEGER DEFAULT 3,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_states (
                agent_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'idle',
                current_game TEXT,
                last_activity TEXT NOT NULL,
                error_message TEXT,
                connection_count INTEGER DEFAULT 0,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            )
        """)
        
        self._conn.commit()
        self._load_from_sqlite()
    
    def _load_from_sqlite(self):
        """Load agents from SQLite database."""
        cursor = self._conn.cursor()
        
        # Load agents
        cursor.execute("SELECT * FROM agents")
        for row in cursor.fetchall():
            config = AgentConfig(
                agent_id=row["agent_id"],
                name=row["name"],
                agent_type=row["agent_type"],
                model=row["model"],
                endpoint=row["endpoint"],
                api_key=row["api_key"],
                timeout=row["timeout"],
                max_retries=row["max_retries"],
                description=row["description"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            self._agents[config.agent_id] = config
        
        # Load states
        cursor.execute("SELECT * FROM agent_states")
        for row in cursor.fetchall():
            state = AgentState(
                agent_id=row["agent_id"],
                status=row["status"],
                current_game=row["current_game"],
                last_activity=row["last_activity"],
                error_message=row["error_message"],
                connection_count=row["connection_count"]
            )
            self._states[state.agent_id] = state
    
    def _load_from_files(self):
        """Load agents from JSON files."""
        agents_dir = self._storage_path / "configs"
        if agents_dir.exists():
            for config_file in agents_dir.glob("*.json"):
                with open(config_file) as f:
                    data = json.load(f)
                    config = AgentConfig.from_dict(data)
                    self._agents[config.agent_id] = config
                    
        states_dir = self._storage_path / "states"
        if states_dir.exists():
            for state_file in states_dir.glob("*.json"):
                with open(state_file) as f:
                    data = json.load(f)
                    state = AgentState.from_dict(data)
                    self._states[state.agent_id] = state
    
    def _save_to_sqlite(self):
        """Save all data to SQLite."""
        cursor = self._conn.cursor()
        
        # Clear existing data
        cursor.execute("DELETE FROM agents")
        cursor.execute("DELETE FROM agent_states")
        
        # Insert agents
        for config in self._agents.values():
            cursor.execute("""
                INSERT INTO agents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config.agent_id,
                config.name,
                config.agent_type,
                config.model,
                config.endpoint,
                config.api_key,
                config.timeout,
                config.max_retries,
                config.description,
                config.created_at,
                config.updated_at
            ))
        
        # Insert states
        for state in self._states.values():
            cursor.execute("""
                INSERT INTO agent_states VALUES (?, ?, ?, ?, ?, ?)
            """, (
                state.agent_id,
                state.status,
                state.current_game,
                state.last_activity,
                state.error_message,
                state.connection_count
            ))
        
        self._conn.commit()
    
    def _save_to_files(self):
        """Save all data to JSON files."""
        agents_dir = self._storage_path / "configs"
        states_dir = self._storage_path / "states"
        
        agents_dir.mkdir(parents=True, exist_ok=True)
        states_dir.mkdir(parents=True, exist_ok=True)
        
        # Save agents
        for config in self._agents.values():
            config_file = agents_dir / f"{config.agent_id}.json"
            with open(config_file, "w") as f:
                json.dump(config.to_dict(), f, indent=2)
        
        # Save states
        for state in self._states.values():
            state_file = states_dir / f"{state.agent_id}.json"
            with open(state_file, "w") as f:
                json.dump(state.to_dict(), f, indent=2)
    
    def register_agent(
        self,
        agent_id: str,
        name: str,
        agent_type: str,
        model: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
        description: str = ""
    ) -> AgentConfig:
        """
        Register a new agent.
        
        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            agent_type: "mcp", "acp", "webhook", or "direct"
            model: Model name (for direct/LLM agents)
            endpoint: Endpoint URL (for MCP/Webhook agents)
            api_key: API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            description: Agent description
            
        Returns:
            The created AgentConfig
        """
        with self._lock:
            if agent_id in self._agents:
                raise ValueError(f"Agent '{agent_id}' already registered")
            
            config = AgentConfig(
                agent_id=agent_id,
                name=name,
                agent_type=agent_type,
                model=model,
                endpoint=endpoint,
                api_key=api_key,
                timeout=timeout,
                max_retries=max_retries,
                description=description
            )
            
            self._agents[agent_id] = config
            self._states[agent_id] = AgentState(agent_id=agent_id)
            
            # Persist
            if self.use_sqlite:
                self._save_to_sqlite()
            else:
                self._save_to_files()
            
            return config
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            True if agent was unregistered, False if not found
        """
        with self._lock:
            if agent_id not in self._agents:
                return False
            
            del self._agents[agent_id]
            if agent_id in self._states:
                del self._states[agent_id]
            
            # Persist
            if self.use_sqlite:
                self._save_to_sqlite()
            else:
                self._save_to_files()
            
            return True
    
    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent configuration by ID."""
        with self._lock:
            return self._agents.get(agent_id)
    
    def get_state(self, agent_id: str) -> Optional[AgentState]:
        """Get agent state by ID."""
        with self._lock:
            return self._states.get(agent_id)
    
    def update_state(
        self,
        agent_id: str,
        status: Optional[str] = None,
        current_game: Optional[str] = None,
        error_message: Optional[str] = None,
        connection_count: Optional[int] = None
    ) -> Optional[AgentState]:
        """
        Update agent state.
        
        Args:
            agent_id: ID of the agent
            status: New status
            current_game: Current game ID
            error_message: Error message (if status is "error")
            connection_count: Connection count
            
        Returns:
            Updated AgentState or None if agent not found
        """
        with self._lock:
            if agent_id not in self._states:
                return None
            
            state = self._states[agent_id]
            if status is not None:
                state.status = status
            if current_game is not None:
                state.current_game = current_game
            if error_message is not None:
                state.error_message = error_message
            if connection_count is not None:
                state.connection_count = connection_count
            
            state.last_activity = datetime.now().isoformat()
            
            # Persist
            if self.use_sqlite:
                self._save_to_sqlite()
            else:
                self._save_to_files()
            
            return state
    
    def list_agents(self, agent_type: Optional[str] = None) -> list[AgentConfig]:
        """
        List all registered agents.
        
        Args:
            agent_type: Filter by agent type (optional)
            
        Returns:
            List of AgentConfig objects
        """
        with self._lock:
            if agent_type:
                return [c for c in self._agents.values() if c.agent_type == agent_type]
            return list(self._agents.values())
    
    def get_agents_by_type(self, agent_type: str) -> list[AgentConfig]:
        """Get all agents of a specific type."""
        return self.list_agents(agent_type=agent_type)
    
    def clear(self):
        """Clear all registered agents and states."""
        with self._lock:
            self._agents.clear()
            self._states.clear()
            
            if self.use_sqlite:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM agents")
                cursor.execute("DELETE FROM agent_states")
                self._conn.commit()
            else:
                # Remove all JSON files
                if self._storage_path.exists():
                    import shutil
                    shutil.rmtree(self._storage_path)
                    self._storage_path.mkdir(parents=True, exist_ok=True)
    
    def close(self):
        """Close the registry and cleanup resources."""
        if self.use_sqlite and hasattr(self, "_conn"):
            self._conn.close()


# Global registry instance
_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def reset_registry():
    """Reset the global registry (for testing)."""
    global _registry
    if _registry is not None:
        _registry.close()
        _registry = None
