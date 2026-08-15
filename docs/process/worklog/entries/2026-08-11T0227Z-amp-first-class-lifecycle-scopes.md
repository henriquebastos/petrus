---
date: 2026-08-11T02:27:07Z
author: Amp
kind: milestone
related:
  - ES-051
  - CV8.DS6
  - docs/project/decisions/records/2026-08-11T0101Z-history-first-lifecycle-scopes.md
verification:
  - post-repair History, Instance, Engine, Dispatch, Worker, transport, and integration boundary — 1246 passed
  - focused lifecycle, codec, Local, Absurd, Worker, transport, and integration boundary — 449 passed
  - real PostgreSQL and pinned Absurd lifecycle cancellation/restart route with skips forbidden — 1 passed
  - scripts/check full — static gates and 2168 passed
  - scripts/check release — 2168 passed in parallel, then 2168 passed with 17 explicit external qualification routes deselected
  - independent adversarial review — approved after exact replay, compatibility, codec, and documentation repairs
---

# Shipped History-first lifecycle scopes

## What changed

Petrus now owns first-class immutable lifecycle identity as
`(name, generation)`. Canonical History records scope open, exact close, and
atomic close-N/open-N+1 reset. Durable queue-entry identity and scope provenance
let replay and cleanup distinguish duplicate-valued token occurrences. Scope
provenance follows ingress, firing, movement, and Activity request records while
firing occurrence remains the same-generation execution owner.

Engine exposes `open_scope`, `close_scope`, `reset_scope`, and `active_scopes`.
Close/reset commits canonical cleanup before Dispatch cancellation is visible;
load repairs cancellation from History before republishing live outbox work.
Local Dispatch schema 3 adds transactional durable cancellation tombstones and
accepts an exact late fenced-claimant terminal for canonical quarantine. Pinned
Absurd uses its existing task tombstone without a schema fork. Inline and
In-Memory adapters provide the same provider-neutral fence contract within
their process lifetime. ZeroMQ remains transport over Local custody.

Scoped ingress proven to target a closed generation is acknowledged and
dropped. A bare scope name or future/otherwise unprovable exact generation is
quarantined and never silently retargeted. Late Activity terminals cannot
mutate a closed generation; exact redelivery acknowledges and conflicting
redelivery fails. Existing unscoped wire constants, record payloads,
`TokenQueue` equality/repr, Engine defaults, Activity Execution V2, and
Instance-scoped Worker contracts remain compatible.

Canonical records without lifecycle or queue-entry provenance remain schema 4;
lifecycle/provenance records use schema 5. One History and observation protocol
v1 page may interleave both record schemas, each with one canonical spelling.

## Why it matters

Hamsterdan can now replace one workflow generation through canonical Petrus
operations instead of application retirement topology. History remains the
business truth, Dispatch remains operational custody, and the host remains the
scheduler. Crashes after canonical close become recoverable cancellation repair
rather than a split truth. The implementation was built fresh from accepted
Petrus `main`; disposable experiment branches were evidence only and were not
integrated.

## Verification

The production boundary run passed 1,246 tests after replay and codec review
repairs. Focused lifecycle, History, Engine, Local, Absurd, Worker, sync/async
ZeroMQ transport, and integration coverage passed 449 tests. The real
PostgreSQL + pinned Absurd cancellation/restart route passed with skips
forbidden. `scripts/check full` passed all static gates and 2,168 tests.
`scripts/check release` then passed 2,168 tests in parallel and 2,168 in the
fixed order, with 17 explicit external installation/provider routes deselected
by project policy.

Independent adversarial review confirmed: close/reset replay requires the exact
append-position open occurrence set; observation/capture retain protocol v1
with per-record schema 4/5; unscoped codec and TokenQueue value surfaces remain
compatible; and the decoder rejects noncanonical alternate schema spellings.
The final review found no remaining code release blocker.

## Follow-up

No new technical-debt item is required. Intentional limits remain visible:
cancellation fences future accepted execution but cannot disprove an ambiguous
external effect; consumed inputs are never restored; compensation is explicit
domain work; an accepted projection-pending terminal finishes before close;
quarantine is an audit disposition rather than a reprocessing queue; Absurd
rejects a Worker terminal after provider cancellation and may clean tombstones;
observation snapshot v1 omits active scopes. Applications retain stable
downstream idempotency, lookup-first reconciliation, provider retention policy,
same-generation business ownership, and explicit compensation.
