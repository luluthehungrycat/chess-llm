# 🎯 Agent Harness Integration - Technical Specification

**Project**: LLM Chess Agent Competition System  
**Version**: 1.0.0  
**Date**: 2025-01-XX  
**Author**: Vibe Code  

---

## 📋 Executive Summary

This specification outlines the architecture, protocols, and implementation details for integrating external agent harnesses (Hermes Agent, OpenCode, Vibe CLI, and custom agents) with the LLM Chess system. The goal is to enable agents to compete in chess games, learn from their experiences, and develop autonomous strategies.

---

## 🎯 Objectives

### Primary Goals
1. **Agent Competition**: Enable agent harnesses to play chess against each other, LLMs, Stockfish, and humans
2. **Learning System**: Allow agents to commit game experiences to memory and develop skills
3. **Multi-Protocol Support**: Support MCP (Model Context Protocol), ACP (Agent Capability Protocol), and Webhooks
4. **Compatibility**: Ensure compatibility with Hermes Agent, OpenCode, Vibe CLI, and custom agent frameworks

### Secondary Goals
1. **Performance Tracking**: ELO ratings and statistics for agents
2. **Skill Development**: Extract and apply learned chess skills
3. **Tournament Integration**: Seamless integration with existing tournament system
4. **Extensibility**: Easy to add new agent types and protocols

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            AGENT INTEGRATION LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │   MCP Server     │  │   ACP Skills      │  │    Webhook Endpoints      │  │
│  │   (port 8081)    │  │   (Hermes)        │  │    (port 8082)            │  │
│  └─────────┬─────────┘  └─────────┬─────────┘  └─────────────┬────────────┘  │
│            │                   │                        │                   │
│            └───────────────────┼────────────────────────┘                   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Agent Registry & Memory System                     │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │ Agent State  │  │  Memory      │  │  Skills      │  │  Metrics     │  │  │
│  │  │ Management   │  │  Storage     │  │  Registry    │  │  Tracking    │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXISTING CHESS-LLM LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │ LLMPlayer   │  │ Stockfish   │  │  Human       │  │  Random              │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────────────────┘  │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         ChessMatch Orchestrator                         │  │
│  │  - Game state management                                          │  │
│  │  - Move validation                                                │  │
│  │  - PGN generation                                                 │  │
│  │  - Result tracking                                                │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROVIDER & MODEL LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │ OpenCode    │  │ Big Pickle  │  │  OpenRouter  │  │  Local Models         │  │
│  │ Go/Zen      │  │ Proxy       │  │              │  │  (Ollama, DMR, etc.)   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Component Specifications

---

### 1. AgentPlayer Class

#### Purpose
Extends the existing `LLMPlayer` class to support external agent harnesses as chess players.

#### Interface

```python
class AgentPlayer(LLMPlayer):
    """A chess player backed by an external agent harness."""
    
    def __init__(
        self,
        agent_id: str,
        agent_type: str = "mcp",  # "mcp", "acp", "webhook", "direct"
        name: str | None = None,
        **kwargs
    ):
        """
        Initialize an agent player.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Protocol type (mcp, acp, webhook, direct)
            name: Display name for the agent
            **kwargs: Additional LLMPlayer arguments
        """
        pass
```

#### Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `get_move(board, history_text)` | Get move from agent | `chess.Move` |
| `check_connectivity()` | Verify agent is reachable | `bool` |
| `save_to_memory(game_state, reasoning)` | Save experience to agent memory | `bool` |
| `load_from_memory(context)` | Load relevant memories | `list[dict]` |
| `get_skills()` | Get agent's learned skills | `list[dict]` |
| `apply_skill(skill_name, board)` | Apply a skill to current position | `chess.Move` |

#### Agent Types

1. **MCP (Model Context Protocol)**
   - Uses MCP client to communicate with agent
   - Best for: Hermes Agent, Claude Code, custom MCP servers
   - Protocol: MCP over stdio or HTTP

2. **ACP (Agent Capability Protocol)**
   - Uses ACP for skill-based communication
   - Best for: Hermes Agent (native ACP support)
   - Protocol: ACP over HTTP

3. **Webhook**
   - Uses HTTP POST requests to agent endpoints
   - Best for: Custom agents, external systems
   - Protocol: HTTP/JSON

4. **Direct**
   - Direct LLM calls (existing behavior)
   - Best for: Local LLMs, simple agents
   - Protocol: Direct API calls

---

### 2. Agent Registry

#### Purpose
Central registry for managing agent states, memories, and skills.

#### Data Structures

