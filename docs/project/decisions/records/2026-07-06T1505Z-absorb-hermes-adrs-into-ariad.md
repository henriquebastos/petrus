---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
related:
---

# Absorb the hermes notebook: ADRs become Ariad decision records

## Question

The hermes design notebook (35 ADRs + CONTEXT.md glossary) is Impetus's design under another name, but it was produced with the grill-with-docs skill using ADR nomenclature, while Impetus uses Ariad (chosen as more iterative). How do the two reconcile?

## Decision

Absorb the hermes work into this repository, mapping formats 1:1:

- Each hermes **ADR** becomes an Ariad **decision record** under `docs/project/decisions/records/`, dated by its original hermes commit date, `status: Decided` (ADR "Superseded"/"Proposed" map to `Superseded`/`Open`), with the original ADR number preserved in the filename and title for traceability.
- Hermes **CONTEXT.md** (the domain glossary / ubiquitous language) is adopted as `CONTEXT.md` at the repo root, with provenance noted.
- Hermes PROJECT-BRIEF content folds into `docs/project/briefing.md` during the upcoming vision rewrite; CURRENT-STATE open questions seed the design-phase exploration stories.
- The hermes repo retires to scratchpad status; Impetus is the canonical home going forward.

## Rationale

Ariad decision records are already one-file-per-decision with a status lifecycle — structurally the same artifact as an ADR. The difference is method (how decisions get made iteratively), not storage. Migrating preserves all 35 decided questions as Impetus's foundation without re-litigating them, while future decisions follow the Ariad loop.

## Consequences

- Migrated records carry `related: hermes ADR NNNN`; their content is faithful, not rewritten.
- Future supersessions of migrated decisions happen as normal Ariad records.
- Grill-with-docs remains usable for grilling sessions, but its output lands as Ariad decision records in this repo.

## Review Trigger

None — structural decision, revisit only if the migrated corpus proves hard to navigate.
