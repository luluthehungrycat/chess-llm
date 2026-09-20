"""
Vibe CLI Agent Harness for LLM Chess

This module provides integration with Vibe CLI agent harness.
Vibe CLI supports MCP servers, ACP, and CLI commands.
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


class VibeCLIAgentHarness(BaseAgentHarness):
    """
    Vibe CLI Agent Harness
    
    Communicates with Vibe CLI via:
    1. MCP Server (native support)
    2. ACP (Agent Capability Protocol) - native support
    3. CLI commands (vibe command)
    
    Vibe CLI supports:
    - MCP (Model Context Protocol) - native support
    - ACP (Agent Capability Protocol) - native support
    - CLI - vibe command for one-shot prompting
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
        # Vibe CLI-specific options
        endpoint: Optional[str] = None,  # MCP or ACP endpoint
        mcp_port: int = 8080,            # Default Vibe MCP port
        acp_port: int = 8081,            # Default Vibe ACP port
        use_cli: bool = False,          # Use CLI instead of server
        cli_command: Optional[str] = None,  # Custom CLI command
        **kwargs
    ):
        """
        Initialize Vibe CLI Agent Harness.
        
        Args:
            model: Model to use with Vibe CLI
            endpoint: MCP or ACP endpoint URL
            mcp_port: MCP server port (default: 8080)
            acp_port: ACP server port (default: 8081)
            use_cli: Use CLI commands instead of server
            cli_command: Custom CLI command (default: 'vibe')
        """
        self.endpoint = endpoint
        self.mcp_port = mcp_port
        self.acp_port = acp_port
        self.use_cli = use_cli
        self.cli_command = cli_command or self._find_vibe_command()
        self._mcp_endpoint = None
        self._acp_endpoint = None
        
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
        return "vibe-cli"
    
    @property
    def harness_type(self) -> str:
        if self.use_cli:
            return "cli"
        elif self.endpoint and self.endpoint.startswith("http"):
            return "acp"  # Vibe CLI uses ACP by default for HTTP
        else:
            return "mcp"
    
    def _find_vibe_command(self) -> str:
        """Find the vibe command in PATH."""
        import shutil
        
        # Try common command names
        commands = ["vibe", "vibe-cli", "vibec"]
        for cmd in commands:
            if shutil.which(cmd):
                return cmd
        
        # Check if vibe is installed as a module
        try:
            import vibe_cli
            return "python -m vibe_cli"
        except ImportError:
            pass
        
        raise FileNotFoundError(
            "Vibe CLI not found. Install it with: pip install vibe-cli"
        )
    
    def _initialize(self, **kwargs):
        """Initialize the Vibe CLI harness."""
        # Set up endpoints
        if self.endpoint:
            if self.endpoint.startswith("http"):
                self._acp_endpoint = self.endpoint
            else:
                self._mcp_endpoint = self.endpoint
        else:
            # Default endpoints
            self._mcp_endpoint = f"http://localhost:{self.mcp_port}"
            self._acp_endpoint = f"http://localhost:{self.acp_port}"
        
        # Check if we should use CLI
        if self.use_cli:
            self._verify_cli_available()
    
    def _verify_cli_available(self):
        """Verify that the Vibe CLI is available."""
        try:
            result = subprocess.run(
                [self.cli_command, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise FileNotFoundError(f"Vibe CLI not working: {result.stderr}")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Vibe CLI command '{self.cli_command}' not found. "
                "Install Vibe CLI or set use_cli=False to use server mode."
            )
    
    def check_connectivity(self) -> bool:
        """Check if Vibe CLI is reachable."""
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
        
        # Try ACP endpoint
        if self._acp_endpoint:
            try:
                self._test_acp_endpoint()
                return True
            except Exception:
                pass
        
        raise AgentConnectionError(
            f"Cannot connect to Vibe CLI. Tried: "
            f"MCP={self._mcp_endpoint}, ACP={self._acp_endpoint}. "
            "Is Vibe CLI running? Start with: vibe serve"
        )
    
    def _test_mcp_endpoint(self):
        """Test MCP endpoint connectivity."""
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
    
    def _test_acp_endpoint(self):
        """Test ACP endpoint connectivity."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._acp_endpoint}/health")
                if response.status_code != 200:
                    raise Exception(f"ACP health check failed: {response.status_code}")
        except Exception as e:
            # Try without /health
            try:
                with httpx.Client(timeout=5) as client:
                    response = client.get(self._acp_endpoint)
                    if response.status_code >= 400:
                        raise Exception(f"ACP endpoint returned: {response.status_code}")
            except Exception as e2:
                raise Exception(f"Cannot reach ACP endpoint {self._acp_endpoint}: {e2}") from e
    
    async def get_move_async(self, game_state: GameState, timeout: int, retry_attempt: int = 0) -> AgentResponse:
        """Get a move from Vibe CLI."""
        if self.use_cli:
            return await self._get_move_cli(game_state, timeout)
        elif self._acp_endpoint:
            return await self._get_move_acp(game_state, timeout)
        else:
            return await self._get_move_mcp(game_state, timeout)
    
    async def _get_move_cli(self, game_state: GameState, timeout: int) -> AgentResponse:
        """Get a move using Vibe CLI commands."""
        # Build the prompt
        prompt = self.build_prompt(game_state)
        
        # Add model specification if provided
        if self.model:
            prompt = f"[MODEL: {self.model}]\n{prompt}"
        
        # Add chess-specific instructions
        system_prompt = self._get_system_prompt()
        
        try:
            # Use vibe one-shot prompting
            cmd = [
                self.cli_command,
                "--model", self.model or "default",
                "--prompt", prompt,
                "--system", system_prompt,
                "--temperature", str(self.temperature),
                "--max-tokens", "256"
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
                        error=f"Vibe CLI error: {stderr}"
                    )
                
                # Parse the response
                response_text = stdout.strip()
                return self._parse_response(response_text, game_state)
                
            except subprocess.TimeoutExpired:
                process.kill()
                raise TimeoutError(f"Vibe CLI timed out after {timeout}s")
                
        except Exception as e:
            return AgentResponse(
                move=None,
                reasoning="",
                error=f"Vibe CLI failed: {e}"
            )
    
    async def _get_move_acp(self, game_state: GameState, timeout: int) -> AgentResponse:
        """Get a move using ACP protocol."""
        # Build ACP request for Vibe CLI
        prompt = self.build_prompt(game_state)
        
        request = {
            "id": 1,
            "method": "agents/execute",
            "params": {
                "agent_id": "chess-player",
                "task": prompt,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": 256,
                "use_tools": self.use_tools
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._acp_endpoint}/acp",
                    json=request
                )
                
                if response.status_code != 200:
                    return AgentResponse(
                        move=None,
                        reasoning="",
                        error=f"ACP {response.status_code}: {response.text}"
                    )
                
                response_data = response.json()
                
                # Extract move from ACP response
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
                error=f"ACP request failed: {e}"
            )
    
    async def _get_move_mcp(self, game_state: GameState, timeout: int) -> AgentResponse:
        """Get a move using MCP protocol."""
        # Build MCP request for Vibe CLI
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
        """Get the system prompt for Vibe CLI."""
        return """You are a chess-playing AI agent using Vibe CLI. Your task is to play chess at the highest level possible.

Rules:
1. Always respond with a valid UCI chess move (e.g., e2e4, g1f3, e7e8q)
2. Only output the move, nothing else
3. Think carefully about the best move in the current position
4. Consider tactics, strategy, and your opponent's potential responses
5. Never make illegal moves
6. If you're unsure, pick the most principled move according to chess fundamentals
7. Learn from your mistakes and improve your play over time

Remember: You are playing to win. Be aggressive when appropriate, but don't take unnecessary risks.

As a Vibe CLI agent, you have access to your memory and skills. Use them to improve your chess playing ability."""
    
    def _parse_response(self, response_text: str, game_state: GameState) -> AgentResponse:
        """Parse Vibe CLI response to extract move."""
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
        """Close the Vibe CLI harness."""
        pass
    
    def __repr__(self) -> str:
        if self.model:
            return f"vibe-cli:{self.model}"
        return "vibe-cli"