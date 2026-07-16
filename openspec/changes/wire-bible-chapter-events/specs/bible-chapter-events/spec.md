## ADDED Requirements

### Requirement: Reviewed entity changes update the Story Bible
The system SHALL persist entity state changes detected by a successful scene review into temporal Bible versions.

#### Scenario: Known character state changes
- **WHEN** reviewed prose changes a character fact and the character was injected into scene context
- **THEN** the change is applied at the current chapter with a scene event identifier

#### Scenario: Unknown entity is returned
- **WHEN** Reviewer output names an entity absent from injected Bible context
- **THEN** the change is discarded and no Bible entry is modified

#### Scenario: Review fails
- **WHEN** a scene requires rewrite or review is unavailable
- **THEN** no entity change is applied
