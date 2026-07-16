## ADDED Requirements

### Requirement: Automatic memory reindexing
The system SHALL periodically retry memory records whose embedding is missing or not indexed.

#### Scenario: Failed record recovers
- **WHEN** the embedding provider becomes available after a write-time failure
- **THEN** a background batch writes the embedding and marks the record indexed

#### Scenario: Provider remains unavailable
- **WHEN** a compensation batch cannot be embedded
- **THEN** records remain failed and the application continues serving requests

### Requirement: Concurrent worker safety
The system SHALL prevent concurrent workers from processing the same compensation rows.

#### Scenario: Multiple backend workers run
- **WHEN** two workers request pending records concurrently
- **THEN** locked rows are skipped and each record is claimed by at most one worker per attempt
