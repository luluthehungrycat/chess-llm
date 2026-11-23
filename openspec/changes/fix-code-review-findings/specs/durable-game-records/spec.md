## ADDED Requirements

### Requirement: Game records use unique paths
Tournament PGN output SHALL use a collision-resistant unique filename for each game, including games started within the same second.

#### Scenario: Parallel games share a timestamp second
- **WHEN** two games finish in the same second with the same pairing
- **THEN** both PGN files are retained

### Requirement: Historical capture statistics are accurate
Capture statistics SHALL evaluate each move against the board position immediately before that move.

#### Scenario: A capture is followed by additional moves
- **WHEN** a game contains a capture and the capturing piece later moves
- **THEN** the reported capture count includes the original capture
