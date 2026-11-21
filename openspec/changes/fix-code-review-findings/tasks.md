## 1. Tournament runner correctness

- [x] 1.1 Capture final board/FEN/move count in worker-owned state rather than relying on UI polling.
- [x] 1.2 Preserve latest-live-state update ordering for concurrent games.
- [x] 1.3 Represent worker failures visibly and exclude error results from completed/resume counts.
- [x] 1.4 Implement pause gating and define completion only for successful game outcomes.
  > Status note (2026-11-21): pause gating exists (`_pause_gate` in `tui/runner.py`). Failed games are excluded from completion (`test_error_result_does_not_update_elo`, `test_failed_resume_tasks_are_retried`). No pause test exists.

## 2. TUI persistence and display

- [x] 2.1 Save unfinished tournament state before quitting and retain it for `--resume`.
  > Status note (2026-11-21): `save_state` is called from `action_save` in `tui/tournament.py`. Not covered by a test found in `tests/`.
- [x] 2.2 Stop ELO table column accumulation during repeated refreshes.
- [x] 2.3 Add regression tests for pause, quit/resume, failures, live state, and repeated ELO refresh.
  > Status note (2026-11-21): **partially false.** Resume and failure tests exist (`tests/test_tui_runner.py`, `tests/test_review_fixes.py`). No tests were found for pause, quit/resume round-trip, or repeated ELO refresh.

## 3. Tournament CLI and records

- [x] 3.1 Thread Stockfish skill, binary path, and startup configuration into player construction.
  > Status note (2026-11-21): **partially false.** `--stockfish-threads` and `--stockfish-time` are threaded into players. `--stockfish-skill` is parsed but never used in `tournament.py`, and `--stockfish-path` is not a tournament flag. Skill comes only from the `stockfish:N` spec.
- [x] 3.2 Make tournament PGN filenames unique under parallel/repeated games.
  > Status note (2026-11-21): implemented with exclusive create and a `_N` suffix in `tournament.py`. Covered by `test_review_fixes.py` (PGN collision test).
- [x] 3.3 Add tests for Stockfish options and PGN collision avoidance.
  > Status note (2026-11-21): **partially false.** The PGN collision test exists. No tests for Stockfish options were found (no test references `skill` or `--stockfish-*`).

## 4. Chess engine and LLM behavior

- [x] 4.1 Replay board positions when calculating historical capture statistics.
  > Status note (2026-11-21): **false.** `ChessMatch.print_stats()` prints no `Captures:` line. `test_print_stats_replays_capture_positions` fails.
- [x] 4.2 Ensure provider timeout returns without waiting for stuck executor threads.
  > Status note (2026-11-21): at `HEAD`, `chess_llm.py` still used `ThreadPoolExecutor` for the call. The working tree now uses `_run_with_timeout()` (daemon thread). `test_core_fixes.py` timeout tests pass.
- [x] 4.3 Add regression tests for captures and hard timeout behavior.
  > Status note (2026-11-21): **partially false.** Hard-timeout tests exist and pass. The capture regression test fails (see 4.1).

## 5. CI validation

- [x] 5.1 Remove failure masking from the CI smoke test and preserve diagnostic output.
  > Status note (2026-11-21): **false when marked done.** No workflow file existed. The workflow is now added at `.github/workflows/ci.yml` on `chore/repo-health` (not yet committed). It runs pytest on 3.11–3.13 and the smoke test without `|| true`.
- [x] 5.2 Run focused and full test suites; validate the OpenSpec change.
  > Status note (2026-11-21): **false when marked done.** The full suite currently has 1 failure (`test_print_stats_replays_capture_positions`). Result: 168 passed, 1 failed, 1 skipped, 6 xfailed.
