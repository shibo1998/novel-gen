## Context

Protected APIs currently allow URL query tokens for EventSource compatibility, decoder errors are reflected to clients, token TTLs are duplicated in routes, registration accepts six-character passwords, and login attempts are unlimited. The application is a single backend process today and has no shared rate-limit store.

## Goals / Non-Goals

**Goals:**

- Enforce header-only access tokens and stable failure-safe responses.
- Centralize token lifetime configuration.
- Add a dependency-free login throttle appropriate for the current single-process deployment.
- Preserve existing token response shape.

**Non-Goals:**

- Distributed Redis rate limiting, MFA, token revocation, asymmetric JWT migration, or refresh-token cookies.

## Decisions

- Use authenticated fetch streaming on the frontend instead of EventSource query tokens, because URL credentials leak through history, logs, and referrers.
- Keep JWT signing unchanged for compatibility, but remove exception details and endpoint TTL constants.
- Implement a lock-protected in-memory sliding-window throttle with bounded stale-entry cleanup. This matches the current process-local task architecture and adds no dependency; a Redis backend is deferred until Redis is actually part of runtime state.
- Key failures by both client address and normalized email. This slows distributed account attacks and single-client enumeration without revealing whether an account exists.
- Keep registration validation in Pydantic so weak passwords fail before hashing or database work.

## Risks / Trade-offs

- [Process restart clears throttle state] -> Accept for the current single-process deployment and document Redis as the future multi-process backend.
- [Header-only tokens break native EventSource] -> Migrate streaming calls to fetch-based readers before deployment.
- [Stronger password validation affects existing automation] -> Existing users remain valid; only new registrations are affected.

## Migration Plan

1. Deploy backend and frontend changes together.
2. Verify protected SSE endpoints work through authenticated fetch streams.
3. Roll back both sides together if streaming regressions occur.

## Open Questions

- When the backend becomes multi-process, which Redis rate-limit implementation will replace the local throttle?