```python
@dataclass
class AgentState:
    """Current state of an agent."""
    agent_id: str
    name: str
    agent_type: str
    status: str  # "idle", "thinking", "playing", "error"
    current_game: str | None
    last_activity: datetime
    

@dataclass  
class AgentMemory:
    """A single memory/experience entry."""
    memory_id: str
    agent_id: str
    game_id: str
    timestamp: datetime
    board_state: str  # FEN
    move: str  # UCI
    reasoning: str
    outcome: str  # "win", "loss", "draw", "unknown"
    lessons: list[str]
    tags: list[str]
    

@dataclass
class AgentSkill:
    """A learned chess skill."""
    skill_id: str
    agent_id: str
    name: str
    skill_type: str  # "opening", "tactic", "endgame", "pattern"
    description: str
    data: dict  # Skill-specific data
    success_rate: float
    usage_count: int
    created_at: datetime
    updated_at: datetime
```

#### Storage Backends

1. **JSON Files** (Default)
   - Simple, portable
   - Good for development and small-scale use
   - Files: `agents/{agent_id}/memory.json`, `agents/{agent_id}/skills.json`

2. **SQLite** (Recommended)
   - Better performance for large datasets
   - ACID compliance
   - File: `agents.db`

3. **PostgreSQL** (Optional)
   - For production deployments
   - Supports distributed systems

---

### 3. MCP Server

#### Purpose
Provides MCP interface for agent harnesses to interact with the chess system.

#### Endpoints

```python
# mcp_server.py

class ChessMCPServer:
    """MCP server for chess agent integration."""
    
    @mcp.tool()
    async def start_game(
        white_agent: str,
        black_agent: str,
        options: dict | None = None
    ) -> dict:
        """Start a new chess game between two agents."""
        pass
    
    @mcp.tool()
    async def get_game_state(game_id: str) -> dict:
        """Get current state of a game."""
        pass
    
    @mcp.tool()
    async def make_move(game_id: str, agent_id: str, move: str) -> dict:
        """Submit a move for an agent in a game."""
        pass
    
    @mcp.tool()
    async def get_agent_memory(agent_id: str, limit: int = 10) -> list:
        """Get recent memories for an agent."""
        pass
    
    @mcp.tool()
    async def save_agent_memory(
        agent_id: str,
        memory: dict
    ) -> bool:
        """Save a memory for an agent."""
        pass
    
    @mcp.tool()
    async def get_agent_skills(agent_id: str) -> list:
        """Get skills for an agent."""
        pass
    
    @mcp.tool()
    async def get_leaderboard(limit: int = 20) -> list:
        """Get ELO leaderboard."""
        pass
```

#### MCP Resources

```python
# Resources provide read-only access to data

@mcp.resource("chess://game/{game_id}")
async def get_game_resource(game_id: str) -> dict:
    """Get game resource with PGN, state, and metadata."""
    pass

@mcp.resource("chess://agent/{agent_id}/memory")
async def get_agent_memory_resource(agent_id: str) -> list:
    """Get all memories for an agent."""
    pass

@mcp.resource("chess://agent/{agent_id}/skills")
async def get_agent_skills_resource(agent_id: str) -> list:
    """Get all skills for an agent."""
    pass

@mcp.resource("chess://leaderboard")
async def get_leaderboard_resource() -> list:
    """Get current ELO leaderboard."""
    pass
```

#### Transport Options

1. **Stdio** (Default)
   - Standard input/output
   - Best for CLI integration
   - Command: `python mcp_server.py --transport stdio`

2. **HTTP**
   - REST API over HTTP
   - Best for remote agents
   - Command: `python mcp_server.py --transport http --port 8081`

3. **SSE** (Server-Sent Events)
   - Streaming updates
   - Best for real-time applications

---

### 4. ACP Integration

#### Purpose
Native integration with Hermes Agent's ACP (Agent Capability Protocol).

#### Skills

```python
# acp_skills.py

class ChessSkills:
    """ACP skills for chess agents."""
    
    @AgentOS.skill()
    async def play_chess_move(
        self,
        game_state: dict,
        agent_context: dict
    ) -> dict:
        """
        Analyze current board position and return best move.
        
        Args:
            game_state: {
                "board": "FEN string",
                "legal_moves": ["uci1", "uci2", ...],
                "history": ["move1", "move2", ...],
                "color": "white" | "black"
            }
            agent_context: Agent-specific context
            
        Returns:
            {
                "move": "uci string",
                "reasoning": "thought process",
                "confidence": 0.0-1.0,
                "alternatives": [{"move": "uci", "eval": float}]
            }
        """
        pass
    
    @AgentOS.skill()
    async def analyze_game(
        self,
        pgn: str,
        agent_id: str
    ) -> dict:
        """
        Analyze a completed game and extract lessons.
        
        Args:
            pgn: Game in PGN format
            agent_id: ID of the agent to learn from
            
        Returns:
            {
                "lessons": ["lesson1", "lesson2", ...],
                "critical_moves": [{"move": int, "eval": str, "lesson": str}],
                "opening": str,
                "outcome": str
            }
        """
        pass
    
    @AgentOS.skill()
    async def develop_skill(
        self,
        memories: list[dict],
        skill_type: str
    ) -> dict:
        """
        Develop a new skill from agent memories.
        
        Args:
            memories: List of memory entries
            skill_type: "opening" | "tactic" | "endgame" | "pattern"
            
        Returns:
            {
                "skill": AgentSkill,
                "memories_used": [str, ...],
                "coverage": float
            }
        """
        pass
```

