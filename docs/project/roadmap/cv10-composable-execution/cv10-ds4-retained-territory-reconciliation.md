---
code: CV10.DS4
level: Delivery Story
status: Done
status_reason: Qualified one hermetic single-host exact-lease release, reconstructed reclaim, and verified retirement route
updated: 2026-08-10
related:
  - CV10.DS1
  - CV10.DS3
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
---

# Reconcile one host-retained Episode territory

## Intent

Qualify explicit retained-territory custody without moving territory lifecycle
into Activity or Worker. A completed Episode may transfer one quiescent exact
lease and bounded public workspace archive to durable host custody; a
reconstructed host may reclaim that same lease into a distinct Episode
Attachment or retire it with verified cleanup.

## Scope

- Add one private, local SQLite custody state machine with a single live writer.
- Persist transfer intent before Attachment release and commit the bounded
  archive, digest, exact lease identity, owner, expiry, and generation before
  retention is acknowledged.
- Release through the Episode Attachment barrier: close admission, drain Hands,
  discard stages, export once, close grants, and transfer rather than destroy.
- Reconstruct one hermetic Gondolin provider and reclaim only the exact retained
  lease, without fallback creation, into a new Episode and Attachment epoch.
- Retire expired, corrupt, missing, or deliberately released custody through
  exact identity-correlated provider destruction and verified evidence.
- Keep Activity, Worker, runtime service, provider protocol, canonical History,
  and public package exports unchanged.

## Acceptance / Done Condition

1. **Given** durable release intent, **when** the Episode Attachment releases,
   **then** its public archive and exact lease enter retained host custody and
   the provider territory remains live without old Attachment authority.
2. **Given** a reconstructed host before expiry, **when** it reclaims custody,
   **then** lookup returns the exact original lease, no create fallback occurs,
   and a distinct Episode Attachment receives a new epoch and execution
   attachment restored from the durable archive.
3. **Given** missing, foreign, uncertain, expired, or corrupt custody, **when**
   reconciliation runs, **then** no territory is adopted or created and the
   exact recorded cleanup obligation remains fail closed until verified.
4. **Given** explicit retirement or expiry, **when** cleanup is verified,
   **then** the exact lease is absent and a bounded retired tombstone remains.
5. Activity and Worker code never call retention, lookup, reclaim, export,
   settlement, reconciliation, or destruction operations.

## Driver QA and Evidence Plan

- Pin the private custody state machine and Attachment release ordering with
  focused unit tests.
- Execute one hermetic fake-Gondolin release, process-level reconstruction,
  exact reclaim, second release, and retirement route.
- Inject crash-state records around release/reclaim/retirement boundaries and
  prove lookup-first, no-create, and fail-closed behavior.
- Run path-scoped static checks, focused Agenticus/Motus suites,
  `scripts/check full`, and `scripts/check release`.

## Out of Scope

- Multi-host custody transfer or provider-side fencing/CAS.
- Live Gondolin, authenticated model/provider, or credential support.
- Indefinite retention; every custody record has a finite expiry.
- Reconstructing an Attachment that was active when its host died.
- Preserving private provider files or runtime rollout as application state.
- Public execution, retention, Session, Activity, or Worker lifecycle APIs.

## Completion Evidence

- A private mode-0600 SQLite custody ledger writes release intent before
  Attachment closure, admits one live writer and one live obligation per
  provider operation, retains a bounded digest-verified public archive, and
  securely clears archive bytes after verified retirement.
- Attachment release closes and drains binding-wide runtime operation
  admission, including Gondolin private-file probe cleanup, before export and
  exact lease transfer. The old binding becomes stale without destroying the
  retained territory.
- A replacement Python process opened the same custody ledger and hermetic
  Gondolin root, reclaimed the exact lease into a distinct Episode Attachment,
  and released it for exact parent-side retirement. Reclaim has no creation
  fallback.
- Malformed durable identity types quarantine without provider cleanup;
  trustworthy temporary identity conflicts remain retryable retirement
  obligations. Incomplete release, reclaim, attached, and cleanup states fail
  closed toward exact retirement rather than reconstructing active work.
- Package-boundary tests keep the Codex Activity adapter and runtime service
  free of retained Territory lifecycle calls.
- Focused Agenticus and package-boundary verification passed 109 tests.
  `scripts/check full` passed 2067 tests. `scripts/check release` passed 2067
  tests in parallel and then 2067 tests with 17 external qualification routes
  deselected in fixed order.

The result qualifies only one hermetic local host state root. It does not claim
power-loss durability, live-provider support, multi-host custody, provider-side
fencing, or reconstruction of work that was active when its host died.
