## ADDED Requirements

### Requirement: Stable public task failures
The system SHALL expose a stable generic task failure code and message and MUST NOT return raw exception text through polling or streaming APIs.

#### Scenario: Live task fails
- **WHEN** an in-memory generation task raises an exception
- **THEN** subscribers and status polling receive only the stable public failure message

#### Scenario: Durable task fails
- **WHEN** a durable generation task raises an exception
- **THEN** its persisted public error fields contain no exception text

#### Scenario: Legacy task is queried
- **WHEN** an older durable task row contains a raw exception message
- **THEN** the task API derives a sanitized response from its failure status

### Requirement: Server-side diagnostics
The system SHALL log the original exception and traceback with the task identifier when a task fails.

#### Scenario: Provider failure
- **WHEN** a provider exception terminates generation
- **THEN** the server log retains diagnostic detail while the client receives only the public failure contract