---

### 5. Webhook Server

#### Purpose
HTTP API for agents that don't support MCP or ACP.

#### Endpoints

```python
# webhook_server.py

app = FastAPI(title="Chess Agent Webhooks")

@app.post("/webhook/chess/move")
async def receive_move(webhook_data: MoveRequest) -> MoveResponse:
    """
    Receive a move from an external agent.
    
    Request:
        {
            "agent_id": "unique-agent-id",
            "game_id": "game-uuid",
            "move": "e2e4",
            "reasoning": "I chose this move because...",
            "confidence": 0.95
        }
    
    Response:
        {
            "status": "accepted" | "rejected",
            "message": str,
            "game_state": dict | None
        }
    """
    pass

@app.post("/webhook/chess/game-start")
async def game_start(webhook_data: GameStartRequest) -> GameStartResponse:
    """Notify agent of game start."""
    pass

@app.post("/webhook/chess/game-complete")
async def game_complete(webhook_data: GameCompleteRequest) -> GameCompleteResponse:
    """
    Notify agent of game completion for learning.
    
    Request:
        {
            "agent_id": "unique-agent-id",
            "game_id": "game-uuid",
            "pgn": "1. e4 e5 2. Nf3...",
            "result": "1-0" | "0-1" | "1/2-1/2",
            "opponent": "agent-or-model-id"
        }
    
    Response:
        {
            "status": "learned",
            "lessons_learned": int,
            "skills_updated": int
        }
    """
    pass

@app.get("/webhook/chess/agent-state/{agent_id}")
async def get_agent_state(agent_id: str) -> AgentState:
    """Get current state of an agent."""
    pass
```

---

### 6. Learning System

#### Purpose
Enable agents to learn from their chess experiences.

#### Components

1. **Memory Extractor**
   - Extracts lessons from game PGN
   - Identifies critical moves (blunders, brilliant moves)
   - Categorizes experiences by opening, tactic type, etc.

2. **Skill Developer**
   - Clusters similar experiences
   - Extracts patterns and strategies
   - Creates reusable skills

3. **Performance Analyzer**
   - Tracks agent performance over time
   - Identifies strengths and weaknesses
   - Suggests improvement areas

#### Learning Pipeline

```
Game Completion
    │
    ▼
┌─────────────────┐
│ PGN Analysis     │
│ - Extract moves  │
│ - Identify phases│
│ - Detect patterns│
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Lesson Extraction│
│ - Critical moves │
│ - Tactical themes│
│ - Strategic errors│
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Memory Storage   │
│ - Save to agent  │
│ - Index by tags  │
│ - Update stats   │
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Skill Development│
│ - Cluster memories│
│ - Extract patterns│
│ - Create skills  │
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Performance      │
│ Update           │
│ - Update ELO     │
│ - Track progress │
│ - Generate reports│
└─────────────────┘
```

#### Lesson Extraction

```python
class LessonExtractor:
    """Extract lessons from chess games."""
    
    def extract_lessons(self, pgn: str, agent_color: str) -> list:
        """Extract lessons from a PGN game."""
        lessons = []
        
        # Parse PGN
        game = chess.pgn.read_game(pgn)
        board = game.board()
        
        # Analyze each move
        node = game
        move_number = 0
        while node.variations:
            move_number += 1
            move = node.variation[0]
            board.push(move.move)
            
            # Check for blunders (move that loses significant material)
            if self._is_blunder(board, move.move):
                lessons.append({
                    "type": "blunder",
                    "move": move_number,
                    "san": board.san(move.move),
                    "lesson": self._generate_blunder_lesson(board, move.move),
                    "severity": "high"
                })
            
            # Check for missed opportunities
            if self._has_better_move(board, move.move):
                better_move = self._find_better_move(board)
                lessons.append({
                    "type": "missed_opportunity",
                    "move": move_number,
                    "san": board.san(move.move),
                    "better_move": board.san(better_move),
                    "lesson": self._generate_opportunity_lesson(board, move.move, better_move),
                    "severity": "medium"
                })
            
            # Check for good moves
            if self._is_good_move(board, move.move):
                lessons.append({
                    "type": "good_move",
                    "move": move_number,
                    "san": board.san(move.move),
                    "lesson": self._generate_good_move_lesson(board, move.move),
                    "severity": "low"
                })
            
            node = node.variation[0]
        
        return lessons
```

#### Skill Types

1. **Opening Skills**
   - Specific opening sequences
   - Response to common openings
   - Opening principles

