---
status: Decided
raised: 2026-07-19
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - DEC-033's unresolved proposal to make Velocitron the first Impetus frontend candidate
  - DEC-033's unresolved proposal to import a declarative replay-property pass now
  - DEC-033's unresolved proposal to standardize a firing-outcome projection now
  - DEC-033's unresolved proposal to commission an immediate Matt/HB alignment packet and prefer Velocitron simulator interoperability
  - ADR 0018 only for the claim that every cross-token correlation can live in a positive-binding transition guard
related:
  - docs/project/decisions/records/2026-06-21T1724Z-hermes-adr-0018-arc-inscriptions-simple-guards-own-cross-token-logic.md
  - spec/net-schema.md
---

# Impetus owns a versioned Net-definition protocol; frontends remain independent

## Question

Which findings from the Velocitron comparison should Impetus carry forward for
authoring, correlated inhibition, replay properties, portable conformance,
History projection, collaboration, and editor direction?

## Decision

Resolve the five DEC-033 calls independently. Impetus owns its serializable
Net-definition boundary. Petrus schema v2 and the existing Petrus editor are
the concrete baseline; Velocitron may become a frontend but does not own the
contract or replace the editor. Accept correlated absence as a semantic
requirement whose exact shape needs a focused exploration. Keep replay
properties and a normalized History projection deferred until concrete
evidence or a consumer earns them. Record, but do not commission, a future
protocol conversation with Matt before Velocitron adapter or shared-artifact
work.

### A — An Impetus-owned Net-definition protocol

Impetus should expose a clear, language-neutral, serializable Net-definition
protocol and a loader/compiler boundary that produces a validated Impetus
`Net`. Direct Python construction, a thin DSL, the Petrus editor, Velocitron,
and other tools may all produce that definition. No frontend owns the in-memory
`Net`, Engine, Instance, or runtime semantics.

Start from the public MIT Petrus flat-file schema v2 and the existing
TypeScript Petrus editor. Preserve Net-definition file schema v2 unchanged if
it honestly expresses Impetus. If Impetus changes the contract, identify the
new format as **Net-definition file schema v3**. There is no backward-
compatibility promise to Petrus: reuse the unencumbered baseline, change what
Impetus needs, and change the version when the contract changes.

Always qualify this as the **Net-definition file schema** so it is not confused
with independently versioned canonical History envelopes.

Editor integrations consume the versioned Net-definition protocol.
Editor implementation details are maintained separately.

### B — Correlated inhibitor anti-joins are required

Impetus should support the enabledness question “there is no token in this
inhibited place correlated with the current positive binding.” A transition
guard sees the selected positive consume/read binding but cannot quantify the
absence of a matching token in an inhibited place. This is distinct from
ordinary positive cross-token correlation.

Open a focused exploration before changing `Arc`. Use several concrete cases,
including per-key suppression, duplicate prevention, and lifecycle exclusion,
to compare the current denormalized workarounds with candidate shapes. The
exploration must determine the expression environment, interaction with color,
filter and weight, stable enumeration cost, failure posture, ordering, and
analysis consequences. It may consider Velocitron's
`correlate(binding, token)` as prior art but must choose the smallest
Impetus-native shape.

ADR 0018 remains binding for ordinary arc simplicity and positive cross-token
guards. It is reopened only where a positive-binding guard cannot express
correlated absence over the inhibited place.

### C — Replay properties remain a candidate

Do not commission a property framework now. First inspect Velocitron's actual
property vocabulary and compare it with concrete Impetus assertions over final
markings and one recorded History: place bounds/emptiness, occurrence
terminalization, key correlation, and firing bindings. Any later proposal must
distinguish replay assertions over one observed run from model checking over
all possible executions.

### D — Conformance follows the definition protocol; History projection waits

Portable valid/invalid examples, expected diagnostics, canonical parse/write
fixed points, and equivalent lowering from multiple frontends are required
evidence for the Impetus-owned Net-definition protocol in A. They are not a
separate Velocitron import and do not justify inventing a second Impetus JSON
format before the Petrus v2 baseline is assessed.

Do not standardize a narrow firing-outcome projection from canonical History
now. Such a derived view becomes useful only when a concrete cross-runtime
execution-conformance consumer exists. It would never replace, rename, narrow,
or become a second authority beside Impetus History; failure semantics may
remain profile-specific because transactional rollback and durable occurrences
are deliberately different.

The two stale `VELOCITRON-DIVERGENCE` markers may be corrected factually to
reflect current Candidate Selection and the deliberate journal/History scope
distinction without creating that projection.

### E — Collaboration is a later adapter gate; Petrus remains the UI baseline

Do not commission a Matt/HB protocol conversation now. Record it as a gate
before any Velocitron adapter or shared schema, grammar, fixture, or source
reuse: compare the formats, ask whether Velocitron should export the
Impetus-owned definition, preserve runtime-profile differences, and establish
reuse permission and licensing.

Do not adopt Velocitron's Graphviz-oriented simulator as the Impetus editor
direction. The existing Petrus editor is the more advanced and relevant UI
baseline. Velocitron may still contribute authoring-language, composition,
diagnostic, or conformance ideas.

Matthew Scott has consented to the existing source-derived Velocitron study
being present in the public Impetus repository. That publication consent is
separate from, and does not grant, a license to reuse private Velocitron source
or artifacts.

## Rationale

The original comparison correctly found complementary centers—Velocitron's
portable authored definition and Impetus's durable Instance—but it overlooked
the stronger lineage already available to Impetus. Petrus schema v2 provides a
public MIT flat-file contract for independent editor integrations. Making
Velocitron the canonical frontend would surrender independence and duplicate
or ignore that working baseline.

Owning the serialized boundary preserves frontend freedom. Honest format
versioning allows Impetus to reuse Petrus where it fits and change it where its
new semantics require more. Conformance makes the boundary executable rather
than aspirational.

Correlated absence is the one demonstrated semantic gap that ordinary guards
cannot express. Accepting the requirement while delaying the exact public API
keeps the semantics honest without copying another project's inscription
shape. Replay properties and normalized firing projections remain attractive
but currently lack concrete Impetus consumers, so the project's concrete-first
discipline keeps them as evidence rather than work.

## Options Considered

- **Accept all five original recommendations.** Rejected: it coupled Impetus's
  authoring direction to Velocitron, understated the existing Petrus editor,
  and commissioned analysis/projection work without concrete consumers.
- **Accept only collaboration first.** Rejected: Impetus can settle ownership
  of its definition protocol and correlated-absence requirement independently.
- **Choose item by item — chosen.** Preserve the useful comparison while
  restoring the Petrus baseline and keeping speculative work deferred.

## Consequences

- ES-026 becomes Candidate with its five carry-forwards adjudicated.
- ES-041 owns the correlated-inhibitor exploration; no `Arc` change is
  authorized by this record.
- A future Net-definition delivery story must begin from Petrus v2, use v2
  unchanged or declare v3 when changed, and include portable conformance.
- No property framework, normalized firing-outcome projection, Velocitron
  adapter, Matt conversation, editor rewrite, or shared private artifact is
  commissioned now.
- Editor implementations are maintained separately from this runtime.
- Canonical History, durable occurrence semantics, registered ingress,
  Instance authorship, pure guards, permissive places, timers, and operational
  telemetry remain unchanged.

## Review Trigger

Return when the Net-definition loader/compiler is planned; the v2-to-v3 delta
is concrete; ES-041 has executable evidence for an inscription shape; at least
one real consumer needs declarative replay properties; cross-runtime execution
comparison needs a normalized projection; or a Velocitron adapter/shared
artifact is proposed.
