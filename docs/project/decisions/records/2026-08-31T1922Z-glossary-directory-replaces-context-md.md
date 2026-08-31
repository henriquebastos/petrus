---
status: Decided
raised: 2026-08-31
decided: 2026-08-31
deciders:
  - henrique (Navigator)
supersedes:
related:
  - ../../glossary/index.md
  - ../../exploration/es-062-consolidation-and-coherence-baseline/index.md
  - 2026-07-23T0315Z-agent-context-and-verification-stay-concrete.md
---

# Glossary directory replaces CONTEXT.md

## Question

Should the repository-root `CONTEXT.md` remain the ubiquitous-language
surface after the one-file-per-term glossary landed at
`docs/project/glossary/`, or should it be dissolved?

## Decision

`docs/project/glossary/` is the one canonical ubiquitous-language surface:
one term per kebab-case file, definitions of one or two sentences, rejected
synonyms under `Avoid`. `CONTEXT.md` is deleted, not retained as a
companion. Contract-level detail that lived only in `CONTEXT.md` was
re-homed into its focused owners before deletion (token-queue semantics,
Sensor retain-and-re-offer, Engine `DriveOutcome` host posture, the
`DrivingPolicy` re-ask contract, derived-handler inhibitor exemption — see
ES-062 WS2). Spec citation tags read `[glossary]` where they read
`[CONTEXT.md]`.

The 2026-07-23 ruling that the language surface is maintained by review and
coherence check, never mechanically proven line by line, transfers to the
glossary unchanged.

## Rationale

A "retiring companion" file is a standing drift surface: two homes for one
language guarantee divergence. Definitions belong in the glossary; behavior
and invariants belong in `spec/` and decision records; Git history preserves
the old `CONTEXT.md` text.

## Consequences

- New or changed terms go to `docs/project/glossary/` only.
- Historical mentions of `CONTEXT.md` in older decision records and worklog
  entries stay as written; they describe past state.
