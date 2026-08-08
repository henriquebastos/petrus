---
status: Decided
raised: 2026-07-19
decided: 2026-07-19
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/process/engineering-conventions.md
---

# Conventions 82–85 ratified as written

## Question

The ES-022 unit-0 parity review distilled four engineering conventions about
behavioral parity surfaces, derived-vector identity, strict canned oracles, and
copy discipline in recording stand-ins. Should they become project doctrine as
written, be amended, or remain observed but non-canonical?

## Decision

**Ratified, all four, as written** (DEC-030 option 1):

- **82** — a parity surface must carry the outcome's semantics, not its verdict
  alone.
- **83** — derived vectors need two identities: one for the document, one for
  the embedded text.
- **84** — a canned oracle must refuse prompts it does not recognize.
- **85** — a recording stand-in hands out copies in both directions.

The ruling adds no edits, conditions, or additional Navigator-authored
rationale. The complete canonical wording remains in
`docs/process/engineering-conventions.md`.

## Evidence Presented

Each convention records a concrete defect caught while hardening ES-022's
shared unit-0 substrate. Together they made the committed parity fixture
falsifiable and trustworthy: 82 exposes user-felt semantics, 83 prevents stale
or cross-model vectors, 84 makes fixture drift fail loudly, and 85 prevents the
instrument from being mutated by its subject. All three subsequent Mirror
variations were built and reviewed against that substrate at exact parity.

No project source moved between preparation and confirmation. The Zooming Out
session verified all four pinned source hashes before authority was requested.

## Authority

The Navigator ratified all four conventions without edits or conditions.

## Options Considered

1. Ratify all four as written — chosen.
2. Ratify with edits, especially narrowing convention 83.
3. Hold or reject one or more until another implementation supplied a second
   witness.

## Consequences

- Conventions 82–85 are project doctrine and should shape future design and
  review.
- The ES-022 unit-0 review loop is closed.
- DEC-029 may treat these conventions as ratified foundations of its parity
  evidence; this ruling does not prejudge DEC-029's architecture choice.

## Review Trigger

Revisit an individual convention only when contrary implementation evidence
shows its stated scope is too broad or its required discipline is insufficient.
