# Handoff — 2026-11-21

For the next coding agent working in this repo. Read this first, then `AGENTS.md`.

## Current state

- Branch `chore/repo-health` (based on `a15ef62`, local only, not pushed, no PR). All work is committed.
- Tests (`.venv/bin/python -m pytest -q tests`): **186 passed, 1 skipped, 6 xfailed.** The skips and xfails are unbuilt features (see below), not failures.
- CI (`.github/workflows/ci.yml`) installs Stockfish, runs pytest on Python 3.11–3.13, and runs a random-vs-random smoke game with no `|| true`.

## What this branch did

- **Timeout**: `_run_with_timeout()` (daemon thread) replaces `with ThreadPoolExecutor`, so a hung provider no longer blocks past the limit.
- **Stderr**: no module-level `sys.stderr` redirect; litellm noise is silenced via logger levels.
- **Engine cleanup**: `ChessMatch.play()` closes both engines in a `finally`. A failing `close()` is reported but never hides the error that ended the match, and never stops the other engine closing.
- **`MOVE:` extraction**: a legal marked move wins. After an illegal marker, a legal move written *after* it wins next, before the rest of the text is scanned.
- **One parser**: `chess_llm.parse_player()` is used by both CLIs (`tournament.parse_player_spec()` only builds players from it). Unknown `@presets` exit 2 before any game starts. `--stockfish-skill` applies to bare `stockfish` in both CLIs.
- **ELO**: Black uses Black's expected score; unknown results raise; self-play (same id on both sides) is left unrated. `elo.player_id(spec)` is the one rating key for sequential, parallel and TUI tournament games, and preset aliases (`@stockfish-0` = `stockfish:0`) share it.
- **Tournament/TUI**: unique PGN names for parallel games, live board fixes, resume retries failed games, explicit `--tui` fails loudly (auto-detected TUI still falls back).
- **Repo**: deps aligned (`pyproject.toml`, `requirements.txt`), `.gitignore` for local agent tooling, docs refreshed, unbuilt-feature tests marked xfail/skip.

## Known gaps (found in review, not fixed)

1. **Kwarg merge priority**: `models.yaml` `defaults:` beat explicit global CLI flags (`--timeout`, `--retries`, `--temperature`) in both CLIs, against the documented priority. In tournaments, `--tiny` set via global flags is applied after construction, so it does not force tools off. Fix: argparse defaults of `None`, merge every layer before constructing the player, then apply the tiny rule.
2. **TUI gauntlet schedules opponent-vs-opponent games** (`tui/state.py` builds round-robin pairs). Plain-text mode is correct. Both should use one pairing schedule, persisted for resume.
3. **Resume**: `--resume --no-tui` without players exits without loading the checkpoint. TUI resume reads `openings_mode` from the ELO dict, and the checkpoint never saves it, so `unbalanced` resumes as `standard`.
4. **No `--stockfish-path` in `tournament.py`**; engines with a custom binary location cannot be used there.
5. **Unknown `?key=val` flags are ignored** (a typo like `?retrise=5` passes silently). `tests/test_parse_player_parity.py` currently asserts this behaviour.
6. **Two ELO-key schemes**: single games key LLMs by the resolved model string, tournaments by the spec. Both share `ratings.json`.
7. **`ratings.json` needs a reset**: values were computed with the old Black-expected-score bug. Move it aside before the next `--elo` run.
8. **Not built** (tests xfail/skip): ChessMatch callbacks, clock/time control, max-moves adjudication, resignation.
9. **God file**: `chess_llm.py` (~1650 lines), with a ~240-line `LLMPlayer.get_move()` and a ~310-line `main()`.
10. **`feat/tui-overhaul`** is unmerged and left as-is; only its CI idea was taken.

## Next steps

1. Push `chore/repo-health` and open a PR against `main`.
2. Fix gap 1 (merge priority), then gaps 2–3 (TUI gauntlet, resume).
3. Decide gap 5 (reject unknown flags) and gap 6 (one ELO-key scheme).
4. Split `chess_llm.py` (LLM player, retry loop, CLI).
5. Keep the xfail markers for unbuilt features until the features exist.
