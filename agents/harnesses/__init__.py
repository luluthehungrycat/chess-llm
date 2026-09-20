"""
Agent Harness Integration for LLM Chess

This module provides implementations for various agent harnesses:
- OpenCode Agent
- Hermes Agent  
- Vibe CLI
- Custom agents

Each harness can communicate via:
- MCP (Model Context Protocol)
- ACP (Agent Capability Protocol) 
- Webhooks (HTTP/JSON)
- CLI commands
"""

from .base import BaseAgentHarness, AgentHarnessError, GameState, AgentResponse
from .opencode import OpenCodeAgentHarness
from .hermes import HermesAgentHarness
from .vibe_cli import VibeCLIAgentHarness

__all__ = [
    'BaseAgentHarness',
    'AgentHarnessError',
    'GameState',
    'AgentResponse',
    'OpenCodeAgentHarness',
    'HermesAgentHarness',
    'VibeCLIAgentHarness',
    'get_harness',
]


def get_harness(harness_name: str, model: str = None, **kwargs) -> BaseAgentHarness:
    """
    Factory function to get the appropriate agent harness.
    
    Args:
        harness_name: Name of the harness ('opencode', 'hermes', 'vibe-cli')
        model: Model to use with the harness
        **kwargs: Additional harness-specific arguments
        
    Returns:
        Appropriate agent harness instance
    """
    harness_map = {
        'opencode': OpenCodeAgentHarness,
        'opencode-agent': OpenCodeAgentHarness,
        'hermes': HermesAgentHarness,
        'hermes-agent': HermesAgentHarness,
        'vibe': VibeCLIAgentHarness,
        'vibe-cli': VibeCLIAgentHarness,
        'vibe_cli': VibeCLIAgentHarness,
    }
    
    harness_class = harness_map.get(harness_name.lower())
    if harness_class is None:
        raise ValueError(f"Unknown agent harness: {harness_name}")
    
    return harness_class(model=model, **kwargs)