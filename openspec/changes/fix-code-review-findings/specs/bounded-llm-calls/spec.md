## ADDED Requirements

### Requirement: Provider calls honor the caller timeout
The LLM call wrapper SHALL return or raise to its caller no later than the configured hard timeout plus documented allowance, without waiting indefinitely for an underlying worker thread.

#### Scenario: Provider call hangs
- **WHEN** the provider call does not return before the hard timeout
- **THEN** the wrapper raises its timeout outcome promptly and the match can retry or forfeit
