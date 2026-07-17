## 1. Chapter Drafting Contracts

- [x] 1.1 Add chapter prompt rendering, hidden scene markers, parsing, and chapter character-count helpers
- [x] 1.2 Add a chapter writer agent that supports initial drafting and one issue-guided repair

## 2. Chapter Review And Coordination

- [x] 2.1 Add complete-chapter review with marker, length, prose, continuity, foreshadow, and entity validation
- [x] 2.2 Add a bounded chapter coordinator with budget checks and LLM metrics

## 3. Atomic Automatic Writing

- [x] 3.1 Replace the automatic write-chapter scene loop with one chapter coordinator call
- [x] 3.2 Atomically map parsed segments to scenes, create one content version, and run quality evaluation once

## 4. Verification

- [x] 4.1 Add unit and API tests for prompt composition, parsing, length gates, bounded repair, and atomic persistence
- [x] 4.2 Run focused and full backend validation plus strict OpenSpec validation
