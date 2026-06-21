# 🎯 Agent Integration - Usage Examples

This document provides practical examples of how to use the agent integration system with LLM Chess.

---

## 📋 Table of Contents

1. [Quick Start](#-quick-start)
2. [AgentPlayer Examples](#-agentplayer-examples)
3. [MCP Server Examples](#-mcp-server-examples)
4. [Webhook Server Examples](#-webhook-server-examples)
5. [Hermes Agent Integration](#-hermes-agent-integration)
6. [OpenCode Integration](#-opencode-integration)
7. [Vibe CLI Integration](#-vibe-cli-integration)
8. [Learning System Examples](#-learning-system-examples)
9. [Tournament with Agents](#-tournament-with-agents)

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Install core dependencies
pip install chess fastapi uvicorn httpx

# Install MCP (optional, for MCP server)
pip install mcp

# Install Hermes Agent (optional, for ACP)
pip install hermes-agent
```

### 2. Start the Servers

```bash
# Start MCP server (port 8081)
python mcp_server.py --port 8081

# Start webhook server (port 8082)
python webhook_server.py --port 8082
```

### 3. Run a Game with Agents

```bash
# Direct agent (uses LLM)
python chess_llm.py -w direct:big-pickle -b stockfish

# MCP agent
python chess_llm.py -w mcp:hermes-agent -b bigpickle/big-pickle

# Webhook agent
python chess_llm.py -w webhook:http://localhost:8082/my-agent -b random
```

---

## 🎮 AgentPlayer Examples

### Basic Usage

```python
from agents.agent_player import AgentPlayer
import chess

# Create an agent player
agent = AgentPlayer(
    agent_id="my-chess-agent",
    name="My Chess Agent",
    agent_type="direct",  # Uses LLM directly
    model="big-pickle",
    learn=True  # Enable learning from games
)

# Use in a game
from chess_llm import ChessMatch, StockfishPlayer

stockfish = StockfishPlayer(skill_level=20)
match = ChessMatch(agent, stockfish, delay=1.0)

# Play the game
result = match.play()
print(f"Game result: {result}")

# Save the game
match.save_pgn("my_game.pgn")
```

### Different Agent Types

```python
# MCP Agent
mcp_agent = AgentPlayer(
    agent_id="mcp-agent",
    agent_type="mcp",
    endpoint="http://localhost:8081"
)

# Webhook Agent
webhook_agent = AgentPlayer(
    agent_id="webhook-agent",
    agent_type="webhook",
    endpoint="http://localhost:8082/chess"
)

# Direct LLM Agent
direct_agent = AgentPlayer(
    agent_id="llm-agent",
    agent_type="direct",
    model="opencode-go/deepseek-v4-pro",
    api_key="your-api-key"
)
```

### Agent with Custom Configuration

```python
agent = AgentPlayer(
    agent_id="custom-agent",
    name="Custom Agent",
    agent_type="direct",
    model="big-pickle",
    timeout=180,        # Longer timeout for reasoning models
    max_retries=5,      # More retries for illegal moves
    temperature=0.7,    # More creative
    use_tools=True,     # Use tool calling
    tiny=False,         # Full prompt
    reasoning="high",  # High reasoning effort
    constrain=True,     # Auto-correct illegal moves
    learn=True          # Enable learning
)
```

---

## 🔌 MCP Server Examples

### Starting the MCP Server

```bash
# Basic usage
python mcp_server.py

# Custom port
python mcp_server.py --port 8081

# Different transport
python mcp_server.py --transport stdio
python mcp_server.py --transport http

# With debug logging
python mcp_server.py --debug
```

### Using MCP Server with Python

```python
from agents.protocols.mcp_server import ChessMCPServer

# Create and start server
server = ChessMCPServer(port=8081, transport="http")
server.start()

# Keep running
try:
    while True:
        pass
except KeyboardInterrupt:
    server.stop()
```

### MCP Tools Available

The MCP server provides these tools:

| Tool | Description | Parameters |
|------|-------------|------------|
| `start_game` | Start a new chess game | `white_agent`, `black_agent`, `options` |
| `get_game_state` | Get game state | `game_id` |
| `make_move` | Make a move in a game | `game_id`, `agent_id`, `move` |
| `get_agent_memory` | Get agent memories | `agent_id`, `limit`, `game_id` |
| `save_agent_memory` | Save agent memory | `agent_id`, `memory` |
| `get_agent_skills` | Get agent skills | `agent_id`, `skill_type` |
| `get_leaderboard` | Get ELO leaderboard | `limit` |
| `list_games` | List active games | `agent_id`, `status` |
| `register_agent` | Register a new agent | `agent_id`, `name`, `agent_type`, etc. |
| `get_agent_state` | Get agent state | `agent_id` |

### MCP Resources Available

| Resource | Description |
|----------|-------------|
| `chess://game/{game_id}` | Game state and PGN |
| `chess://agent/{agent_id}/memory` | Agent memories |
| `chess://agent/{agent_id}/skills` | Agent skills |
| `chess://leaderboard` | ELO leaderboard |

### Example: MCP Client Usage

```python
import httpx
import json

# Start a game
response = httpx.post(
    "http://localhost:8081/tools/start_game",
    json={
        "arguments": {
            "white_agent": "my-agent",
            "black_agent": "big-pickle"
        }
    }
)

game_id = response.json()["game_id"]

# Get game state
response = httpx.post(
    f"http://localhost:8081/tools/get_game_state",
    json={"arguments": {"game_id": game_id}}
)

game_state = response.json()["game"]
print(f"Current FEN: {game_state['fen']}")

# Make a move
response = httpx.post(
    f"http://localhost:8081/tools/make_move",
    json={
        "arguments": {
            "game_id": game_id,
            "agent_id": "my-agent",
            "move": "e2e4"
        }
    }
)
```

---

## 🌐 Webhook Server Examples

### Starting the Webhook Server

```bash
# Basic usage
python webhook_server.py

# Custom port
python webhook_server.py --port 8082

# With API key authentication
python webhook_server.py --api-key my-secret-key

# With debug logging
python webhook_server.py --debug
```

### Webhook Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chess/move` | Submit a move |
| POST | `/chess/game-start` | Game started notification |
| POST | `/chess/game-complete` | Game completed notification |
| GET | `/chess/agent-state/{agent_id}` | Get agent state |
| GET | `/chess/agent-memory/{agent_id}` | Get agent memories |
| POST | `/chess/agent-memory/{agent_id}` | Save agent memory |
| GET | `/chess/agent-skills/{agent_id}` | Get agent skills |
| POST | `/chess/agent-skills/{agent_id}` | Save agent skill |
| POST | `/chess/register` | Register an agent |
| GET | `/chess/leaderboard` | Get leaderboard |
| GET | `/chess/agents` | List all agents |
| GET | `/health` | Health check |
| GET | `/capabilities` | Get server capabilities |

### Example: Simple Webhook Agent

```python
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
    
    # Simple strategy: pick first legal move
    legal_moves = list(board.legal_moves)
    move = legal_moves[0]
    
    # Return move
    return {
        "status": "accepted",
        "move": move.uci(),
        "reasoning": f"Chose {move.uci()} as the first legal move",
        "confidence": 0.5
    }

@app.post("/chess/game-start")
async def game_start(request: Request):
    """Game started notification."""
    data = await request.json()
    print(f"Game started: {data['game_id']}")
    return {"status": "notified"}

@app.post("/chess/game-complete")
async def game_complete(request: Request):
    """Game completed notification."""
    data = await request.json()
    print(f"Game completed: {data['game_id']} with result: {data['result']}")
    # Learn from the game
    pgn = data["pgn"]
    # ... analyze PGN and save lessons
    return {"status": "learned"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
```

### Example: Webhook Client Usage

```python
import httpx

# Register an agent
response = httpx.post(
    "http://localhost:8082/chess/register",
    json={
        "agent_id": "my-webhook-agent",
        "name": "My Webhook Agent",
        "agent_type": "webhook",
        "endpoint": "http://localhost:8082/chess"
    }
)

# Get agent state
response = httpx.get("http://localhost:8082/chess/agent-state/my-webhook-agent")
state = response.json()
print(f"Agent status: {state['status']}")

# Get leaderboard
response = httpx.get("http://localhost:8082/chess/leaderboard")
leaderboard = response.json()["leaderboard"]
print(f"Top player: {leaderboard[0]['name']}")
```

---

## 🤖 Hermes Agent Integration

### Setting Up Hermes Agent

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

### Using Hermes Agent with Chess-LLM

```python
from hermes_agent import AgentOS
from chess_llm.agents.protocols.acp_skills import ChessSkills

# Create Hermes agent
agent = AgentOS(
    name="ChessMaster",
    model="big-pickle",
    description="A chess agent that learns"
)

# Register chess skills
chess_skills = ChessSkills()
agent.register_skills(chess_skills)

# Connect to MCP server
agent.connect_mcp("chess-llm", port=8081)

# Now the agent can play chess using the play_chess_move skill
# The agent will automatically use the skill when appropriate
```

### Example: Hermes Agent Playing Chess

```python
from hermes_agent import AgentOS
from chess_llm.agents.protocols.acp_skills import ChessSkills
from chess_llm import ChessMatch, StockfishPlayer

# Create and configure Hermes agent
agent = AgentOS(name="ChessMaster", model="big-pickle")
chess_skills = ChessSkills()
agent.register_skills(chess_skills)
agent.connect_mcp("chess-llm", port=8081)

# Create AgentPlayer that uses Hermes
from agents.agent_player import AgentPlayer

hermes_player = AgentPlayer(
    agent_id="hermes-chess",
    name="Hermes Chess Agent",
    agent_type="acp",
    endpoint="http://localhost:8083"  # Hermes endpoint
)

# Play against Stockfish
stockfish = StockfishPlayer(skill_level=20)
match = ChessMatch(hermes_player, stockfish, delay=2.0)
result = match.play()

print(f"Game result: {result}")
```

---

## 🎓 OpenCode Integration

### Using Big Pickle Proxy

The Big Pickle Proxy is already integrated with chess-llm. You can use it directly:

```bash
# Start Big Pickle Proxy
cd bigpickle-proxy
python proxy.py --port 8000

# Play with Big Pickle models
python chess_llm.py -w bigpickle/big-pickle -b stockfish
python chess_llm.py -w bigpickle/deepseek-v4-flash-free -b random
```

### Using OpenCode Go/Zen Directly

```bash
# Set API key
export OPENCODE_GO_API_KEY=your-api-key

# Play with OpenCode Go models
python chess_llm.py -w opencode-go/deepseek-v4-pro -b opencode-go/kimi-k2.5

# Play with OpenCode Zen models (free)
python chess_llm.py -w opencode-zen/big-pickle -b opencode-zen/deepseek-v4-flash-free
```

### Agent with OpenCode Model

```python
from agents.agent_player import AgentPlayer

# Direct OpenCode agent
agent = AgentPlayer(
    agent_id="opencode-agent",
    name="OpenCode Agent",
    agent_type="direct",
    model="opencode-go/deepseek-v4-pro",
    api_key="your-api-key"
)

# Or via Big Pickle Proxy
agent = AgentPlayer(
    agent_id="bigpickle-agent",
    name="Big Pickle Agent",
    agent_type="direct",
    model="bigpickle/big-pickle"
)
```

---

## 💬 Vibe CLI Integration

### Connecting Vibe to MCP Server

```bash
# Start MCP server
python mcp_server.py --port 8081

# Connect Vibe to the MCP server
vibe --mcp-server chess-llm:8081
```

### Using Vibe with Chess-LLM

Once connected, you can use natural language commands:

```
# Start a game
"Start a chess game between my agent and Stockfish"

# Make a move
"My agent should play e4 in the current game"

# Get game state
"What's the current position in my game?"

# Analyze a game
"What lessons can my agent learn from the last game?"

# Get leaderboard
"Show me the chess ELO leaderboard"

# Get agent info
"Tell me about my chess agent"
```

### Example: Vibe Agent Script

```python
# This would be a Vibe skill/tool that integrates with chess-llm

from vibe_cli import Vibe

class ChessVibeAgent:
    def __init__(self):
        self.vibe = Vibe()
        self.vibe.connect_mcp("chess-llm", port=8081)
    
    def play_chess(self, opponent="stockfish", color="white"):
        """Play a chess game using Vibe."""
        # Start game via MCP
        result = self.vibe.call_tool("start_game", {
            "white_agent": "vibe-agent",
            "black_agent": opponent
        })
        
        game_id = result["game_id"]
        
        # Play moves
        while True:
            # Get game state
            state = self.vibe.call_tool("get_game_state", {"game_id": game_id})
            
            if state["game"]["status"] != "in_progress":
                break
            
            # Get move from Vibe (using LLM)
            move = self.vibe.ask(f"What should I play in this chess position? FEN: {state['game']['fen']}")
            
            # Make move via MCP
            self.vibe.call_tool("make_move", {
                "game_id": game_id,
                "agent_id": "vibe-agent",
                "move": move
            })
        
        return result
```

---

## 🧠 Learning System Examples

### Basic Learning from a Game

```python
from agents.learning import LearningSystem, get_learning_system
from agents.memory import reset_memory_manager

# Reset and get learning system
reset_memory_manager()
learning_system = get_learning_system()

# PGN from a completed game
pgn = """[Event "My Game"]
[White "My Agent"]
[Black "Stockfish"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6
"""

# Learn from the game
result = learning_system.learn_from_game(
    pgn=pgn,
    agent_id="my-agent",
    agent_color="white",
    result="1-0"
)

print(f"Lessons extracted: {result['lessons_extracted']}")
print(f"Skills developed: {result['skills_developed']}")
print(f"Memories saved: {result['memories_saved']}")
```

### Getting Learning Statistics

```python
# Get agent's learning stats
stats = learning_system.get_stats("my-agent")
print(f"Memories: {stats['memories_count']}")
print(f"Skills: {stats['skills_count']}")
print(f"Lessons: {stats['lessons_count']}")
print(f"Average confidence: {stats['average_confidence']:.2f}")
```

### Getting Learning Recommendations

```python
# Get personalized recommendations
recommendations = learning_system.get_recommendations("my-agent", limit=5)

for i, rec in enumerate(recommendations, 1):
    print(f"{i}. [{rec['priority']}] {rec['topic']}")
    print(f"   {rec['description']}")
    if rec['resources']:
        print(f"   Resources: {', '.join(rec['resources'])}")
```

### Querying Memories

```python
from agents.memory import get_memory_manager

memory_manager = get_memory_manager()

# Get all memories for an agent
memories = memory_manager.query(agent_id="my-agent")
print(f"Total memories: {len(memories)}")

# Get memories from a specific game
 game_memories = memory_manager.query(agent_id="my-agent", game_id="game-123")

# Get memories with specific tags
opening_memories = memory_manager.query(agent_id="my-agent", tag="opening")

# Find similar positions
board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 2")
similar = memory_manager.get_memory("my-agent").find_similar(board.fen())
print(f"Found {len(similar)} similar positions")
```

### Managing Skills

```python
from agents.skills import SkillManager

skill_manager = SkillManager("my-agent")

# Get all skills
skills = skill_manager.list_skills()
print(f"Total skills: {len(skills)}")

# Get skills by type
opening_skills = skill_manager.list_skills(skill_type="opening")
tactic_skills = skill_manager.list_skills(skill_type="tactic")

# Find applicable skills for current position
board = chess.Board()
board.push_san("e4")
board.push_san("e5")

applicable = skill_manager.find_applicable(board, "white", "opening")
for skill, relevance in applicable:
    print(f"{skill.name}: {relevance:.2f}")

# Apply a skill
if applicable:
    skill, relevance = applicable[0]
    move = skill_manager.apply_skill(skill, board, "white")
    print(f"Skill suggests: {move.uci()}")
```

---

## 🏆 Tournament with Agents

### Simple Agent Tournament

```python
from agents.agent_player import AgentPlayer
from chess_llm import ChessMatch

# Create agents
agent1 = AgentPlayer(
    agent_id="agent-1",
    name="Agent Alpha",
    agent_type="direct",
    model="big-pickle"
)

agent2 = AgentPlayer(
    agent_id="agent-2",
    name="Agent Beta",
    agent_type="direct",
    model="bigpickle/deepseek-v4-flash-free"
)

# Play a game
match = ChessMatch(agent1, agent2, delay=1.0)
result = match.play()

print(f"Result: {result}")
match.save_pgn("agent_tournament.pgn")

# Save game results for learning
agent1.save_game_result(result, match.pgn(), "agent-2")
agent2.save_game_result(
    "1-0" if result == "0-1" else "0-1" if result == "1-0" else "1/2-1/2",
    match.pgn(),
    "agent-1"
)
```

### Round-Robin Tournament

```python
from agents.agent_player import AgentPlayer
from chess_llm import ChessMatch
import itertools

# Create a list of agents
agents = [
    AgentPlayer(agent_id=f"agent-{i}", name=f"Agent {i}", 
                agent_type="direct", model="big-pickle")
    for i in range(1, 4)
]

# Play round-robin
results = {}
for white, black in itertools.combinations(agents, 2):
    # Play both colors
    for color_order in ["white", "black"]:
        if color_order == "white":
            match = ChessMatch(white, black, delay=0.5)
        else:
            match = ChessMatch(black, white, delay=0.5)
        
        result = match.play()
        results[(white.agent_id, black.agent_id)] = result
        
        # Save for learning
        if color_order == "white":
            white.save_game_result(result, match.pgn(), black.agent_id)
            black.save_game_result(
                "1-0" if result == "0-1" else "0-1" if result == "1-0" else "1/2-1/2",
                match.pgn(),
                white.agent_id
            )
        else:
            black.save_game_result(result, match.pgn(), white.agent_id)
            white.save_game_result(
                "1-0" if result == "0-1" else "0-1" if result == "1-0" else "1/2-1/2",
                match.pgn(),
                black.agent_id
            )

# Print results
print("Tournament Results:")
for (w, b), result in results.items():
    print(f"  {w} vs {b}: {result}")
```

### Using Tournament.py with Agents

```bash
# Tournament with agents and models
python tournament.py --round-robin \
    mcp:hermes-agent \
    bigpickle/big-pickle \
    opencode-go/deepseek-v4-pro \
    stockfish \
    --delay 0 \
    --elo

# Gauntlet: one agent vs multiple opponents
python tournament.py --gauntlet mcp:hermes-agent \
    --opponents bigpickle/big-pickle opencode-go/kimi-k2.5 stockfish \
    --delay 0
```

---

## 📚 Advanced Examples

### Custom Agent with Learning

```python
from agents.agent_player import AgentPlayer
from agents.learning import get_learning_system
from agents.memory import get_memory_manager
import chess

class LearningChessAgent(AgentPlayer):
    """Custom agent that learns from every game."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.learning_system = get_learning_system()
        self.memory_manager = get_memory_manager()
    
    def save_game_result(self, result: str, pgn: str, opponent: str):
        """Save game result and learn from it."""
        super().save_game_result(result, pgn, opponent)
        
        # Additional learning
        learning_result = self.learning_system.learn_from_game(
            pgn=pgn,
            agent_id=self.agent_id,
            agent_color=self._color or "white",
            result=result
        )
        
        print(f"Learning: {learning_result}")
        
        # Get recommendations
        recommendations = self.learning_system.get_recommendations(
            self.agent_id, limit=3
        )
        
        for rec in recommendations:
            print(f"Recommendation: {rec['topic']} - {rec['description']}")

# Use the custom agent
agent = LearningChessAgent(
    agent_id="learning-agent",
    name="Learning Agent",
    agent_type="direct",
    model="big-pickle",
    learn=True
)

# Play a game
from chess_llm import ChessMatch, StockfishPlayer
stockfish = StockfishPlayer(skill_level=20)
match = ChessMatch(agent, stockfish, delay=1.0)
result = match.play()

# Save and learn
agent.save_game_result(result, match.pgn(), "stockfish-20")
```

### Agent with Skill Application

```python
from agents.agent_player import AgentPlayer
from agents.skills import SkillManager
import chess

class SkillfulChessAgent(AgentPlayer):
    """Agent that tries to apply learned skills."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skill_manager = SkillManager(self.agent_id)
    
    def get_move(self, board: chess.Board, history_text: str) -> chess.Move:
        """Get move, trying to apply skills first."""
        # Try to apply a skill
        move = self.skill_manager.apply_skills(board)
        
        if move:
            # Found a skill to apply
            return move
        
        # Fall back to default behavior
        return super().get_move(board, history_text)

# Use the skillful agent
agent = SkillfulChessAgent(
    agent_id="skillful-agent",
    name="Skillful Agent",
    agent_type="direct",
    model="big-pickle",
    learn=True
)
```

### Multi-Agent Collaboration

```python
from agents.agent_player import AgentPlayer
from agents.registry import get_registry
import chess

class CollaborativeAgent(AgentPlayer):
    """Agent that consults with other agents."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = get_registry()
    
    def get_move(self, board: chess.Board, history_text: str) -> chess.Move:
        """Get move by consulting with other agents."""
        # Get our own move first
        our_move = super().get_move(board, history_text)
        
        # Consult with other agents (simplified example)
        # In production, this would query other agents via MCP/webhook
        other_agents = self.registry.list_agents()
        
        # For now, just return our move
        return our_move

# Create collaborative agents
agent1 = CollaborativeAgent(
    agent_id="collab-agent-1",
    name="Collaborative Agent 1",
    agent_type="direct",
    model="big-pickle"
)

agent2 = CollaborativeAgent(
    agent_id="collab-agent-2",
    name="Collaborative Agent 2",
    agent_type="direct",
    model="bigpickle/deepseek-v4-flash-free"
)
```

---

## 🎯 Best Practices

### 1. Agent Configuration

- **Use appropriate timeouts**: Reasoning models need more time (180-240s)
- **Set max_retries**: 3-5 retries is usually sufficient
- **Enable learning**: Set `learn=True` to enable memory and skill development
- **Use constrain mode**: Set `constrain=True` to auto-correct illegal moves

### 2. Performance Optimization

- **Use SQLite for production**: JSON files are good for development, but SQLite is better for production
- **Limit memory size**: Set `max_entries` to prevent memory bloat
- **Prune old memories**: Regularly clean up old or low-priority memories

### 3. Learning Strategies

- **Review games regularly**: Use `learning_system.learn_from_game()` after each game
- **Get recommendations**: Use `learning_system.get_recommendations()` to identify weaknesses
- **Focus on weaknesses**: Spend more time studying areas where the agent struggles

### 4. Agent Types

| Agent Type | Best For | Pros | Cons |
|------------|----------|------|------|
| Direct | Simple agents, local LLMs | Easy to set up, full control | Requires LLM API |
| MCP | Hermes, Claude Code, Vibe | Standard protocol, rich features | Requires MCP server |
| Webhook | Custom agents, external systems | Flexible, any language | Requires HTTP server |
| ACP | Hermes Agent | Native integration, skills | Hermes-specific |

---

## 📖 API Reference

### AgentPlayer

```python
AgentPlayer(
    agent_id: str,
    name: Optional[str] = None,
    agent_type: str = "mcp",  # "mcp", "acp", "webhook", "direct"
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 120,
    max_retries: int = 3,
    use_tools: bool = True,
    temperature: float = 0.3,
    tiny: bool = False,
    reasoning: Optional[str] = None,
    constrain: bool = False,
    learn: bool = True
)
```

**Methods:**
- `get_move(board, history_text) -> chess.Move`
- `check_connectivity() -> bool`
- `save_game_result(result, pgn, opponent)`
- `get_skills() -> list[AgentSkill]`
- `apply_skills(board) -> Optional[chess.Move]`
- `close()`

### AgentRegistry

```python
registry = AgentRegistry(storage_path="agents", use_sqlite=True)
```

**Methods:**
- `register_agent(agent_id, name, agent_type, ...)`
- `unregister_agent(agent_id)`
- `get_agent(agent_id) -> Optional[AgentConfig]`
- `get_state(agent_id) -> Optional[AgentState]`
- `update_state(agent_id, status, current_game, ...)`
- `list_agents(agent_type=None) -> list[AgentConfig]`
- `clear()`

### MemoryManager

```python
memory_manager = MemoryManager(storage_path="agents", use_sqlite=True)
```

**Methods:**
- `save(agent_id, board_state, move, reasoning, ...)`
- `get(memory_id) -> Optional[MemoryEntry]`
- `query(agent_id, board_state, game_id, ...) -> list[MemoryEntry]`
- `find_similar(board_state, threshold=0.8, limit=10) -> list[tuple[MemoryEntry, float]]`
- `clear()`

### SkillManager

```python
skill_manager = SkillManager(agent_id, storage_path="agents", use_sqlite=True)
```

**Methods:**
- `save(skill) -> str`
- `get(skill_id) -> Optional[AgentSkill]`
- `list_skills(skill_type=None, tag=None) -> list[AgentSkill]`
- `find_applicable(board, color, phase) -> list[tuple[AgentSkill, float]]`
- `apply_skill(skill, board, color) -> Optional[chess.Move]`
- `update_success(skill_id, success)`
- `clear()`

### LearningSystem

```python
learning_system = LearningSystem()
```

**Methods:**
- `learn_from_game(pgn, agent_id, agent_color, result) -> dict`
- `get_stats(agent_id) -> dict`
- `get_recommendations(agent_id, limit=5) -> list[dict]`
- `review_memory(memory_id, agent_id, feedback) -> bool`

---

## 🎓 Troubleshooting

### Common Issues

1. **Import Errors**
   - Make sure all dependencies are installed: `pip install chess fastapi uvicorn httpx`
   - For MCP: `pip install mcp`
   - For Hermes: `pip install hermes-agent`

2. **Connection Errors**
   - Check that servers are running: `python mcp_server.py`, `python webhook_server.py`
   - Verify ports are not blocked
   - Check API keys for direct agents

3. **Illegal Moves**
   - Enable `constrain=True` to auto-correct illegal moves
   - Increase `max_retries` for more attempts
   - Check that the model supports the chess task

4. **Memory Issues**
   - Use SQLite for better performance with many memories
   - Limit `max_entries` to prevent memory bloat
   - Regularly prune old memories

5. **Learning Issues**
   - Make sure `learn=True` is set on the agent
   - Verify that `save_game_result()` is called after each game
   - Check that the PGN is valid

### Debug Mode

Enable debug mode for more information:

```bash
# MCP server with debug
python mcp_server.py --debug

# Webhook server with debug
python webhook_server.py --debug

# Set environment variable for agent debug
export CHESS_AGENT_DEBUG=1
```

---

## 📚 Additional Resources

- [Chess-LLM Documentation](README.md)
- [Agent Integration Specification](AGENT_INTEGRATION_SPEC.md)
- [MCP Protocol](https://github.com/modelcontextprotocol/python-sdk)
- [Hermes Agent](https://github.com/hermes-agent/hermes)
- [OpenCode](https://opencode.ai/)
- [Vibe CLI](https://github.com/vibe-ai/vibe-cli)

---

## 🏁 Conclusion

The agent integration system provides a powerful framework for:

1. **Playing chess** with various agent types (MCP, ACP, Webhook, Direct)
2. **Learning from experience** through memory and skill systems
3. **Competing in tournaments** against other agents and models
4. **Integrating with popular agent frameworks** (Hermes, OpenCode, Vibe CLI)

The examples in this document should help you get started with building your own chess-playing agents that can learn and improve over time!
