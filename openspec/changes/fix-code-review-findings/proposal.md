## Why

The latest code review found several correctness and reliability regressions in the tournament TUI, CLI tournament flow, game statistics, LLM timeout handling, PGN persistence, and CI smoke test. These failures can present incomplete games as successful, lose resumable progress or PGNs, and allow broken code to pass CI.

## What Changes

- Make tournament workers report final game state and failures reliably, including resumable error handling.
- Make TUI pause, quit, ELO refresh, and live-board behavior match their visible controls and labels.
- Preserve tournament progress when quitting and honor tournament Stockfish configuration.
- Make PGN filenames unique under parallel execution.
- Calculate capture statistics from the position before each move.
- Ensure LLM timeout handling returns control promptly after the configured deadline.
- Make CI smoke tests fail when the CLI crashes or times out.

## Capabilities

### New Capabilities
- `reliable-tournament-execution`: Correct worker results, failure visibility, pause/quit semantics, resume behavior, live state, ELO rendering, and Stockfish options.
- `durable-game-records`: Unique PGN persistence and correct historical game statistics.
- `bounded-llm-calls`: Enforce the caller-visible timeout for provider calls.
- `honest-ci-validation`: Ensure smoke tests propagate application failures.

### Modified Capabilities

_None._

## Impact

Affected modules include `tui/runner.py`, `tui/tournament.py`, `tui/state.py`, `tournament.py`, `chess_llm.py`, and `.github/workflows/ci.yml`, plus regression tests. No new runtime dependency is required. Existing tournament state and PGN files remain readable; unfinished state will be saved rather than deleted on an early quit.
