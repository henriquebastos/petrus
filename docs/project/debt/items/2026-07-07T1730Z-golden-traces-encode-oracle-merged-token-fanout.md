---
id: golden-traces-oracle-merged-token-fanout
status: Paid
kind: test
severity: medium
revisit_trigger: Changes to canonical trace or History schemas.
closure_condition: Generate and replay fixtures using canonical Impetus semantics.
---

# Golden traces must encode canonical runtime semantics

The conformance corpus must cover per-arc output, single-typed tokens,
recorded source delivery, and guard enumeration over candidate bindings.
Fixture generation and replay must be self-contained in this repository.

The technical risk is accepting fixtures that encode different behavior
from the ratified specification. Repository-owned generation and replay
tests establish the contract without external regeneration dependencies.

## Resolution

Paid 2026-08-09. Eight deterministic fixtures generated from public Impetus
APIs cover the baseline and required divergence cases. Two consecutive
generations were byte-identical, focused checks passed, and release
qualification passed its parallel and fixed-order serial runs.

See `spec/traces/README.md` for current generation and replay instructions.