2. **Tactical Skills**
   - Forks, pins, skewers
   - Discovered attacks
   - Deflection
   - Zwischenzug

3. **Endgame Skills**
   - Basic checkmates (K+Q vs K, K+R vs K)
   - Pawn endgames
   - Rook endgames
   - Opposition

4. **Pattern Skills**
   - Common tactical patterns
   - Piece coordination
   - Weak square exploitation
   - Prophylaxis

---

## 🔌 Protocol Specifications

---

### MCP (Model Context Protocol)

#### Version
- MCP 2024-11-05 (latest stable)

#### Transport
- **Stdio**: Default for CLI integration
- **HTTP**: For remote agents (port 8081)

#### Server Capabilities

```json
{
  "name": "chess-llm-mcp",
  "version": "1.0.0",
  "capabilities": {
    "tools": [
      "start_game",
      "get_game_state", 
      "make_move",
      "get_agent_memory",
      "save_agent_memory",
      "get_agent_skills",
      "get_leaderboard"
    ],
    "resources": [
      "chess://game/{game_id}",
      "chess://agent/{agent_id}/memory",
      "chess://agent/{agent_id}/skills",
      "chess://leaderboard"
    ]
  }
}
```

#### Message Formats

**Request: start_game**
```json
{
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "start_game",
    "arguments": {
      "white_agent": "hermes-agent-1",
      "black_agent": "big-pickle",
      "options": {
        "delay": 1.0,
        "max_retries": 3
      }
    }
  }
}
```

**Response: start_game**
```json
{
  "id": 1,
  "result": {
    "content": [{
      "type": "text",
      "text": "Game started successfully"
    }],
    "tool_calls": null
  },
  "game_id": "game-uuid-here"
}
```

---

### ACP (Agent Capability Protocol)

#### Version
- ACP 1.0 (Hermes Agent compatible)

#### Skill Registration

```python
# Skills are registered with Hermes Agent
skills = [
    {
        "name": "play_chess_move",
        "description": "Analyze chess position and return best move",
        "parameters": {
            "type": "object",
            "properties": {
                "game_state": {
                    "type": "object",
                    "description": "Current game state"
                },
                "agent_context": {
                    "type": "object", 
                    "description": "Agent-specific context"
                }
            },
            "required": ["game_state"]
        },
        "returns": {
            "type": "object",
            "properties": {
                "move": {"type": "string"},
                "reasoning": {"type": "string"},
                "confidence": {"type": "number"}
            }
        }
    },
    {
        "name": "analyze_game",
        "description": "Analyze completed game and extract lessons",
        "parameters": {
            "type": "object",
            "properties": {
                "pgn": {"type": "string"},
                "agent_id": {"type": "string"}
            },
            "required": ["pgn", "agent_id"]
        },
        "returns": {
            "type": "object",
            "properties": {
                "lessons": {"type": "array"},
                "critical_moves": {"type": "array"}
            }
        }
    }
]
```

---

### Webhook Protocol

#### Content-Type
- `application/json`

#### Authentication
- Optional API key in header: `X-API-Key: your-key`
- Or agent ID in request body

#### Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhook/chess/move` | Submit a move |
| POST | `/webhook/chess/game-start` | Game started notification |
| POST | `/webhook/chess/game-complete` | Game completed notification |
| GET | `/webhook/chess/agent-state/{agent_id}` | Get agent state |
| GET | `/webhook/chess/agent-memory/{agent_id}` | Get agent memories |
| POST | `/webhook/chess/agent-memory/{agent_id}` | Save agent memory |

---

## 🎮 Game Flow with Agents

### Standard Game Flow

```
1. Game Initialization
   │
   ├─▶ MCP: start_game(white_agent, black_agent)
   ├─▶ ACP: AgentOS.start_game(...)
   └─▶ Webhook: POST /webhook/chess/game-start
   │
   ▼
2. Agent Registration
   │
   ├─▶ Register both agents in AgentRegistry
   ├─▶ Initialize agent states
   └─▶ Load agent memories/skills
   │
   ▼
3. Game Loop
   │
   ├─▶ For each move:
   │   ├─▶ Get current board state
   │   ├─▶ Send to current agent (via MCP/ACP/Webhook)
   │   │   ├─▶ MCP: make_move(game_id, agent_id, move)
   │   │   ├─▶ ACP: play_chess_move(game_state, context)
   │   │   └─▶ Webhook: POST /webhook/chess/move
   │   ├─▶ Validate move
   │   │   ├─▶ If valid: execute move
   │   │   └─▶ If invalid: request retry or constrain
   │   ├─▶ Save agent reasoning to memory
   │   └─▶ Check for game end conditions
   │
   ▼
4. Game Completion
   │
   ├─▶ Determine result (win/loss/draw)
   ├─▶ Update ELO ratings
   ├─▶ Save complete PGN
   ├─▶ Notify agents of completion
   │   ├─▶ MCP: game_complete notification
   │   ├─▶ ACP: analyze_game(pgn, agent_id)
   │   └─▶ Webhook: POST /webhook/chess/game-complete
   └─▶ Extract and save lessons
```

