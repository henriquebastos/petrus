---
status: Decided
raised: 2026-07-24
decided: 2026-07-24
deciders:
  - henrique (Navigator)
supersedes:
  - earlier provisional licensing posture
related:
  - LICENSE
  - LICENSE-SCOPE.md
  - THIRD_PARTY_NOTICES.md
---

# Apache governs Petrus-authored material with explicit exceptions

## Decision

Petrus-authored source, tests, specifications, documentation, scripts, and
configuration are licensed under Apache License 2.0 unless a more specific
notice applies.

The vendored Absurd SQL schema identified in `THIRD_PARTY_NOTICES.md` remains
under its upstream Apache-2.0 license and copyright. Package-manager-resolved
dependencies retain their own licenses and are not relicensed by Petrus.

## Rationale

This matches the exact scope stated by `LICENSE-SCOPE.md` and keeps the one
vendored upstream artifact explicit without implying ownership of dependency
code.

## Consequences

- License scope and third-party notices travel with distributed artifacts.
- Any newly vendored material requires its own provenance and license review.
- Dependencies continue to be governed by their respective licenses.

## Review Trigger

Revisit when vendored material is added, removed, or modified, or when a
distribution begins bundling dependency source.
