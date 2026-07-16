## Why

Authentication currently accepts bearer tokens in URL query parameters, exposes decoder details, permits weak registration passwords, and has no login throttling. These behaviors leak credentials and make credential-stuffing attacks unnecessarily cheap.

## What Changes

- **BREAKING**: accept access tokens only through the `Authorization: Bearer` header; SSE clients must use authenticated fetch streams.
- Return stable, generic authentication errors without JWT decoder details.
- Use configured access and refresh token lifetimes instead of endpoint constants.
- Require stronger registration passwords.
- Add bounded, process-local login throttling keyed by client and normalized account identifier.

## Capabilities

### New Capabilities

- `auth-transport`: Defines secure bearer-token transport, token lifetime, password, error, and login-throttling behavior.

### Modified Capabilities


## Impact

Backend authentication dependencies, auth schemas and routes, SSE frontend clients, configuration, and authentication tests are affected. No database migration or new runtime dependency is required.
