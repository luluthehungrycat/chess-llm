# Handoff — 2026-11-21

For the next coding agent working in this repo. Read this first, then `AGENTS.md`.

## Current state

- Branch: `chore/repo-health`. **Nothing from this branch is committed yet.** The working tree has modified and untracked files (`tests/`, `.github/`, `openspec/`, `HANDOFF.md`, …).
- Test run (2026-11-21, `.venv/bin/python -m pytest -q tests`): **168 passed, 1 failed, 1 skipped, 6 xfailed.**
  - Failing: `tests/test_review_fixes.py::test_print_stats_replays_capture_positions`. `ChessMatch.print_stats()` prints no `Captures:` line, so capture statistics are not implemented.
  - Skipped: `tests/test_clock_and_timing.py` (module-level skip, clock/time control not built).
  - xfail: ChessMatch callbacks, max-moves adjudication.

## What this branch did

- **Stderr**: `chess_llm.py` no longer redirects `sys.stderr` to `/dev/null` at import. litellm noise is silenced via logger levels and `litellm.suppress_debug_info`. `--log` still tees stderr on purpose.
- **Hard timeout**: `_run_with_timeout()` (daemon thread) replaces `ThreadPoolExecutor`. A hung call no longer blocks the caller; the thread is abandoned.
- **Engine cleanup**: `ChessMatch.play()` closes engine players in a `finally`.
- **`MOVE:` extraction**: prefers a legal marked move and falls through if the marked move is illegal.
- **Player specs**: `parse_player()` is the shared parser. `LLM_PLAYER_KWARGS` lists spec-settable LLM kwargs (includes `constrain`). `stockfish:` (empty) means skill 20. Unknown `@preset` or `?flag` exits with code 2.
- **ELO** (`elo.py`): Black's update now uses Black's expected score (it used White's). Unknown results and self-play raise `ValueError`. `":memory:"` means no file I/O.
- **Tournament PGNs**: filenames are unique per game (exclusive create, `_1`, `_2`, … suffix), so parallel games don't overwrite each other.
- **CI**: `.github/workflows/ci.yml` runs pytest on 3.11–3.13 and a random-vs-random smoke test with no `|| true`.
- **Deps**: `pyproject.toml` and `requirements.txt` both list `textual`, `rich`, `pyyaml`. pytest is a dev dependency.

## Known gaps

1. **Not built** (tests are xfail/skip, not failures): ChessMatch callbacks, clock/time control (`_parse_clock`), max-moves adjudication, **resignation** (no code or tests).
2. **Failing test**: capture statistics (see above). Either implement the `Captures:` line in `print_stats()` or remove the test.
3. **`--tui` does not fail loudly.** `tournament.py` (line 598) still wraps TUI startup in `except Exception` and falls back to plain text. An earlier note said this was removed; it was not.
4. **Stockfish options in tournament**: `--stockfish-skill` is parsed but never used. `--stockfish-path` is not a tournament flag. Stockfish skill comes only from the spec (`stockfish:N`).
5. **Duplicate parser**: `tournament.py` still has its own `parse_player_spec()`. It should call `chess_llm.parse_player()`.
6. **`ratings.json` needs a reset.** Existing values were computed with the Black-expected-score bug and are skewed. The file is gitignored and untracked (since `2684cf5`); the local copy has 148 lines. Move it aside before the next tournament with `--elo`.
7. **`feat/tui-overhaul` is unmerged** and left as-is. Only its CI idea was taken. Do not merge it wholesale; review it branch-by-branch.
8. **God files**: `chess_llm.py` is ~1620 lines. `LLMPlayer.get_move()` is ~240 lines (≈ lines 707–944) and `main()` is ~310 lines (≈ lines 1310–1621). Split prompt building, the retry loop, and CLI parsing into separate modules.
9. **Unverified**: a sandboxed test run tried to reach `raw.githubusercontent.com`. This is probably litellm fetching its model cost map at import. Not investigated.

## Next steps

1. Decide on the capture-statistics test (implement or drop) and get the suite to green.
2. Remove the broad `except` around TUI startup in `tournament.py` so `--tui` fails loudly, or update the README to match (it currently describes the fallback).
3. Switch `tournament.py` to `parse_player()`; wire up or remove `--stockfish-skill`.
4. Reset `ratings.json` (move it aside), then re-run the ELO tests.
5. Split `chess_llm.py` (LLM player, retry loop, CLI).
6. Commit the branch in logical pieces, then open a PR against `main`.
7. Keep the xfail markers for unbuilt features until the features exist; do not remove them just to get a green run.
