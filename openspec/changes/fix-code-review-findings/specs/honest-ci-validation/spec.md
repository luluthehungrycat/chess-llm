## ADDED Requirements

### Requirement: CI smoke tests propagate failures
The CI smoke test SHALL fail when the chess CLI exits nonzero or is terminated by its timeout.

#### Scenario: CLI crashes or times out
- **WHEN** the smoke command exits with a nonzero status
- **THEN** the CI step exits nonzero
