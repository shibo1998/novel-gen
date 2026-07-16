## ADDED Requirements

### Requirement: Header-only bearer authentication
The system SHALL accept access tokens only from the `Authorization: Bearer` header and SHALL reject query-parameter tokens.

#### Scenario: Query token is rejected
- **WHEN** a protected endpoint is called with only a `token` query parameter
- **THEN** the system returns 401 without authenticating the request

### Requirement: Stable authentication errors
The system SHALL return generic authentication errors and MUST NOT expose JWT decoder or provider exception text.

#### Scenario: Malformed token
- **WHEN** a malformed access or refresh token is supplied
- **THEN** the system returns 401 with a stable generic message

### Requirement: Configured token lifetimes
The system SHALL issue access and refresh tokens using configured lifetime values.

#### Scenario: Login token lifetime
- **WHEN** a user logs in successfully
- **THEN** the access token expiration reflects the configured access-token lifetime

### Requirement: Registration password strength
The system SHALL reject registration passwords shorter than 12 characters.

#### Scenario: Weak password registration
- **WHEN** registration supplies a password shorter than 12 characters
- **THEN** request validation rejects the request

### Requirement: Login throttling
The system SHALL throttle repeated failed login attempts using both client identity and normalized account identifier while avoiding account-existence disclosure.

#### Scenario: Repeated failures
- **WHEN** the configured failure limit is reached within the configured window
- **THEN** subsequent login attempts return 429 until the window expires

#### Scenario: Successful login clears account failures
- **WHEN** valid credentials are supplied before the account key is blocked
- **THEN** prior failures for that account identifier are cleared
