# ♟ LLM Chess

Pit language models against each other — or against humans, Stockfish and random players — in a game of chess. Every game auto-saves as a standard PGN file. Tournaments (round-robin or gauntlet) can track ELO ratings and show a live terminal UI.

## Quickstart

```bash
# Install (uv recommended; pip works too)
uv pip install -e .

# Set API keys for the providers you use
export OPENCODE_GO_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-v1-...

# Play!
python chess_llm.py --white opencode-go/deepseek-v4-pro --black stockfish
```

## Players

A player spec is one of the following (also accepted by `tournament.py`):

| Spec | Description |
|---|---|
| `opencode-go/model` | OpenCode Go API (`$OPENCODE_GO_API_KEY`) |
| `opencode-zen/model` | OpenCode Zen API (`$OPENCODE_ZEN_API_KEY`) |
| `openrouter/model` | OpenRouter API (`$OPENROUTER_API_KEY`) |
| `openai/model` | OpenAI API (`$OPENAI_API_KEY`) |
| `anthropic/model` | Anthropic API via litellm (`$ANTHROPIC_API_KEY`) |
| `groq/model` | Groq API via litellm (`$GROQ_API_KEY`) |
| `ollama/model` | Local Ollama, `http://localhost:11434/v1` (no key) |
| `llama-cpp/model` | Local `llama-server`, `http://localhost:8080/v1` (no key) |
| `docker/ai/model` | Docker Model Runner, `http://localhost:12434/engines/v1` (no key) |
| `bigpickle/model` | Local Big Pickle proxy, `http://localhost:8000/v1` (no key) |
| `stockfish`, `stockfish:N` | Stockfish engine, skill `N` 0–20 (default 20) |
| `human`, `human:NAME` | Terminal input (SAN or UCI notation) |
| `random` | Random legal moves (baseline) |
| `@preset` | Named model from `models.yaml` (see below) |
| `model?key=val&key=val` | Inline per-model flags, e.g. `?retries=5&tiny=true` |