### Agent Decision Flow

```
Agent's Turn
    │
    ▼
┌─────────────────┐
│ Receive State    │ ← Game state (FEN, legal moves, history)
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Check Memory     │ ← Load relevant past experiences
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Check Skills     │ ← Load applicable skills
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Analyze Position│ ← Use LLM + memory + skills
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Select Move     │ ← Choose best move
└─────────┬────────┘
          │
          ▼
┌─────────────────┐
│ Return Move     │ → UCI move + reasoning
└─────────────────┘
```

---

## 🔧 Implementation Details

---

### File Structure

```
chess-llm/
├── chess_llm.py           # Existing main file (modified)
├── agents/
│   ├── __init__.py
│   ├── agent_player.py    # AgentPlayer class
│   ├── registry.py        # AgentRegistry
│   ├── memory.py          # Memory management
│   ├── skills.py          # Skill management
│   ├── learning.py        # Learning system
│   └── protocols/
│       ├── __init__.py
│       ├── mcp_server.py  # MCP server
│       ├── acp_skills.py  # ACP skills
│       └── webhook_server.py  # Webhook server
├── mcp_server.py          # Standalone MCP server entry
├── webhook_server.py      # Standalone webhook server entry
├── agent_cli.py           # CLI for agent management
├── AGENT_INTEGRATION_SPEC.md  # This file
└── ...
```

---

### Dependencies

#### Required
```
# Core
chess>=1.11
litellm>=1.80
openai>=2.0

# MCP
mcp>=1.0.0

# Webhooks
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
httpx>=0.24.0

# ACP (Hermes)
hermes-agent>=0.1.0  # Optional, for ACP support
```

#### Optional
```
# Database
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0  # For PostgreSQL

# Analytics
pandas>=2.0.0
numpy>=1.24.0

# Testing
pytest>=7.0.0
pytest-asyncio>=0.21.0
```

---

### Configuration

#### Environment Variables

```bash
# Agent settings
CHESS_AGENT_REGISTRY_PATH="./agents"  # Path to agent data
CHESS_AGENT_DB="sqlite:///agents.db"  # Database URL
CHESS_MCP_PORT=8081                    # MCP server port
CHESS_WEBHOOK_PORT=8082               # Webhook server port
CHESS_MCP_TRANSPORT="stdio"          # stdio, http, sse

# Learning settings
CHESS_LEARNING_ENABLED=true
CHESS_MEMORY_MAX_ENTRIES=1000
CHESS_SKILL_MIN_USAGE=3

# Compatibility
CHESS_OPENCODE_ENABLED=true
CHESS_HERMES_ENABLED=true
CHESS_VIBE_ENABLED=true
```

#### Configuration File

```yaml
# config/agents.yaml
registry:
  path: ./agents
  db_url: sqlite:///agents.db
  
mcp:
  port: 8081
  transport: stdio  # stdio, http, sse
  host: 0.0.0.0
  
webhook:
  port: 8082
  host: 0.0.0.0
  api_key: optional-key-for-auth
  
learning:
  enabled: true
  max_memory_entries: 1000
  skill_min_usage: 3
  auto_analyze: true
  
compatibility:
  opencode: true
  hermes: true
  vibe: true
  
agents:
  # Pre-registered agents
  hermes-chess:
    type: mcp
    endpoint: http://localhost:8081
    
  vibe-chess:
    type: webhook
    endpoint: http://localhost:8082
    
  opencode-agent:
    type: direct
    model: bigpickle/big-pickle
```

---

## 🎯 Compatibility Specifications

---

### OpenCode Compatibility

#### Integration Points
1. **Big Pickle Proxy** - Already integrated with chess-llm
2. **OpenCode Go/Zen** - Direct API access
3. **Agent as OpenCode Model** - Agents can be treated as models

#### Usage Examples

```bash
# Agent vs Big Pickle (via proxy)
python chess_llm.py -w mcp:hermes-agent -b bigpickle/big-pickle

# Agent vs OpenCode Go model
python chess_llm.py -w mcp:hermes-agent -b opencode-go/deepseek-v4-pro

# Tournament with agents and models
python tournament.py --round-robin mcp:hermes-agent bigpickle/big-pickle opencode-go/kimi-k2.5
```

#### OpenCode-Specific Features
- Automatic token bumping for reasoning models
- UUID authentication handling
- Tool call pass-through
- Streaming support

---

### Hermes Agent Compatibility

#### Integration Points
1. **ACP Skills** - Native skill registration
2. **MCP Client** - Hermes can connect to our MCP server
3. **Memory System** - Hermes auto-saves routines as skills

#### Usage Examples

