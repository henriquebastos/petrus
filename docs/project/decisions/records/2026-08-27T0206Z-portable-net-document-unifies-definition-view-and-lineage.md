---
status: Decided
raised: 2026-08-27
decided: 2026-08-27
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/exploration/es-061-portable-net-document-and-forkable-execution-lineage/index.md
  - docs/project/roadmap/cv20-approachable-petrus/cv20-ds3-live-understanding.md
  - spec/net-definition-v3.md
  - spec/net-document-v1.md
---

# Portable Net document unifies definition, view, and eventual lineage

## Question

Should Arx arrangement, simulation, and captured production evidence use
separate top-level file models, or should Petrus own one portable document
whose optional facts determine what a consumer can show and safely change?

## Decision

Petrus owns one strict `petrus-net-document` v1 envelope. Every document
contains one exact canonical Net-definition v3 document. It may also contain
an identity-neutral portable view and, after a later Delivery story specifies
and implements it, one optional forkable execution lineage.

The static foundation carries node positions only. Paths directly address
places and transitions in the embedded definition; partial views are valid.
Moving a node changes view bytes but not the definition identity, which remains
the SHA-256 digest of canonical Net-definition v3 bytes.

The later lineage uses one flat entry sequence rather than distinct capture
and simulation trees. Entry ids are sequential integers equal to list indexes;
each non-root entry names an earlier parent. Observed and simulated entries
carry the same generic History-record fact with explicit provenance. Manual
interventions are explicit hypotheses in that same sequence. Retained source
artifacts remain immutable custody anchors rather than nested timelines.

Read-only versus editable behavior follows authority, not a different file
shape. For example, moving a node in a captured document changes only its
view. Changing a captured marking starts a manual branch and saves as another
document rather than overwriting the observed source.

## Rationale

Definition, arrangement, simulated steps, and observed steps share one Net and
one state-evolution vocabulary. Separate file models would make every consumer
reimplement navigation and conversion rules, while putting view or execution
facts into Net-definition v3 would incorrectly change semantic identity.

The flat parent-linked sequence makes ordinary continuation cheap and branches
explicit without recursive structures. Explicit provenance preserves the
important difference between production evidence and a hypothesis without
inventing unrelated event models.

## Options Considered

1. **Separate inspection, workspace, simulation, and capture formats.** Rejected
   as the long-term model because shared facts would drift behind conversion
   logic and users could not naturally continue from evidence into a branch.
2. **An Arx-owned workspace envelope.** Rejected because definition, History,
   and provenance are Petrus contracts; other consumers need the same portable
   truth even when Arx is absent.
3. **Add layout to Net-definition v3.** Rejected because moving a visual node
   must not change canonical Net identity.
4. **Use string entry ids or a recursive branch tree.** Rejected because one
   append-only array already supplies stable dense identity and parent links
   supply the branch structure.

## Consequences

- Net-definition v3 remains unchanged and independently usable.
- The current foundation strictly refuses unknown lineage fields until their
  contract and implementation land; pre-release v1 is complete only when
  CV20.DS3 closes.
- Arx derives current-Petrus interaction directly from the embedded v3
  definition and writes portable view facts without translating through its
  predecessor v2 workspace schema.
- Observation capture and simulation-result protocols remain source
  authorities during the later lineage bridge; this decision does not silently
  replace their current producers.
- Camera state, selection, panels, credentials, implementation bindings, and
  editor-local affordances remain outside the portable document.

## Review Trigger

Review before the first stable release of document v1, when lineage's concrete
schema is delivered, or if a non-Arx consumer demonstrates that direct node
positions or flat parent-linked entries cannot preserve required portable
truth.
