## ADDED Requirements

### Requirement: Atomic request transaction
The system SHALL commit ordinary request-scoped database changes only after the route completes successfully and SHALL roll them back when route processing raises.

#### Scenario: Response preparation fails after mutation
- **WHEN** a CRUD route mutates data and later raises before completing
- **THEN** no partial mutation is committed

#### Scenario: Background task is launched
- **WHEN** a route starts work in an independent database session
- **THEN** required task and snapshot state is explicitly committed before launch
