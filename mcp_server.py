#!/usr/bin/env python3
"""
MCP Server Entry Point for Chess LLM Agent Integration.

This is the main entry point for running the MCP server that enables
agent harnesses (Hermes, Claude Code, Vibe CLI, custom agents) to
interact with the chess-llm system.

Usage:
    python mcp_server.py --port 8081
    python mcp_server.py --port 8081 --transport stdio
    python mcp_server.py --port 8081 --transport http
"""

from chess_llm.agents.protocols.mcp_server import main

if __name__ == "__main__":
    main()