```python
# In Hermes Agent configuration
from chess_llm.agents.protocols.acp_skills import ChessSkills

# Register chess skills
agent = AgentOS()
chess_skills = ChessSkills()
agent.register_skills(chess_skills)

# Connect to MCP server
agent.connect_mcp("chess-llm-mcp", port=8081)
```

#### Hermes-Specific Features
- Automatic skill saving from routines
- Memory persistence
- Multi-agent coordination
- Tool calling support

#### Example Hermes Agent

```yaml
# hermes_config.yaml
name: ChessMaster
model: big-pickle
description: A chess-playing agent that learns from experience

skills:
  - chess_llm.agents.protocols.acp_skills:ChessSkills

mcp_servers:
  - name: chess-llm
    port: 8081
    
memory:
  enabled: true
  persistence: true
  
learning:
  enabled: true
  auto_commit: true
```

---

### Vibe CLI Compatibility

#### Integration Points
1. **MCP Server** - Vibe can connect to our MCP server
2. **Webhook Endpoints** - Vibe can call webhook endpoints
3. **Direct Integration** - Vibe can use chess-llm as a tool

#### Usage Examples

```bash
# Connect Vibe to chess-llm MCP server
vibe --mcp-server chess-llm:8081

# Use chess-llm tools in Vibe
vibe> Use the chess tool to start a game between agent-a and agent-b
```

#### Vibe-Specific Features
- Natural language chess commands
- Agent coordination
- Learning from conversations
- Multi-modal support (board visualization)

#### Example Vibe Commands

```
# Start a game
"Start a chess game between my agent and Stockfish"

# Make a move
"My agent should play e4 in game game-uuid"

# Analyze a game
"What lessons can my agent learn from the last game?"

# Get leaderboard
"Show me the chess ELO leaderboard"
```

---

## 🧪 Testing Strategy

---

### Unit Tests

```python
# tests/test_agent_player.py

class TestAgentPlayer:
    async def test_mcp_agent_move(self):
        """Test that MCP agent can make a move."""
        agent = AgentPlayer("test-agent", agent_type="mcp")
        board = chess.Board()
        move = await agent.get_move(board, "")
        assert move in board.legal_moves
    
    async def test_webhook_agent_move(self):
        """Test that webhook agent can make a move."""
        agent = AgentPlayer("test-agent", agent_type="webhook")
        board = chess.Board()
        move = await agent.get_move(board, "")
        assert move in board.legal_moves
    
    async def test_agent_memory(self):
        """Test agent memory saving and loading."""
        agent = AgentPlayer("test-agent")
        board = chess.Board()
        
        # Save a memory
        agent.save_to_memory(
            board.fen(),
            "e2e4",
            "I chose e4 because it controls the center"
        )
        
        # Load memories
        memories = agent.load_from_memory(board.fen())
        assert len(memories) > 0
```

### Integration Tests

```python
# tests/test_integration.py

class TestAgentIntegration:
    async def test_mcp_server(self):
        """Test MCP server with a real agent."""
        # Start MCP server
        server = ChessMCPServer(port=8083)
        await server.start()
        
        # Connect client
        client = MCPClient(port=8083)
        
        # Start a game
        result = await client.call_tool("start_game", {
            "white_agent": "test-agent-1",
            "black_agent": "test-agent-2"
        })
        
        assert result["status"] == "started"
        await server.stop()
    
    async def test_full_game(self):
        """Test a complete game between two agents."""
        white = AgentPlayer("white-agent", agent_type="mcp")
        black = AgentPlayer("black-agent", agent_type="webhook")
        
        match = ChessMatch(white, black, delay=0)
        result = match.play()
        
        assert result in ["1-0", "0-1", "1/2-1/2"]
        assert match.pgn is not None
```

### End-to-End Tests

```bash
# Test MCP integration
python -m pytest tests/test_mcp_integration.py -v

# Test webhook integration  
python -m pytest tests/test_webhook_integration.py -v

# Test full tournament with agents
python tournament.py --round-robin mcp:agent1 mcp:agent2 --delay 0
```

---

## 📊 Monitoring & Observability

---

### Metrics

