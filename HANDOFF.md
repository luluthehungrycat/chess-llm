# Handoff — 2026-11-23

For the next coding agent working in this repo. Read this first, then `AGENTS.md`.

## Current state

- Branch `chore/repo-health` (based on `a15ef62`), open as PR #3 against `main`.
- Tests (`.venv/bin/python -m pytest -q -p no:warnings tests`): **197 passed, 1 skipped, 6 xfailed.** The skips and xfails are unbuilt features (see below), not failures.
- CI (`.github/workflows/ci.yml`) installs Stockfish, runs pytest on Python 3.11–3.13, and runs a random-vs-random smoke game with no `|| true`.

## What this branch did

- **Timeout**: `_run_with_timeout()` (daemon thread) replaces `with ThreadPoolExecutor`, so a hung provider no longer blocks past the limit.
- **Stderr**: no module-level `sys.stderr` redirect; litellm noise is silenced via logger levels.
- **Engine cleanup**: `ChessMatch.play()` closes both engines in a `finally`. A failing `close()` is reported but never hides the error that ended the match, and never stops the other engine closing.
- **`MOVE:` extraction**: a legal marked move wins. After an illegal marker, a legal move written *after* it wins next, before the rest of the text is scanned.
- **One parser**: `chess_llm.parse_player()` is used by both CLIs (`tournament.parse_player_spec()` only builds players from it). Unknown `@presets` exit 2 before any game starts. `--stockfish-skill` applies to bare `stockfish` in both CLIs.
- **LLM settings**: Explicit global CLI flags override model settings. Per-player flags take priority, and tiny mode disables tools after merging.
- **ELO**: Black uses Black's expected score, unknown results raise, and self-play leaves ratings unchanged. Both CLIs use the resolved model for LLM ratings and the same IDs for non-LLM players.
- **Tournament/TUI**: Both modes share a schedule. Checkpoints store pending games and openings and can resume in plain text or the TUI. The ratings file is the source of truth: each finished game is applied to it once (the TUI also checkpoints after every game), never overwritten with a checkpoint snapshot. Tournament `--stockfish-path` is taken from the command line on resume, never from the checkpoint (a checkpoint must not choose an executable); restored player options are filtered to known keys.
- **Repo**: deps aligned (`pyproject.toml`, `requirements.txt`), `.gitignore` for local agent tooling, docs refreshed, unbuilt-feature tests marked xfail/skip.

## Known gaps (found in review, not fixed)

1. **Unknown `?key=val` flags are ignored** (a typo like `?retrise=5` passes silently). `tests/test_parse_player_parity.py` currently asserts this behaviour.
2. **Parallel Ctrl-C**: `_run_schedule` submits every game up front; on Ctrl-C the executor still waits for queued games, which can write PGNs that the checkpoint still lists as pending. Bound submissions and cancel queued work on interrupt.
3. **Legacy checkpoints** (written before the merge-priority fix) stored argparse defaults such as `timeout: 120` as explicit flags, so on resume they now beat preset values. Checkpoints are not versioned.
4. **Rating keys of odd specs**: ids come from the spec string, not the parsed player type, so an LLM spec like `human-Kai` shares the key of `human:Kai`. Old preset-keyed rows (`@qwen3-local`) are not migrated; `ratings.json` was reset on 2026-11-23, so only other DB files are affected.
5. **Unbuilt features** (tests xfail/skip) include ChessMatch callbacks, clock/time control, max-moves adjudication, and resignation.
6. **Large CLI module**: `chess_llm.py` contains the LLM player, retry loop, and single-game CLI.
7. **`feat/tui-overhaul`** stays unmerged: as a whole it reintroduces the stderr redirect, the `ThreadPoolExecutor` timeout and unprotected engine cleanup. Worth porting piecemeal: `--max-moves` adjudication, the Ollama context-window warning, a configurable Stockfish startup timeout, per-player timing in the TUI.

## Next steps

1. Merge PR #3.
2. Decide whether to reject unknown flags.
3. Split `chess_llm.py` into the LLM player, retry loop, and CLI.
4. Keep the xfail markers for unbuilt features until the features exist.
