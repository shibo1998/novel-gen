## ADDED Requirements

### Requirement: Regeneration is explicit and protected
The system SHALL preserve an existing outline unless the caller explicitly requests regeneration, and MUST reject regeneration after writing has started.

#### Scenario: Existing outline without regenerate flag
- **WHEN** a project already has volume or chapter rows and `regenerate=false`
- **THEN** the API returns HTTP 409 without deleting data

#### Scenario: Written chapter exists
- **WHEN** a chapter has nonzero word count, writing/completed status, or related scenes
- **THEN** regeneration returns HTTP 409 even if `regenerate=true`

### Requirement: Duplicate outline mutations are rejected
The system SHALL allow only one active task of each outline mutation kind for a project.

#### Scenario: Two initial outline requests overlap
- **WHEN** a second initial outline request arrives while the first is pending or running
- **THEN** the API returns HTTP 409 with the active task ID