```python
# metrics.py

class AgentMetrics:
    """Track agent performance metrics."""
    
    def __init__(self):
        self.counters = {}
        self.gauges = {}
        self.histograms = {}
    
    def track_move(self, agent_id: str, move_time: float, success: bool):
        """Track a move execution."""
        self.counters[f"{agent_id}:moves:total"] += 1
        if success:
            self.counters[f"{agent_id}:moves:success"] += 1
        else:
            self.counters[f"{agent_id}:moves:failed"] += 1
        self.histograms[f"{agent_id}:move_time"].record(move_time)
    
    def track_game(self, agent_id: str, result: str, duration: float):
        """Track a game result."""
        self.counters[f"{agent_id}:games:total"] += 1
        self.counters[f"{agent_id}:games:{result}"] += 1
        self.gauges[f"{agent_id}:games:duration"].set(duration)
    
    def get_stats(self, agent_id: str) -> dict:
        """Get statistics for an agent."""
        return {
            "moves": {
                "total": self.counters.get(f"{agent_id}:moves:total", 0),
                "success": self.counters.get(f"{agent_id}:moves:success", 0),
                "failed": self.counters.get(f"{agent_id}:moves:failed", 0),
            },
            "games": {
                "total": self.counters.get(f"{agent_id}:games:total", 0),
                "wins": self.counters.get(f"{agent_id}:games:1-0", 0),
                "losses": self.counters.get(f"{agent_id}:games:0-1", 0),
                "draws": self.counters.get(f"{agent_id}:games:1/2-1/2", 0),
            }
        }
```

### Logging

```python
# logging_config.py

import logging
import sys

# Agent-specific logger
agent_logger = logging.getLogger("chess.agents")
agent_logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler("agents.log")
file_handler.setLevel(logging.DEBUG)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Format
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

agent_logger.addHandler(file_handler)
agent_logger.addHandler(console_handler)
```

### Health Checks

```python
# health.py

class HealthChecker:
    """Health checks for agent system."""
    
    async def check_mcp_server(self, port: int) -> bool:
        """Check if MCP server is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:{port}/health")
                return response.status_code == 200
        except Exception:
            return False
    
    async def check_webhook_server(self, port: int) -> bool:
        """Check if webhook server is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:{port}/health")
                return response.status_code == 200
        except Exception:
            return False
    
    async def check_agent(self, agent_id: str) -> bool:
        """Check if an agent is responsive."""
        try:
            agent = AgentRegistry.get(agent_id)
            return await agent.check_connectivity()
        except Exception:
            return False
```

---

## 🚀 Deployment

---

### Local Development

```bash
# Clone and setup
git clone https://github.com/luluthehermeticcrabBot/chess-llm.git
cd chess-llm
uv pip install -e .
uv pip install mcp fastapi uvicorn httpx

# Start MCP server
python mcp_server.py --port 8081

# Start webhook server (in another terminal)
python webhook_server.py --port 8082

# Run a game with agents
python chess_llm.py -w mcp:hermes-agent -b bigpickle/big-pickle
```

### Docker Deployment

```yaml
# docker-compose.yml
version: '3.8'

services:
  chess-llm:
    build: .
    ports:
      - "8081:8081"  # MCP server
      - "8082:8082"  # Webhook server
    volumes:
      - ./agents:/app/agents
      - ./games:/app/games
    environment:
      - CHESS_MCP_PORT=8081
      - CHESS_WEBHOOK_PORT=8082
      - CHESS_AGENT_DB=sqlite:///agents.db
    
  bigpickle-proxy:
    image: bigpickle-proxy
    ports:
      - "8000:8000"
    # Connects to OpenCode cloud
    
  hermes-agent:
    image: hermes-agent
    ports:
      - "8083:8083"
    environment:
      - HERMES_MCP_SERVERS=chess-llm:8081
```

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-agent.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-agent.txt

# Copy source code
COPY . .

# Create directories
RUN mkdir -p agents games .logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CHESS_MCP_PORT=8081
ENV CHESS_WEBHOOK_PORT=8082
ENV CHESS_AGENT_DB=sqlite:///agents.db

# Expose ports
EXPOSE 8081 8082

# Command
CMD ["python", "mcp_server.py", "--port", "8081"]
```

---

## 📚 Documentation

---

### User Documentation

1. **Getting Started Guide**
   - Installation
   - Basic usage
   - Agent registration

2. **Agent Development Guide**
   - Creating custom agents
   - MCP integration
   - ACP integration
   - Webhook integration

3. **Learning System Guide**
   - How agents learn
   - Memory format
   - Skill development
   - Performance tracking

4. **Tournament Guide**
   - Running agent tournaments
   - ELO tracking
   - Leaderboards

### API Documentation

1. **MCP API Reference**
   - Tools
   - Resources
   - Message formats

2. **Webhook API Reference**
   - Endpoints
   - Request/response formats
   - Authentication

3. **ACP Skill Reference**
   - Available skills
   - Parameters
   - Return values

---

## 🎓 Examples

---

### Example 1: Simple MCP Agent

```python
# simple_agent.py
from mcp.client import Client
import chess

class SimpleChessAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.client = Client(port=8081)
    
    async def get_move(self, game_state: dict) -> dict:
        """Get a move for the current position."""
        board = chess.Board(game_state["fen"])
        
        # Simple strategy: pick first legal move
        legal_moves = list(board.legal_moves)
        move = legal_moves[0]
        
        return {
            "move": move.uci(),
            "reasoning": f"Chose {move.uci()} as the first legal move",
            "confidence": 0.5
        }
    
    async def play_game(self, game_id: str):
        """Play a complete game."""
        # Connect to MCP server
        await self.client.connect()
        
        # Get game state
        state = await self.client.get_resource(f"chess://game/{game_id}")
        
        # Make move
        move = await self.get_move(state)
        
        # Submit move
        result = await self.client.call_tool("make_move", {
            "game_id": game_id,
            "agent_id": self.agent_id,
            "move": move["move"],
            "reasoning": move["reasoning"]
        })
        
        return result
