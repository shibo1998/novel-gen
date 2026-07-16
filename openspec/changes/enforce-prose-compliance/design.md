## Context

Five prose persistence paths currently make independent status decisions and none invokes the existing deterministic compliance scanner.

## Decisions

- A shared service scans content, stores structured issues under `review_result.compliance`, and computes effective pass state.
- Confirmation requires both reviewer approval and zero compliance issues.
- Manual save without a review remains draft; a subsequent streaming Reviewer pass can confirm it.
- Content is retained for user correction rather than rejected or silently rewritten.
