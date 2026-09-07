---
status: Decided
raised: 2026-09-06
decided: 2026-09-06
deciders:
  - Driver, under the accepted Hamsterdan credential-refresh plan
---

# 1. Refresh direct Pi authority before new work after reconstruction

A reconstructed Pi A2 host must request its installation's current credential
before starting new work. A retained READY connection is encrypted custody, not
an alternative authority. Terminal replay and readiness probes remain credential
free. The public factory API remains unchanged.

Use the existing custody `rotate` operation for a retained READY connection;
authorize absent or previously erased authority as before. Track successful
initialization separately from attempting the one-shot supplier so a failed
refresh cannot fall back to the retained credential on a later operation.

## 1a. Correctness sketch

The operation ledger owns settlement and replay. Connection custody owns the
current encrypted credential, generation, and lease fences. No operation history
is deleted. New work must never use an unrefreshed retained connection; failed
retrieval must remain failed for the lifetime of that host. Rotation increments
the authority epoch and cancels prior leases through existing custody semantics.

Each host requests one bounded credential buffer at most once. Progress requires
a ready runtime, a valid current supplier, and functioning local storage. Existing
deadlines and operation bounds remain unchanged. Tests control the credential
supplier and scripted runtime; OS process death is the real crash boundary.

The consequential cuts are before rotation commits, after rotation commits, and
after operation completion before host cleanup. Fresh reconstruction retries from
current installation authority; retained terminal replay must never redispatch.
Fake runtime observations of the exact credential and supplier call counts judge
the behavior independently of custody's stored credential implementation.

## 1b. Verification and delivery state

All 27 tests in `tests/petrus/agenticus/runtime/test_pi_a2_host.py` passed in an
isolated Linux amd64 container running the current source. This includes actual
child-process exit after completion, clean shutdown, fresh-key use on two new
operations, failed-refresh refusal with no retained-key fallback, credential-free
terminal replay, and the existing killed-incomplete-operation classification.
Focused Ruff, formatting, type and architecture checks passed.

The canonical `scripts/check full` passed under native Linux arm64 with Python
3.14.7: 2,595 tests passed in 53.99 seconds, with no selected skips. Ruff,
formatting, type and architecture checks also passed. The test container included
Node 22.19.0, Graphviz, procps, system Python, Docker access and the repository's
Git metadata. The prerequisite gaps found in earlier disposable runs were
corrected; those runs are not counted as passing evidence. The Mac focused run
had two existing Hands failures reproduced with the unchanged HEAD, and its full
command could not start without `flock`.

The full gate initially scanned the bundled Ariad adoption script and rejected
its formatting. Ruff now excludes installed `.agents/skills` packages; project
source remains included and the installed package is unchanged. The development
guide records the full suite's external tool requirements.

Review found no need for a new credential API, persisted format, synchronization
mechanism or operation-history reset. The Driver recommends recording the
validated change under the local automatic checkpoint policy. Publication and
Hamsterdan's dependency pin remain pending the shared-history checkpoint. No
issuer-side rotation or production migration is claimed.