Any other OpenAI-compatible endpoint works through `openai/model` plus `--api-base` and `--api-key` (see [Custom endpoints](#custom-endpoints)).

Unknown `@presets` or `?flags` are errors (exit code 2), not model names.

## Model presets (`models.yaml`)

`models.yaml` in the repo root defines named presets and global `defaults:`. Reference them with `@name`:

```bash
python chess_llm.py -w @qwen3-local -b @stockfish-0
python tournament.py --round-robin @qwen3-local @big-pickle @stockfish-10
```

Flags you can set in a preset or inline (`?key=val`): `use_tools`/`tools`, `tiny`, `max_retries`/`retries`, `temperature`/`temp`, `timeout`, `reasoning` (`low`/`medium`/`high`/`none`), `constrain`.

Merge priority, lowest to highest: `defaults:` → named preset → inline `?key=val` → `--white-flags` / `--black-flags` / `--model-flags`.

## Usage

### Single game (`chess_llm.py`)

```bash
# LLM vs LLM
python chess_llm.py --white opencode-go/deepseek-v4-pro --black openrouter/anthropic/claude-sonnet-4

# Same model both sides
python chess_llm.py --model opencode-go/deepseek-v4-pro

# Human vs Stockfish
python chess_llm.py --white human --black stockfish

# Local model with per-player flags
python chess_llm.py -w llama-cpp/my-model --white-flags "tiny=true,retries=10" -b stockfish:10

# Speed mode — no delay between moves
python chess_llm.py --model opencode-go/deepseek-v4-pro --delay 0

# Debug mode — see model responses
LLM_CHESS_DEBUG=1 python chess_llm.py --model opencode-go/deepseek-v4-pro

# Tee output to .logs/
python chess_llm.py --model opencode-go/deepseek-v4-pro --log

# Show the ELO leaderboard and exit
python chess_llm.py --leaderboard
```

### Tournaments (`tournament.py`)

```bash
# Round-robin, both colors, ELO tracking, 2 games per pair
python tournament.py --round-robin @qwen3-local @big-pickle stockfish:5 --elo --games 2

# Gauntlet: one champion against several opponents
python tournament.py --gauntlet @big-pickle --opponents @qwen3-local stockfish:10 --elo

# Run 4 games at once, resume an interrupted run
python tournament.py --round-robin @qwen3-local @big-pickle --parallel 4 --elo
python tournament.py --round-robin @qwen3-local @big-pickle --resume

# Force decisive games with unbalanced opening positions
python tournament.py --round-robin stockfish:5 stockfish:10 --openings unbalanced
```

Tournament PGNs go to `games/`, one file per game. ELO ratings go to `ratings.json` (`--elo-db` to change the path).

All games auto-save as PGN in `./games/` — load them in Lichess or Chess.com for analysis.

## Flags

### `chess_llm.py`

| Flag | Default | Description |
|---|---|---|
| `--white`, `-w` | `opencode-go/deepseek-v4-pro` | White player spec |
| `--black`, `-b` | `opencode-go/deepseek-v4-pro` | Black player spec |
| `--model`, `-m` | — | Same model for both sides |
| `--delay`, `-d` | `1.0` | Seconds between moves (`0` = max speed) |
| `--no-tools` | off | Disable tool calling, parse moves from text |
| `--tiny` | off | Compact UCI-only prompt for models under ~20B |
| `--constrain` | off | When a proposed move is illegal, play the closest legal move instead of retrying or forfeiting |
| `--reasoning` | — | Reasoning effort (`low`/`medium`/`high`/`none`), provider support varies |
| `--retries`, `-r` | `3` | Illegal-move retries before forfeit |
| `--timeout` | `120` | API timeout in seconds |
| `--temperature`, `-t` | `0.3` | LLM temperature |
| `--white-flags`, `--black-flags` | — | Per-player `key=val,key=val` model flags |
| `--pgn`, `-p` | auto | PGN output path |
| `--log`, `-l` | off | Tee output to `.logs/game_<timestamp>.txt` (or give a path) |
| `--elo` | off | Update ratings in `ratings.json` after the game |
| `--elo-db` | `ratings.json` | Ratings file |
| `--leaderboard`, `-L` | — | Print the ELO leaderboard and exit |
| `--stockfish-skill` | `20` | Stockfish skill 0–20 (for `stockfish` without `:N`) |
| `--stockfish-time` | `0.1` | Stockfish think time in seconds |
| `--stockfish-threads` | all cores | Stockfish CPU threads |
| `--stockfish-path` | auto | Stockfish binary (`chess_llm.py` only for now) |
| `--api-base`, `--api-key` | provider default | Override endpoint and key (`LLM_CHESS_API_BASE`, `LLM_CHESS_API_KEY`) |

### `tournament.py`

| Flag | Default | Description |
|---|---|---|
| `--round-robin MODEL ...` | — | Every player meets every other, both colors |
| `--gauntlet CHAMPION` | — | Champion plays each `--opponents` entry |
| `--opponents MODEL ...` | — | Opponents for `--gauntlet` |
| `--games` | `1` | Games per pair |
| `--parallel N` | `1` | Run N games concurrently |
| `--openings` | `standard` | `standard` or `unbalanced` start positions |
| `--delay` | `0.5` | Seconds between moves |
| `--elo`, `--elo-db` | off, `ratings.json` | ELO tracking |
| `--model-flags` | — | `key=val,...` applied to every LLM player |
| `--resume` | off | Continue an unfinished tournament |
| `--tui` / `--no-tui` | auto | Force or disable the Textual UI (auto = TUI when stdout is a terminal) |
| `--log`, `-l` | off | Tee output to a log file |
| `--retries`, `--temperature`, `--timeout`, `--no-tools`, `--tiny`, `--constrain`, `--reasoning` | as in `chess_llm.py` | Defaults applied to LLM players |
| `--stockfish-time`, `--stockfish-threads` | `0.1`, all cores | Stockfish settings |

If the TUI fails to start, an explicit `--tui` shows the error and exits. When the TUI was only auto-detected (stdout is a terminal), `tournament.py` prints a warning and falls back to plain-text mode. Use `--no-tui` to skip the TUI entirely.

## Environment

| Variable | Used by |
|---|---|
| `OPENCODE_GO_API_KEY` | `opencode-go/` provider |
| `OPENCODE_ZEN_API_KEY` | `opencode-zen/` provider |
| `OPENROUTER_API_KEY` | `openrouter/` provider |
| `OPENAI_API_KEY` | `openai/` provider |
| `ANTHROPIC_API_KEY` | `anthropic/` provider (read by litellm) |
| `GROQ_API_KEY` | `groq/` provider (read by litellm) |
| `LLM_CHESS_API_BASE`, `LLM_CHESS_API_KEY` | Default for `--api-base` / `--api-key` |
| `LLM_CHESS_DEBUG=1` | Verbose model output (also `DEBUG_CHESS_LLM=1`) |

Local providers (`ollama/`, `llama-cpp/`, `docker/`, `bigpickle/`) need no key.

## How it works

**Move validation pipeline:**

```
LLM thinks → calls make_move(uci) → python-chess validates:
  ✓ Legal → push move, next turn
  ✗ Illegal → "That move is illegal because… Legal options: …"
              → retry (up to --retries) → forfeit if still no legal move
```

- **Tool calling** (default): models use a `make_move` tool — clean, reliable extraction
- **Text fallback**: parses a `MOVE: <uci>` marker or UCI tokens from free text; used with `--no-tools`, and automatically if a model ignores tools
- **Empty responses**: transient empty completions get exponential backoff retries
- **Hard timeout**: each API call runs in a daemon thread with a deadline. A hung call returns control at the deadline; the thread is abandoned in the background
- **Pre-flight check**: before the match starts, each LLM player sends a tiny probe to confirm connectivity

## Custom endpoints

Any OpenAI-compatible endpoint works via `--api-base` + `--api-key`:

```bash
python chess_llm.py \
  -w stockfish \
  -b openai/some-model \
  --api-base https://your-proxy.com/v1 \
  --api-key sk-...
```

The `openai/` prefix tells litellm to use the OpenAI-compatible handler.

## Development

```bash
# Set up a dev environment (pytest is a dev dependency)
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

# Run the test suite
.venv/bin/python -m pytest -q tests

# Smoke test without any API
python chess_llm.py --white random --black random --delay 0
```

CI (`.github/workflows/ci.yml`) runs on push and pull requests to `main`: the test suite on Python 3.11, 3.12 and 3.13, then a random-vs-random smoke test that fails the build on error or timeout.

Some tests are marked `xfail`/`skip` on purpose for features not built yet (ChessMatch callbacks, clock/time control, max-moves adjudication). See `HANDOFF.md` for current status and open items.

## Project files

```
chess-llm/
├── chess_llm.py          # Single-game CLI, player classes, ChessMatch (~1620 lines)
├── tournament.py         # Round-robin / gauntlet runner (~650 lines)
├── elo.py                # ELO tracker → ratings.json
├── model_config.py       # models.yaml loader (@presets, ?flags)
├── models.yaml           # Named model presets
├── openings.py           # Opening positions for --openings
├── tui/                  # Textual tournament UI
├── tests/                # pytest suite
├── .github/workflows/    # CI
├── AGENTS.md             # Notes for coding agents
├── HANDOFF.md            # Current handoff and open items
├── run_tournament.sh     # Example tournament invocation
├── pyproject.toml        # uv / pip project config
├── requirements.txt      # pip fallback
├── games/                # Auto-saved PGN files (gitignored)
└── .logs/                # Logs from --log (gitignored)
```
