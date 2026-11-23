## Context

The review covers independent regressions introduced across the CLI, tournament orchestration, Textual TUI, persistence, and CI. The runner currently crosses a thread boundary using queues, but final game metadata is incorrectly reconstructed from UI-drained state. Tournament failures are converted into ordinary results, and several visible controls do not affect execution or persistence.

## Goals / Non-Goals

**Goals:**
- Make worker-owned results authoritative and thread-safe.
- Preserve failure information and make resume accounting retry failed games.
- Align pause, quit, live display, ELO refresh, Stockfish options, PGN persistence, and statistics with user-visible behavior.
- Restore prompt timeout behavior and CI failure propagation.

**Non-Goals:**
- Redesign the tournament UI or introduce a new persistence format.
- Change chess rules, ELO formulas, or provider selection semantics beyond the reviewed bugs.

## Decisions

1. **Capture final state in the worker callback path.** The worker already owns the `ChessMatch` execution; it will retain the latest board per task as callbacks arrive and use that state directly when constructing the result. UI queues remain for display only.
2. **Represent failures distinctly from completed games.** Error results will be surfaced/logged and excluded from completed/resume counts. Completion requires all required games to have valid outcomes.
3. **Use synchronization for pause and latest-state ordering.** A pause event/gate will prevent additional dispatch, and live updates will carry an update sequence or timestamp so latest means most recently updated.
4. **Save before clearing.** An unfinished quit will persist current state and leave it available for resume; only successful completion clears it.
5. **Configure players before construction.** Tournament parser/factory inputs will carry Stockfish path, skill, and startup options rather than mutating an already-created player.
6. **Use unique output names and replay boards for statistics.** PGN names will include a collision-resistant component; capture counts will replay moves from the initial position.
7. **Avoid waiting executor shutdown on timeout.** The timeout wrapper will not use a context-manager exit path that waits for a stuck provider call.

## Risks / Trade-offs

- [Risk] Python threads cannot forcibly terminate a stuck provider call → Mitigation: return promptly, cancel pending work, and rely on provider/client timeouts for eventual cleanup.
- [Risk] Existing state files may contain `error` tuples → Mitigation: filter them during resume and treat them as unfinished.
- [Risk] Textual API behavior varies by version → Mitigation: keep column creation in mount/setup and test repeated refreshes against the pinned dependency.
- [Risk] More visible errors may alter output expectations → Mitigation: update focused tests while preserving successful output.
