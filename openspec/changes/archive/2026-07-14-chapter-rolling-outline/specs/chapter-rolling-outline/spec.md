## ADDED Requirements

### Requirement: Complete volume contracts precede chapter details
The system SHALL create and persist a complete contract for every volume before generating detailed chapters. Each contract MUST include an exact chapter range, core conflict, character arc, opening state, ending state, and handoff hook.

#### Scenario: Ninety chapters across four volumes
- **WHEN** a skeleton contains four volumes for a 90-chapter project
- **THEN** the system persists non-overlapping ranges `1-23`, `24-46`, `47-68`, and `69-90`

#### Scenario: Volume remains structurally complete before expansion
- **WHEN** no detailed chapters have been generated for a planned volume
- **THEN** the volume contract still exposes its narrative goal, boundaries, ending state, and next-volume handoff

### Requirement: Chapter details roll in bounded batches
The system SHALL generate detailed chapters in sequential batches of at most five chapters and MUST NOT request an entire volume's detailed chapters in one LLM response.

#### Scenario: Initial outline generation
- **WHEN** the outline task completes for a project with completed worldbuilding
- **THEN** all volume contracts and no more than the first five detailed chapters are persisted

#### Scenario: Expand within a volume
- **WHEN** chapters 1 through 5 exist and the first volume ends at chapter 23
- **THEN** the next expansion requests exactly chapters 6 through 10

#### Scenario: Batch crosses a volume boundary
- **WHEN** the active volume has only chapters 22 and 23 remaining
- **THEN** the system generates only chapters 22 and 23 and the following request starts at the next volume's first chapter

### Requirement: Generated batches match their assigned range
The system MUST validate that each model response contains every requested chapter number exactly once, contains no out-of-range chapter, and assigns every chapter to the active volume before persistence.

#### Scenario: Model skips a requested chapter
- **WHEN** the model is asked for chapters 6 through 10 but omits chapter 8
- **THEN** the task fails atomically and no chapters from that batch are persisted

#### Scenario: Duplicate expansion request
- **WHEN** an expansion is requested after the same batch has already been persisted
- **THEN** the system recomputes the next missing range and does not insert duplicate chapter numbers

### Requirement: Legacy volume expansion remains compatible
The system SHALL retain the existing volume expansion endpoint but MUST limit it to the next chapter batch and enforce sequential planning.

#### Scenario: Legacy client expands the active volume
- **WHEN** a client calls `/volumes/expand/{vol_num}` for the next incomplete volume
- **THEN** the endpoint returns a task with its existing response fields and generates at most five chapters

#### Scenario: Legacy client skips an incomplete earlier volume
- **WHEN** a client requests a later volume while an earlier volume is incomplete
- **THEN** the endpoint returns HTTP 409 with the active volume number

### Requirement: Existing outline semantics remain stable
The system SHALL return HTTP 200 with empty arrays when an existing project has no generated outline and SHALL retain HTTP 404 for a project that does not exist or is not owned by the caller.

#### Scenario: Existing project without outline
- **WHEN** an authorized user requests an outline with no volume or chapter rows
- **THEN** the response is HTTP 200 with empty `volumes`, `chapters`, and `foreshadowing_registry`

#### Scenario: Missing project
- **WHEN** a user requests an unknown project ID
- **THEN** the response is HTTP 404 with `Project not found`

