# AGENTS.md — LLM Chess

## Project overview

Python chess engine that pits LLMs, humans, Stockfish and random players against each other. No web server, no database. Two CLIs:

- `chess_llm.py` — single game, Unicode board in the terminal, PGN saved to `games/`.
- `tournament.py` — round-robin / gauntlet runs with ELO tracking, optional Textual TUI.

## Architecture

```
chess_llm.py      (~1620 lines) single-game CLI + player classes
├── PROVIDER_PRESETS / _resolve_provider()   prefix → base URL + env var
├── _run_with_timeout() / _call_llm()        litellm call with a hard timeout
├── LLMPlayer         _build_system(), check_connectivity(), get_move()
├── StockfishPlayer, HumanPlayer, RandomPlayer
├── LLM_PLAYER_KWARGS / parse_player()       shared player-spec parser
├── ChessMatch        play(), save_pgn(), print_stats()
└── main()            argparse, --log tee, --elo, --leaderboard
tournament.py     (~650 lines) round_robin(), gauntlet(), --parallel, --resume, --tui
elo.py            EloTracker → ratings.json (":memory:" = no file I/O)
model_config.py   models.yaml loader: @preset, ?key=val flags, merge rules
models.yaml       named model presets (@qwen3-local, @stockfish-0, …)
openings.py       starting positions for tournament --openings
tui/              Textual tournament UI (runner.py, state.py, board.py, elo_view.py)
tests/            pytest suite (conftest.py + 12 test_*.py modules)
.github/workflows/ci.yml   pytest on Python 3.11–3.13 + random-vs-random smoke test
```

## Key design decisions

- **Provider presets, not litellm config**: `PROVIDER_PRESETS` maps prefixes (`opencode-go/`, `openrouter/`, `ollama/`, `docker/`, `bigpickle/`, `llama-cpp/`, …) to base URLs and env var names. Set the env var and go.
- **Hard timeout, non-blocking**: `_run_with_timeout()` runs the litellm call in a daemon thread and joins with a limit. On timeout it raises `TimeoutError` immediately. Python cannot kill a thread, so the hung call keeps running in the background and its result is discarded. Do not use `with ThreadPoolExecutor` here: its `__exit__` blocks until the hung call finishes, which defeats the timeout.
- **No stderr redirection**: litellm noise is silenced only through logger levels (`CRITICAL`) and `litellm.suppress_debug_info`. Do not reassign `sys.stderr` at import time or around API calls; that hid argparse errors and tracebacks. (The one exception is `--log`, which tees stdout and stderr into the log file on purpose.)
- **Retry escalation**: illegal or missing moves get progressively shorter, more forceful messages. Attempt 3 is a single line: `"JUST THE UCI. ONE STRING. Example: Nc3"`.
- **Tool → text fallback**: if tools are enabled and the model ignores them on attempt 1, tools are disabled for attempts 2+.
- **Empty response = retry, not error**: empty completions get exponential backoff, not a correction message.
- **`MOVE:` marker extraction**: prefers a marked move that is legal; if the marked move is illegal, extraction falls through to later candidates.
- **Engine cleanup**: `ChessMatch.play()` closes engine players in a `finally`, including on exceptions and Ctrl-C.
- **Stockfish reuse**: `StockfishPlayer` starts the engine once and reuses it for every move.
- **One player-spec parser**: `parse_player()` in `chess_llm.py` handles `@preset`, `?key=val`, `human[:name]`, `random`, `stockfish[:N]` (empty `N` = skill 20). Unknown presets or flags are errors (exit 2), never treated as model names. `tournament.py` still has its own `parse_player_spec()`; switching it to `parse_player()` is pending.

## Dependencies

- Runtime (`requirements.txt`, `pyproject.toml`): `chess`, `litellm`, `openai`, `botocore` (pulled by litellm for AWS), `textual`, `rich`, `pyyaml`.
- Optional: `stockfish` Python wrapper (`pyproject` extra `stockfish`). The Stockfish binary itself must be installed or passed with `--stockfish-path`.
- Dev: `pytest` (`pyproject` `dev` extra / uv dev-dependency).

