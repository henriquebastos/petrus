---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-07T2118Z-permissive-flow-defaults.md
  - docs/project/decisions/records/2026-06-21T0749Z-hermes-adr-0006-support-consume-read-and-inhibitor-arcs.md
  - docs/project/decisions/records/2026-07-08T0048Z-token-flow-support-line-r3.md
---

# Analysis: three-tier commitment and the OUT OF REACH refusal

## Question

The Navigator's verification dream — prove no race conditions, completeness,
soundness — hit state-space explosion on Petrus. What analysis does Impetus
commit to, given that inhibitor arcs make the net class Turing-complete
(unbounded behavioral verification undecidable in general) and colored data
compounds the explosion?

## Decision

**Three tiers, plus a standing refusal** (full catalog: ES-006 `b1`–`b3`):

- **T1 — Instantiation validation** (already decided
  [DR permissive-flow-defaults, ADR 0021]): the validation run at instance
  build. The floor, not new scope.
- **T2 — Structural analysis on the uncolored skeleton** (default-on):
  invariants and state-equation refutations (linear algebra),
  siphon/trap reports (size-capped), subclass detection with polynomial
  free-choice/WF results where the shape lands, structural reduction,
  conflict-site listing. **No state space exists to explode.**
- **T3 — Opt-in bounded behavioral checks**: budgeted Karp-Miller
  coverability on the inhibitor-free skeleton, bounded colored exploration
  with stubborn-set reduction, bounded confluence probes. Only three
  verdicts: PROVEN-WITHIN-BOUND / REFUTED-WITH-WITNESS / BOUND-EXHAUSTED —
  the bound is enforced, so explosion is structurally impossible.
- **OUT OF REACH — do not attempt**: unbounded behavioral proofs on the
  full class (no-deadlocks-ever, general soundness, no-races-ever). This is
  undecidability, not a tooling gap; the answer to such requests is a T2
  theorem, a T3 bounded verdict, or reshaping the net down the
  expressiveness ladder.

Two standing rules: every verdict carries its **transfer label** (theorem
about the real net vs diagnostic about a projection, per the ES-006 `b2`
direction table); and **analysis never gates expressiveness** — only T1
rejects, for already-ratified reasons.

## Rationale

Safety-flavored results (bounds, invariants, refutations, termination)
transfer soundly from the skeleton over-approximation to the real net;
liveness-flavored ones do not — the tier design follows that asymmetry.
The Petrus path explosion was an unbounded (out-of-reach) question attacked
without bounds; the tiers fund the tractable half of the dream and label the
wall.

## Consequences

- Kernel/roadmap scope: T2 is the analysis investment default; T3 is
  explicitly opt-in tooling; nothing beyond is roadmapped.
- Tooling MUST surface bound exhaustion as a first-class outcome, never
  silently truncate (no-silent-caps).
- Admitting reset arcs (TF-40, deferred) would *worsen* the decidability
  landscape (boundedness undecidable for reset nets) — the r3 DR's warning
  stands.

## Review Trigger

Ratified with a partial picture; implementation will reveal tier contents.
Revisit tier composition when the kernel's validation/analysis surface is
built, or when a concrete user need appears to *move* a check between tiers.
The OUT OF REACH line itself moves only if the net class changes.