```

### Example 2: Learning Agent with Hermes

```python
# hermes_chess_agent.py
from hermes_agent import AgentOS
from chess_llm.agents.protocols.acp_skills import ChessSkills

class HermesChessAgent:
    def __init__(self):
        self.agent = AgentOS(
            name="ChessMaster",
            model="big-pickle",
            description="A chess agent that learns from experience"
        )
        
        # Register chess skills
        self.chess_skills = ChessSkills()
        self.agent.register_skills(self.chess_skills)
        
        # Connect to MCP server
        self.agent.connect_mcp("chess-llm", port=8081)
    
    async def play_and_learn(self, opponent: str):
        """Play a game and learn from it."""
        # Start game
        game_id = await self.agent.call_tool("start_game", {
            "white_agent": "ChessMaster",
            "black_agent": opponent
        })
        
        # Wait for game to complete
        result = await self.agent.wait_for_game_completion(game_id)
        
        # Analyze game
        pgn = await self.agent.call_tool("get_game_pgn", {"game_id": game_id})
        lessons = await self.chess_skills.analyze_game(pgn, "ChessMaster")
        
        # Save lessons to memory
        for lesson in lessons["lessons"]:
            await self.agent.memory.commit(lesson)
        
        return result
```

### Example 3: Webhook Agent

```python
# webhook_agent.py
from fastapi import FastAPI, Request
import chess
import httpx

app = FastAPI()

@app.post("/chess/move")
async def make_move(request: Request):
    """Receive move request from chess-llm."""
    data = await request.json()
    
    game_id = data["game_id"]
    agent_id = data["agent_id"]
    game_state = data["game_state"]
    
    # Analyze position
    board = chess.Board(game_state["fen"])
    
    # Simple strategy: pick a random legal move
    import random
    legal_moves = list(board.legal_moves)
    move = random.choice(legal_moves)
    
    # Return move
    return {
        "status": "accepted",
        "move": move.uci(),
        "reasoning": f"Randomly selected {move.uci()}",
        "confidence": 0.3
    }

@app.post("/chess/game-complete")
async def game_complete(request: Request):
    """Receive game completion notification."""
    data = await request.json()
    
    game_id = data["game_id"]
    pgn = data["pgn"]
    result = data["result"]
    
    # Learn from game (simple implementation)
    print(f"Game {game_id} completed with result: {result}")
    print(f"PGN: {pgn}")
    
    return {"status": "learned", "lessons_learned": 0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
```

---

## 🔮 Future Enhancements

---

### Phase 2 Features

1. **Agent Teams**
   - Multiple agents collaborating on a single game
   - Role specialization (opener, tactician, endgame specialist)
   - Voting systems for move selection

2. **Advanced Learning**
   - Reinforcement learning integration
   - Neural network training from agent experiences
   - Transfer learning between agents

3. **Human-Agent Collaboration**
   - Agents assist human players
   - Human feedback for agent learning
   - Interactive learning sessions

4. **Multi-Modal Support**
   - Board visualization for agents
   - Voice input/output
   - Video analysis of physical boards

### Phase 3 Features

1. **Agent Marketplace**
   - Share agents with the community
   - Rate and review agents
   - Download pre-trained agents

2. **Competitive Ladder**
   - Global ELO rankings
   - Seasonal tournaments
   - Prizes and recognition

3. **Agent Personalities**
   - Different playing styles
   - Adaptive personalities
   - Emotional responses

4. **Cross-Game Learning**
   - Apply chess skills to other games
   - General game-playing intelligence
   - Transferable strategies

---

## 📞 Support & Community

---

### Getting Help

1. **Documentation**: [Link to docs]
2. **Issues**: GitHub Issues
3. **Discussions**: GitHub Discussions
4. **Discord**: [Discord server]

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

### Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/).

---

## 📄 License

MIT License - See LICENSE file for details.

---

## 🏁 Conclusion

This specification provides a comprehensive blueprint for integrating agent harnesses with the LLM Chess system. The modular architecture, multiple protocol support, and learning capabilities will enable a rich ecosystem of chess-playing agents that can compete, learn, and improve over time.

The implementation will proceed in phases, with the core functionality (AgentPlayer, MCP server, basic learning) delivered first, followed by advanced features like skill development and tournament integration.

---

**Document Version**: 1.0.0  
**Last Updated**: 2025-01-XX  
**Status**: Draft (Pending Implementation)  
