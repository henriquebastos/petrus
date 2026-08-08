---
status: Decided
raised: 2026-07-23
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-23T1614Z-impetus-owns-versioned-net-definition-protocol.md
  - docs/project/decisions/records/2026-06-21T1724Z-hermes-adr-0018-arc-inscriptions-simple-guards-own-cross-token-logic.md
  - docs/project/decisions/records/2026-07-08T1605Z-guard-filter-evaluation-errors.md
  - spec/net-schema.md
  - spec/firing-semantics.md
---

# Correlated inhibitors use explicit binding-token correlation

## Question

What semantic and expression contract should Impetus use for the inhibitor
anti-join “enable this positive binding only when no admitted token in this
inhibited place correlates with it,” and how should that contract compose with
ordinary filters, weight, deterministic candidate ordering, and evaluation
errors?

## Decision

Adopt an explicit, optional **correlation declaration on an inhibitor arc** as
the semantic target. It remains distinct from the arc's ordinary color,
single-token filter, and weight, and from the transition's positive-binding
guards.

For each transition:

1. enumerate positive consume/read bindings and evaluate positive-binding
   guards in the existing deterministic order;
2. for each correlated inhibitor and each positive binding, scan the inhibited
   place in FIFO order;
3. apply the inhibitor arc's color and ordinary single-token filter first;
4. evaluate the pure correlation over one complete positive binding and one
   admitted inhibitor token; and
5. inhibit that positive binding when at least the arc's `weight` tokens
   correlate.

Correlation stably removes bindings; it never ranks or reorders them. Several
correlated inhibitors compose as conjunction in Net input-arc order. An
inhibitor with no correlation keeps its existing whole-transition meaning.

The declaration uses the existing pure expression tier: a named implementation
receives `(Binding, Token)`, while CEL receives the positive consume/read place
lists plus one reserved value representing the inhibitor token. It never sees
the wider marking, performs external calls, or introduces general
quantification across several places. The exact reserved CEL identifier,
Python constructor field, and serialized Net-definition spelling remain for
the receiving Delivery story.

Declaration and compilation mismatches fail before enablement. A correlation
evaluation error means the affected positive binding is not satisfied: skip
that binding, emit a mandatory diagnostic naming the declaration, arc,
binding/token evidence, and error, then continue enumeration. This is distinct
from an ordinary filter error, whose already-decided behavior remains “that
token is not admitted” plus diagnostic. The resulting difference is
intentional: a correlation failure cannot be mistaken for proof that the token
is unrelated, while this decision does not silently change filter semantics.

## Rationale

ES-041 proved the gap through the production candidate pipeline. A whole-place
inhibitor vetoes before positive bindings exist, while a transition guard sees
only consume/read selections and cannot inspect or quantify absence in the
inhibited place. Account suppression, duplicate prevention, and lifecycle
exclusion all need the same anti-join, and current partitioned workarounds grow
places, transitions, arcs, and routing per known key. [E]

An explicit declaration preserves each existing boundary. Color and filter
remain single-token admission; guards remain positive-binding correlation;
the inhibitor place remains visible Net structure; named code remains the
escape hatch; and enabledness remains pure and replay-deterministic. The
experiment pinned stable ordering, weighted correlated counts, ordinary-
inhibitor coexistence, multiple correlated inhibitors, named and CEL contexts,
and both error outcomes across 18 focused cases. The full suite passed 2,032
tests with 5 optional skips. [E]

The uncached semantic floor is honest: with `B` positive bindings and `A`
color/filter-admitted inhibitor tokens, worst-case correlation work is
proportional to `B × A`, with early exit after `weight` matches. That cost does
not justify putting an index or cache into the semantic contract.

## Options Considered

- **Partition the marking and topology per key.** Valid with current semantics
  but grows topology/routing per known key and does not serve dynamic or
  unbounded key domains without topology generation.
- **Overload the existing arc filter with binding-aware arity.** Rejected: it
  breaks the one-token filter contract, behaves differently on one arc mode,
  and cannot cleanly compose ordinary token admission with anti-join
  correlation.
- **Expose the wider marking to transition guards.** Rejected: it introduces a
  general marking-query capability, hides the inhibited place's structural
  role, and weakens the current guard boundary.
- **Declare equality key paths only.** Rejected: it creates a narrow field-path
  mini-language and lacks the ordinary-code escape hatch needed for real
  correlation.
- **Use an explicit inhibitor-only correlation — chosen.** It is the smallest
  shape that preserves existing concepts while expressing the accepted
  anti-join.

## Consequences

- ES-041 becomes Candidate with executable evidence and this semantic target.
- ADR 0018 remains binding for ordinary single-token filters and positive
  cross-token guards; this declaration exists only for absence a positive
  guard cannot express.
- The existing guard/filter evaluation-error decision remains unchanged for
  filters and guards; this record adds the new negative-correlation judgment's
  fail-closed-per-binding posture.
- No production `Arc`, enabledness, CEL, spec, public API, or serialized schema
  changes are authorized inside ES-041.
- A receiving Delivery story must choose the exact in-memory/wire spelling,
  implement instantiation validation and diagnostics, preserve timer and
  ordering invariants, update normative specs and glossary, and add portable
  conformance. A changed Petrus-v2-derived file contract is Net-definition file
  schema v3 under the existing versioning decision.
- Indexing, caching, generalized relational joins, multi-place negation, and
  arbitrary quantifiers remain out of scope.

## Review Trigger

Return at the correlated-inhibitor Delivery Plan Checkpoint; when the
Net-definition v2-to-v3 delta is specified; when a measured workload justifies
an index; or if implementation evidence shows the bounded CEL environment,
per-binding error posture, weight composition, timer integration, or stable
ordering cannot be preserved as ruled.
