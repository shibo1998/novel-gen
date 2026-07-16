## ADDED Requirements

### Requirement: Confirmed prose is compliant
The system SHALL require both a successful review and a clean deterministic compliance scan before a scene enters confirmed state.

#### Scenario: Reviewed prose contains a blocked term
- **WHEN** the Reviewer passes prose that contains a configured blocked term
- **THEN** the prose is retained as draft and structured compliance issues are persisted

#### Scenario: Manual prose is saved
- **WHEN** a user saves prose without completing review
- **THEN** the prose remains draft until a successful compliant review

#### Scenario: Clean prose passes review
- **WHEN** prose passes review and has no compliance issues
- **THEN** the scene becomes confirmed

#### Scenario: Manual review completes a chapter
- **WHEN** a manually saved scene passes review and all chapter scenes are confirmed
- **THEN** the active content version is evaluated by the chapter quality workflow
