"""
Agent Integration Module for LLM Chess.

This module provides the infrastructure for integrating external agent harnesses
(Hermes Agent, OpenCode, Vibe CLI, custom agents) with the chess-llm system.

Components:
- AgentPlayer: Chess player backed by external agents
- AgentRegistry: Central registry for agent management
- Memory: Agent memory and experience storage
- Skills: Agent skill development and application
- Learning: Game analysis and lesson extraction
- Protocols: MCP, ACP, Webhook implementations
"""

# Import from submodules
from .agent_player import AgentPlayer
from .registry import AgentRegistry, get_registry, reset_registry
from .memory import AgentMemory, MemoryEntry, MemoryManager, get_memory_manager, reset_memory_manager
from .skills import AgentSkill, SkillManager, SkillExtractor, get_skill_extractor
from .learning import Lesson, PerformanceMetric, LessonExtractor, LearningSystem, get_learning_system, reset_learning_system

__all__ = [
    # AgentPlayer
    "AgentPlayer",
    
    # Registry
    "AgentRegistry",
    "get_registry",
    "reset_registry",
    
    # Memory
    "AgentMemory",
    "MemoryEntry",
    "MemoryManager",
    "get_memory_manager",
    "reset_memory_manager",
    
    # Skills
    "AgentSkill",
    "SkillManager",
    "SkillExtractor",
    "get_skill_extractor",
    
    # Learning
    "Lesson",
    "PerformanceMetric",
    "LessonExtractor",
    "LearningSystem",
    "get_learning_system",
    "reset_learning_system",
]

# Version info
__version__ = "1.0.0"