## Running tests

```bash
# Full test suite (pytest is a dev dependency)
.venv/bin/python -m pytest -q tests

# Smoke test: random vs random, no API needed (this is what CI runs)
timeout 60 python chess_llm.py --white random --black random --delay 0

# With debug output
LLM_CHESS_DEBUG=1 python chess_llm.py --white random --black random --delay 0
```

Tests for unbuilt features are marked `xfail` or `skip` (ChessMatch callbacks, clock/time control, max-moves adjudication). Do not "fix" them by deleting the markers without implementing the feature. Known open test failures are listed in `HANDOFF.md`.

CI (`.github/workflows/ci.yml`) runs pytest on Python 3.11–3.13 and the smoke test. The smoke test has no `|| true`: a crash or hang fails the build.

## Common issues

- **llama.cpp models**: `llama-cpp/` routes to llama-server's OpenAI-compatible `/v1` endpoint (default port 8080). Start with `llama-server -m model.gguf --port 8080`. No API key needed. Use `--tiny` for quantized models that handle tool calling poorly.
- **Model config system** (`models.yaml` + `model_config.py`):
  ```bash
  python chess_llm.py -w @qwen3-local -b @stockfish-0
  python chess_llm.py -w @qwen3-local?retries=5
  python chess_llm.py -w llama-cpp/model --white-flags "tiny=true,retries=10"
  python tournament.py --round-robin @qwen3-local @big-pickle --model-flags "timeout=180"
  ```
  Merge priority (lowest → highest): `defaults:` in models.yaml → named preset → inline `?key=val` → `--white-flags` / `--black-flags` / `--model-flags`.
- **Ollama**: `ollama/` routes through Ollama's `/v1` endpoint, not litellm's native handler (which has [tool-calling bugs](https://github.com/BerriAI/litellm/issues/13823)). The model must be pulled and the server running. Default base URL `http://localhost:11434/v1`; override with `--api-base`.
- **Ollama context window**: small default contexts (2K) overflow on the growing prompt. Raise `num_ctx` in a Modelfile. A model that goes silent mid-game usually means context overflow.
- **Docker Model Runner**: `docker/` routes to `/engines/v1` (port 12434). Models use the `ai/` namespace, e.g. `docker/ai/ministral3:3B-Q4_K_M`. Default context is 4K for GGUF models; raise with `docker model configure --ctx-size 8192 ai/<model>`.
- **Big Pickle Proxy**: `bigpickle/` routes to `http://localhost:8000/v1`. Start first: `cd bigpickle-proxy && python proxy.py --port 8000`. No API key needed. `big-pickle` and `deepseek-v4-flash-free` are reasoning models with a 16384-token floor (`chess_llm.py`, around line 225); `nemotron-3-super-free` and `mimo-v2.5-free` are non-reasoning. Whether `--reasoning` reaches the model depends on the proxy version; see the note at `PROVIDER_PRESETS`.
- **Stockfish startup**: cold systems can take >10 s to start; the popen timeout is 30 s.
- **No move returned**: small models can reason without ever emitting a UCI move. Try `--no-tools` or more `--retries`.
- **Empty API responses**: some providers return empty completions; these are retried automatically.

## File conventions

- Single-game PGN → `games/YYYYMMDD_HHMMSS_<white>_vs_<black>.pgn` (`/` and spaces in names become `_`). Written with plain `open(..., "w")`.
- Tournament PGN → same stem, names truncated to 40 characters. Files are created exclusively; on collision a `_1`, `_2`, … suffix is added, so parallel games never overwrite each other.
- Log files → `.logs/game_YYYYMMDD_HHMMSS.txt` (`--log` in `chess_llm.py`).
- ELO → `ratings.json` (gitignored, created at runtime).
- `.hermes/skills/` holds local agent skill definitions (gitignored). It is not used for plans.
