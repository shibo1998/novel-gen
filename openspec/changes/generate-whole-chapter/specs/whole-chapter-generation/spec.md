## ADDED Requirements

### Requirement: Automatic writing uses one chapter generation context
The system SHALL generate an automatic chapter from all ordered scene contracts in one LLM drafting call instead of invoking the writer independently for each scene.

#### Scenario: Chapter contains multiple planned scenes
- **WHEN** a user starts automatic chapter writing for a chapter with two or more scene contracts
- **THEN** the system sends all ordered contracts to one chapter writer call under one chapter-level budget

#### Scenario: Manual scene writing remains available
- **WHEN** a user invokes an existing manual or automatic single-scene writing endpoint
- **THEN** the system continues to use the scene writing flow and its scene budget

### Requirement: Generated prose maps back to planned scenes
The chapter writer SHALL emit machine-readable scene boundaries, and the system MUST remove those boundaries before storing non-empty prose for every planned scene.

#### Scenario: All boundaries are valid
- **WHEN** the generated chapter contains each expected scene marker exactly once and in order
- **THEN** the system stores the corresponding prose on each scene without persisting the markers

#### Scenario: Boundaries are invalid
- **WHEN** a marker is missing, duplicated, out of order, or followed by an empty scene segment
- **THEN** the system reports a blocking format issue and does not persist an ambiguous chapter result

### Requirement: Chapter length is enforced once
The system SHALL measure the complete chapter using a single prose-character metric and SHALL accept only content between 92% and 108% of the configured chapter budget.

#### Scenario: Chapter is within range
- **WHEN** the complete chapter character count is within the accepted range
- **THEN** no length repair issue is produced

#### Scenario: Chapter is outside range
- **WHEN** the complete chapter character count is below or above the accepted range
- **THEN** the reviewer produces a blocking issue containing the actual and accepted character counts

### Requirement: Chapter repair is bounded
The system SHALL allow at most one chapter repair after the initial draft, and the repair prompt MUST include the prior draft and concrete blocking issues.

#### Scenario: Initial draft fails review
- **WHEN** the initial draft has a repairable blocking issue
- **THEN** the system performs one chapter repair and reviews the repaired chapter

#### Scenario: Repaired draft still fails
- **WHEN** the repaired draft still has blocking issues
- **THEN** the system marks the result as needing review without requesting a third draft

### Requirement: Chapter persistence is atomic
The system SHALL update all scene contents and create exactly one chapter content version after the complete chapter result has been parsed and reviewed.

#### Scenario: Chapter passes review
- **WHEN** the complete chapter passes chapter-level review and deterministic compliance checks
- **THEN** every scene is confirmed, one chapter version is created, and quality evaluation runs once

#### Scenario: Chapter needs human review
- **WHEN** the final bounded attempt does not pass chapter-level review
- **THEN** every parsed scene remains draft, one reviewable chapter version is created, and no scene is individually committed as a successful chapter fragment

### Requirement: Chapter generation preserves operational safeguards
The system MUST retain durable task idempotency, cost reservation, LLM metrics, frozen context snapshots, foreshadow validation, and validated Bible updates for automatic chapter writing.

#### Scenario: Duplicate chapter request
- **WHEN** the same chapter and ordered context snapshots are submitted again
- **THEN** the system returns the existing non-failed generation task instead of starting duplicate LLM work

#### Scenario: Successful chapter establishes story changes
- **WHEN** chapter review validates foreshadow resolutions or Bible entity changes
- **THEN** the system applies only identifiers and entities present in the frozen chapter context
