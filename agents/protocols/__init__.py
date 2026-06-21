"""
Protocol implementations for agent communication.

This module provides the communication protocols for integrating with
different agent harnesses:
- MCP (Model Context Protocol)
- ACP (Agent Capability Protocol)
- Webhooks (HTTP/JSON)
"""

from .mcp_server import ChessMCPServer
from .acp_skills import ChessSkills
from .webhook_server import WebhookServer

__all__ = [
    "ChessMCPServer",
    "ChessSkills", 
    "WebhookServer",
]

__version__ = "1.0.0"
