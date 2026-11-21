## ADDED Requirements

### Requirement: Tournament results preserve worker-owned final state
The tournament runner SHALL attach final FEN and move-count metadata from the worker's completed match state, independently of UI polling order.

#### Scenario: Fast game completes before a UI poll
- **WHEN** a worker completes a game before the UI drains its move queue
- **THEN** the result contains the actual final FEN and move count, not the opening position or zero

### Requirement: Tournament failures remain visible and resumable
A worker failure SHALL be surfaced to the TUI and SHALL NOT count as a successfully completed game for resume accounting or clean-completion state removal.

#### Scenario: Worker raises during a game
- **WHEN** a tournament worker encounters an exception
- **THEN** the UI reports the failed pairing and resume state retains it as unfinished

### Requirement: TUI controls reflect execution state
The TUI SHALL implement pause as an execution control, save unfinished progress before quitting, and SHALL refresh the ELO table without accumulating duplicate columns.

#### Scenario: User pauses an active tournament
- **WHEN** the user toggles pause
- **THEN** no new tournament work is dispatched until the user resumes

#### Scenario: User quits an unfinished tournament
- **WHEN** the user quits while games remain unfinished
- **THEN** current progress is persisted for `--resume` and the state file is not cleared

#### Scenario: ELO table refreshes repeatedly
- **WHEN** the progress poll refreshes the ELO table multiple times
- **THEN** the table retains one set of columns and current rows

### Requirement: Tournament Stockfish options are honored
The tournament command SHALL apply the configured Stockfish skill and binary path before constructing Stockfish players, including bare `stockfish` specifications.

#### Scenario: Custom Stockfish configuration is supplied
- **WHEN** a tournament specifies `--stockfish-skill N` or `--stockfish-path PATH`
- **THEN** every constructed Stockfish player uses those values

### Requirement: Live board selection tracks latest updates
The runner SHALL identify the most recently updated active game by update time or equivalent update ordering, not only by task insertion order.

#### Scenario: Multiple games emit moves concurrently
- **WHEN** a later-created task receives the newest move
- **THEN** the TUI displays that task's latest state
