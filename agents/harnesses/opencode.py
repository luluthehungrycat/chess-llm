"""
OpenCode Agent Harness for LLM Chess

This module provides integration with OpenCode Agent harness.
OpenCode supports MCP servers, webhooks, and CLI commands.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseAgentHarness, AgentResponse, GameState, AgentConnectionError


class OpenCodeAgentHarness(BaseAgentHarness):
    """
    OpenCode Agent Harness
    
    Communicates with OpenCode Agent via:
    1. MCP Server (port 8081 by default)
    2. HTTP API (opencode serve, port 4096 by default)
    3. CLI commands (opencode one-shot prompting)
    
    OpenCode supports:
    - MCP (Model Context Protocol) - native support
    - HTTP API - via opencode serve
    - CLI - via opencode command
    - ACP (Agent Capability Protocol) - native support
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        name: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
        use_tools: bool = True,
        temperature: float = 0.3,
        tiny: bool = False,
        reasoning: Optional[str] = None,
        constrain: bool = False,
        # OpenCode-specific options
        endpoint: Optional[str] = None,  # MCP or HTTP endpoint
        mcp_port: int = 8081,           # MCP server port
        http_port: int = 4096,          # HTTP server port
        use_cli: bool = False,          # Use CLI instead of server
        cli_command: Optional[str] = None,  # Custom CLI command
        **kwargs
    ):
        """
        Initialize OpenCode Agent Harness.
        
        Args:
            model: Model to use with OpenCode
            endpoint: MCP or HTTP endpoint URL
            mcp_port: MCP server port (default: 8081)
            http_port: HTTP server port (default: 4096)
            use_cli: Use CLI commands instead of server
            cli_command: Custom CLI command (default: 'opencode')
        """
        self.endpoint = endpoint
        self.mcp_port = mcp_port
        self.http_port = http_port
        self.use_cli = use_cli
        self.cli_command = cli_command or self._find_opencode_command()
        self._mcp_endpoint = None
        self._http_endpoint = None
        
        super().__init__(
            model=model,
            name=name,
            timeout=timeout,
            max_retries=max_retries,
            use_tools=use_tools,
            temperature=temperature,
            tiny=tiny,
            reasoning=reasoning,
            constrain=constrain,
            **kwargs
        )
    
    @property
    def harness_name(self) -> str:
        return "opencode-agent"
    
    @property
    def harness_type(self) -> str:
        if self.use_cli:
            return "cli"
        elif self.endpoint and self.endpoint.startswith("http"):
            return "http"
        else:
            return "mcp"
    
    def _find_opencode_command(self) -> str:
        """Find the opencode command in PATH."""
        import shutil
        
        # Try common command names
        commands = ["opencode", "opencode-agent", "opencode-cli"]
        for cmd in commands:
            if shutil.which(cmd):
                return cmd
        
        # Check if opencode is installed as a module
        try:
            import opencode
            return "python -m opencode"
        except ImportError:
            pass
        
        raise FileNotFoundError(
            "OpenCode not found. Install it with: pip install opencode-agent"
        )
    
    def _initialize(self, **kwargs):
        """Initialize the OpenCode harness."""
        # Set up endpoints
        if self.endpoint:
            if self.endpoint.startswith("http"):
                self._http_endpoint = self.endpoint
            else:
                self._mcp_endpoint = self.endpoint
        else:
            # Default endpoints
            self._mcp_endpoint = f"http://localhost:{self.mcp_port}"
            self._http_endpoint = f"http://localhost:{self.http_port}"
        
        # Check if we should use CLI
        if self.use_cli:
            self._verify_cli_available()
    
    def _verify_cli_available(self):
        """Verify that the OpenCode CLI is available."""
        try:
            result = subprocess.run(
                [self.cli_command, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise FileNotFoundError(f"OpenCode CLI not working: {result.stderr}")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"OpenCode CLI command '{self.cli_command}' not found. "
                "Install OpenCode Agent or set use_cli=False to use server mode."
            )
    
    def check_connectivity(self) -> bool:
        """Check if OpenCode is reachable."""
        if self.use_cli:
            # CLI is available if we can run --version
            self._verify_cli_available()
            return True
        
        # Try MCP endpoint
        if self._mcp_endpoint:
            try:
                self._test_mcp_endpoint()
                return True
            except Exception:
                pass
        
        # Try HTTP endpoint
        if self._http_endpoint:
            try:
                self._test_http_endpoint()
                return True
            except Exception:
                pass
        
        raise AgentConnectionError(
            f"Cannot connect to OpenCode. Tried: "
            f"MCP={self._mcp_endpoint}, HTTP={self._http_endpoint}. "
            "Is OpenCode running? Start with: opencode serve"
        )
    
    def _test_mcp_endpoint(self):
        """Test MCP endpoint connectivity."""
        # MCP typically uses SSE or WebSocket, but we can try a simple HTTP check
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._mcp_endpoint}/health")
                if response.status_code != 200:
                    raise Exception(f"MCP health check failed: {response.status_code}")
        except Exception as e:
            # Try without /health
            try:
                with httpx.Client(timeout=5) as client:
                    response = client.get(self._mcp_endpoint)
                    if response.status_code >= 400:
                        raise Exception(f"MCP endpoint returned: {response.status_code}")
            except Exception as e2:
                raise Exception(f"Cannot reach MCP endpoint {self._mcp_endpoint}: {e2}") from e
    
    def _test_http_endpoint(self):
        """Test HTTP endpoint connectivity."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._http_endpoint}/health")
                if response.status_code != 200:
                    raise Exception(f"HTTP health check failed: {response.status_code}")
        except Exception as e:
            # Try without /health
            try:
                with httpx.Client(timeout=5) as client:
                    response = client.get(self._http_endpoint)
                    if response.status_code >= 400:
                        raise Exception(f"HTTP endpoint returned: {response.status_code}")
            except Exception as e2:
                raise Exception(f"Cannot reach HTTP endpoint {self._http_endpoint}: {e2}") from e
    
    async def get_move_async(self, game_state: GameState, timeout: int, retry_attempt: int = 0) -> AgentResponse:
        """Get a move from OpenCode Agent."""
        if self.use_cli:
            return await self._get_move_cli(game_state, timeout)
        elif self._http_endpoint:
            return await self._get_move_http(game_state, timeout)
        else:
            return await self._get_move_mcp(game_state, timeout)
    
    async def _get_move_cli(self, game_state: GameState, timeout: int) -> AgentResponse:
        """Get a move using OpenCode CLI."""
        # Build the prompt
        prompt = self.build_prompt(game_state)
        
        # Add model specification if provided
        if self.model:
            prompt = f"[MODEL: {self.model}]\n{prompt}"
        
        # Add chess-specific instructions
        system_prompt = self._get_system_prompt()
        
        try:
            # Use opencode one-shot prompting
            cmd = [
                self.cli_command,
                "--model", self.model or "default",
                "--prompt", prompt,
                "--system", system_prompt,
                "--temperature", str(self.temperature),
                "--max-tokens", "256",
                "--output-format", "text"
            ]
            
            # Add reasoning if specified
            if self.reasoning:
                cmd.extend(["--reasoning", self.reasoning])
            
            # Run the command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.getcwd()
            )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                
                if process.returncode != 0:
                    return AgentResponse(
                        move=None,
                        reasoning="",
                        error=f"OpenCode CLI error: {stderr}"
                    )
                
                # Parse the response
                response_text = stdout.strip()
                return self._parse_response(response_text, game_state)
                
            except subprocess.TimeoutExpired:
                process.kill()
                raise TimeoutError(f"OpenCode CLI timed out after {timeout}s")
                
        except Exception as e:
            return AgentResponse(
                move=None,
                reasoning="",
                error=f"OpenCode CLI failed: {e}"
            )
    
    async def _get_move_http(self, game_state: GameState, timeout: int) -> AgentResponse:
        """Get a move using OpenCode HTTP API."""
        # Build the request
        prompt = self.build_prompt(game_state)
        system_prompt = self._get_system_prompt()
        
        request_data = {
            "model": self.model or "default",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": 256,
            "stream": False
        }
        
        # Add reasoning if specified
        if self.reasoning:
            request_data["reasoning_effort"] = self.reasoning
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._http_endpoint}/chat",
                    json=request_data
                )
                
                if response.status_code != 200:
                    return AgentResponse(
                        move=None,
                        reasoning="",
                        error=f"HTTP {response.status_code}: {response.text}"
                    )
                
                response_data = response.json()
                response_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                return self._parse_response(response_text, game_state)
                
        except Exception as e:
            return AgentResponse(
                move=None,
                reasoning="",
                error=f"HTTP request failed: {e}"
            )
    
    async def _get_move_mcp(self, game_state: GameState, timeout: int) -> AgentResponse:
        """Get a move using MCP protocol."""
        # For MCP, we need to use the MCP client library
        # This is a simplified implementation using HTTP-based MCP
        
        # Build MCP request
        prompt = self.build_prompt(game_state)
        
        request = {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "play_chess_move",
                "arguments": {
                    "game_state": game_state.to_dict(),
                    "prompt": prompt,
                    "model": self.model,
                    "temperature": self.temperature,
                    "use_tools": self.use_tools
                }
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._mcp_endpoint}/mcp",
                    json=request
                )
                
                if response.status_code != 200:
                    return AgentResponse(
                        move=None,
                        reasoning="",
                        error=f"MCP {response.status_code}: {response.text}"
                    )
                
                response_data = response.json()
                
                # Extract move from MCP response
                if "result" in response_data:
                    result = response_data["result"]
                    if isinstance(result, dict):
                        move = result.get("move", result.get("content", ""))
                        reasoning = result.get("reasoning", "")
                        return AgentResponse(
                            move=move,
                            reasoning=reasoning,
                            raw_response=str(result)
                        )
                    else:
                        return self._parse_response(str(result), game_state)
                
                return self._parse_response(str(response_data), game_state)
                
        except Exception as e:
            return AgentResponse(
                move=None,
                reasoning="",
                error=f"MCP request failed: {e}"
            )
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for OpenCode."""
        return """You are a chess-playing AI agent. Your task is to play chess at the highest level possible.

Rules:
1. Always respond with a valid UCI chess move (e.g., e2e4, g1f3, e7e8q)
2. Only output the move, nothing else
3. Think carefully about the best move in the current position
4. Consider tactics, strategy, and your opponent's potential responses
5. Never make illegal moves
6. If you're unsure, pick the most principled move according to chess fundamentals

Remember: You are playing to win. Be aggressive when appropriate, but don't take unnecessary risks."""
    
    def _parse_response(self, response_text: str, game_state: GameState) -> AgentResponse:
        """Parse OpenCode response to extract move."""
        import re
        
        # Clean up the response
        response_text = response_text.strip()
        
        # Try to extract UCI move
        uci_pattern = r'\b([a-h][1-8][a-h][1-8][qrbn]?)\b'
        uci_matches = re.findall(uci_pattern, response_text)
        
        if uci_matches:
            # Get the last UCI move (most likely to be the intended move)
            move = uci_matches[-1]
            return AgentResponse(
                move=move,
                reasoning=response_text,
                raw_response=response_text
            )
        
        # Try to extract SAN move
        san_pattern = r'\b([KQRBNkqrbn]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBNqrbn])?[+#]?)\b'
        san_matches = re.findall(san_pattern, response_text)
        
        if san_matches:
            move = san_matches[-1]
            return AgentResponse(
                move=move,
                reasoning=response_text,
                raw_response=response_text
            )
        
        # Try to extract from MOVE: prefix
        move_pattern = r'(?:MOVE|move|MakeMove|make_move):\s*([a-h][1-8][a-h][1-8][qrbn]?)'
        move_match = re.search(move_pattern, response_text, re.IGNORECASE)
        
        if move_match:
            return AgentResponse(
                move=move_match.group(1),
                reasoning=response_text,
                raw_response=response_text
            )
        
        # If we have a tool call, extract from there
        tool_pattern = r'make_move\s*\(\s*["\']?move["\']?\s*:\s*["\']?([a-h][1-8][a-h][1-8][qrbn]?)["\']?\s*\)'
        tool_match = re.search(tool_pattern, response_text, re.IGNORECASE)
        
        if tool_match:
            return AgentResponse(
                move=tool_match.group(1),
                reasoning=response_text,
                raw_response=response_text
            )
        
        # No move found
        return AgentResponse(
            move=None,
            reasoning=response_text,
            error="No valid chess move found in response",
            raw_response=response_text
        )
    
    def close(self):
        """Close the OpenCode harness."""
        pass
    
    def __repr__(self) -> str:
        if self.model:
            return f"opencode-agent:{self.model}"
        return "opencode-agent"