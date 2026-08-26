---
date: 2026-08-26T18:00:00Z
author: claude-driver
kind: milestone
related:
  - ES-059
  - ES-056
verification:
  - UV_FROZEN=1 uv run pytest -q docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments — 183 passed (118 existing + 65 inscription-net)
  - ruff check / ruff format --check on the new directory — clean
  - ty check on all seven inet_* source modules — clean
  - CEL arc filter confirmed present in the retained canonical Net v3 golden
  - adversarial review round (gpt-5.6-terra) incorporated before commit
---

# ES-059 inscription-net experiment executed

## What changed

The fourth decision-structure spelling — the Navigator's "impure =
transition, pure = inscription/structure" extreme — is implemented under
`experiments/inscription-net/` and classified promising, behavior-equivalent
by design rather than byte-equivalent. A seven-combinator kernel (`await_`,
`fork`, `join`, `choice`, `effect`, `latch`, `>>`) over typed ports plus
eleven pure token methods lets the compiler derive every transition, arc,
and guard. Ordered choice generates mutually exclusive guards, and the
experiment's central refutation is that the naive NOT-chain is unsound over
marking-state — guards cannot test absence — forcing structural-exclusivity
subtraction plus a compile-time cover proof that refuses incomplete covers
by name. B's overlapping-guard counterexample yields one enabled candidate
here.

The rung budget, rung ordering, ladder exhaustion, and publication latch all
became structure; head identity, watermark ordering, operation ids, and the
`(lineage, fingerprint)` budget key refused — the last is a named behavioral
divergence outside the fixture. Effects fuse into their deciding branch for
exactly one firing per observation (108 History records vs 147), priced by
in-flight folded state and 18 predicate evaluations per decision. One CEL
arc filter enters the canonical Net v3 bytes; CEL guards are blocked by a
place-path addressing gap, pinned by test. The combined ES-059 conclusion:
combinators plus rich tokens made the hand-written Hamsterdan spelling cheap
to author and expensive to compile — the right side of that trade above an
authoring layer.

The experiment's own boundary held — it added only its directory, leaving
the three sibling experiments, `src/petrus`, `spec`, and normal `tests`
untouched. This integration commit additionally updates ES-059's index and
adds this worklog entry (orchestrator-owned files, outside the experiment's
boundary by design). An adversarial review round (gpt-5.6-terra) confirmed
and pinned two findings before commit: the fused effect's failure blast
radius (a terminal Activity failure destroys the folded watermark and wedges
the decision group — `FailureProjectingActivityHandler` is the seam a
promoted design must use) and token multiplicity sitting outside the cover
proof's Boolean-occupancy model (duplicate heads corrupt the structural
budget).
