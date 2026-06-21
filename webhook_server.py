#!/usr/bin/env python3
"""
Webhook Server Entry Point for Chess LLM Agent Integration.

This is the main entry point for running the webhook server that enables
agents to interact with the chess-llm system via HTTP/JSON.

Usage:
    python webhook_server.py --port 8082
    python webhook_server.py --port 8082 --api-key my-secret-key
"""

from chess_llm.agents.protocols.webhook_server import main

if __name__ == "__main__":
    main()
