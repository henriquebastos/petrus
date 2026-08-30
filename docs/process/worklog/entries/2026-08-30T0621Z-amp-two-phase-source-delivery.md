---
date: 2026-08-30T06:21:22Z
author: Amp
kind: milestone
related:
  - CV19.DS2
  - Hamsterdan CV21.DS2 prerequisite
verification:
  - uv run pytest -q tests/petrus/engine/test_execution.py tests/petrus/engine/test_engine.py tests/petrus/engine/test_observation.py tests/petrus/engine/test_postgres_engine.py tests/petrus/impetus/history_store/test_persistence.py tests/petrus/impetus/instance/test_ingress.py tests/petrus/impetus/instance/test_firing_occurrences.py tests/petrus/impetus/instance/test_instance_identity.py tests/petrus/impetus/instance/test_lifecycle_scopes.py tests/petrus/impetus/instance/test_resume.py tests/petrus/motus/worker/test_worker_topology.py tests/integration/test_activity_seam.py tests/dst/test_generated_runtime_world.py tests/dst/test_generated_runtime_qualification.py tests/dst/test_campaign.py tests/project/test_package_boundaries.py
  - uv run pytest -q tests/dst/test_joined_world.py
  - scripts/check release
---

# Public two-phase identified source delivery

## What changed

Petrus now exposes one identified source delivery through two public Engine
phases. `accept_delivery` commits `ExternalEventDelivered` plus `FiringBegun`
and returns a detached `AcceptedDelivery`; `complete_delivery` resolves and
completes only that accepted unfinished pure source occurrence. Exact
redelivery reconstructs an unfinished acceptance after load and returns
`PriorAcknowledgement` only after the occurrence ends. The convenient
`Engine.deliver` is the sole composed operation and commits between the
phases; it requires the same stable identity as `accept_delivery`, and
`Instance` owns only the two phase primitives.

Acceptance snapshots the complete token wire to its strict durable JSON
spelling before mutation. Public Engine records, in-flight occurrences,
markings, and firing outcomes are detached so caller mutation cannot rewrite
accepted History or later projection. Collision errors report recorded and
attempted source/scope values and whether canonical token content matches.
Identities, source paths, and lifecycle scope values admit only exact protocol
types, so a subclass cannot override durable spelling, prefix, or equality
behavior to bypass that judgment.
Sensor batches likewise admit only exact `Delivery` parcels before reading any
parcel field, and completion admits only the exact detached
`AcceptedDelivery`, so a subclass cannot redirect the source or occurrence
between validation reads. Every sensor parcel and Instance acceptance now
requires the adapter's stable identity; Petrus no longer derives an identity
that the adapter could not reconstruct after process interruption.
The source handler receives an isolated copy of the canonical delivery, so it
cannot mutate the already-durable acceptance or its redelivery index, including
after fresh reconstruction.
Fresh load also verifies that an ended accepted source occurrence has only a
writer-valid pure lifecycle: a lone failure, lifecycle cancellation, or one
globally contiguous ordered completion batch whose productions match the
source output arcs, colors, lifecycle scope, and exact queue-entry sequence. A
malformed terminal batch cannot turn an unfinished delivery into an
acknowledgement or introduce unrelated marking. Replay also proves that a
source with no declared handler completed with the exact built-in passthrough
productions and no delivery-registration effects; omission, substitution, or
forged registration authority is rejected. Replay also proves that a
source registration was armed at the exact acceptance position, matching the
live writer's admission rule, and rejects an uncorrelated registration open
outside the initial construction batch so a forged reopen cannot authorize a
delivery. Every firing-correlated registration effect must likewise belong to
its contiguous, ordered completion batch from the first production through
terminal completion before replay applies it, and that firing's complete begin
batch must remain contiguous at one instant, precede completion, match the
supplied net and handler purity, and remain valid even after it ended. An
interleaved or late begin fact cannot retroactively legitimize a completion
batch; every activity fact must name its occurrence's begun transition; and an
impossible ended firing therefore cannot re-arm a sealed source.
The live writer runs the same exact record-scalar validation before every
append, so it cannot create History that fresh reconstruction refuses. This
validation inspects original fields before replay detachment, does not
substitute detached replay copies for live records, and preserves ordinary
opaque token payload and identity semantics. Fresh replay also requires the
retained activity input, result, failure details, and quarantined outcome to
already use their canonical strict-JSON shapes before detaching them.
The construction prefix requires all initial tokens before its uncorrelated
default registrations; each such record must name one declared place exactly
once, carry non-empty tokens at the construction instant, and omit queue-entry
and scope metadata the live constructor never writes. A later initialization
is rejected even when a source-free net has no registration records to mark the
end of construction.
Handler effects use exact registration/key values, and runtime seal shares the
exact source canonicalizer, before either can alter authority. Terminal failure records
revalidate the writer's non-empty bounded error payload before they can make an
accepted occurrence appear ended. A source projection that raises appends that
terminal failure and asks the provider to commit it before propagation. After
an acknowledged commit, exact redelivery acknowledges the same ended occurrence
instead of rerunning it, and the original projection exception propagates with
deterministic non-empty failure text bounded to 4,096 characters. Refusal or
acknowledgement loss at the separate failure commit instead propagates the
storage error and poisons the Engine; fresh load decides whether the occurrence
remains unfinished or ended. In contrast, refusal of the prepared completion
append remains a storage failure: it records no terminal failure, leaves the
accepted occurrence unfinished, never renders or replaces the backend's
exception, and exposes that original exception. Fresh reconstruction and exact
redelivery then resume that same occurrence.
Exact redelivery through either the public acceptance door or a Sensor appends
nothing and does not invoke an empty provider commit.
Completion constructs separate writer-owned and detached return values before
the append, so a fallible copy cannot strand a durably completed call without
its return value, and neither value is re-derived from the other's record
length. Record validation preserves the kernel's opaque, totally ordered
`Instant` contract; strict durable backends remain responsible for their
encodable representation. Resume first captures and validates one tuple of exact base
records, and accepts construction authority only from the complete live-writer
prefix: one `InstanceCreated`, all initial tokens, and one canonical default
registration for every source. Those initial tokens must satisfy the same
shape, instant, and typed-place color rules enforced by live construction.

This milestone supersedes the delivery semantics and artifact authorities in
[`2026-08-18T2010Z-amp-dst-joined-delivery-boundary.md`](2026-08-18T2010Z-amp-dst-joined-delivery-boundary.md).
That entry remains the historical account of the former combined transaction;
the retained strict fixture paths now prove separate acceptance and completion
transactions. The delivery refusal fixture still has 10 operations, 17 journal
entries, and 7 checker evaluations. The acknowledgement-loss fixture now has
9 operations, 16 journal entries, and 7 checker evaluations: acceptance
survives the lost acknowledgement unfinished, then exact redelivery completes
that occurrence before a subsequent acknowledgement.

The current strict fixture authorities are:

| Fixture | Artifact | Profile | Checker | Journal |
| --- | --- | --- | --- | --- |
| `joined-delivery-commit-refusal-world-v3` | `sha256:0afa00107a196b56d340a442e2ba0842784f1e320e178190b9f5a4917b667ed9` | `sha256:539962bdbe6737e00bf065c4264aac5b9793c6ec4d2e5ef31929fa35a190a2da` | `sha256:12c29b1dfeb60c0772814239a541572e2ecc65353f18a9fe98cadfa498ef3ee4` | `sha256:362b508460976d44b5f043734b55874a9778aa62d59e5175df45976ccfaf3ff6` |
| `joined-delivery-ack-loss-world-v3` | `sha256:37bb56850c2170bf776a44cd67c0a1211be20f037a0e631b36592c5f7ec69106` | `sha256:865020a9eea08d2a7645ff82032a38a95ffd18280e4ef4c78d6a153e02d53e62` | `sha256:12c29b1dfeb60c0772814239a541572e2ecc65353f18a9fe98cadfa498ef3ee4` | `sha256:43c34a65646c2870b03dfaf2e6c0160c2f12f78c6138f90b1b43f99099c2bcc6` |
| `joined-reset-commit-refusal-world-v3` | `sha256:fdd034b68469659c2f2ec2d3377291485562fa6b89f2c0158dd76822ff27bdc0` | `sha256:445dd36e7f1a018ece468c853a51a12cfd288d637c7dfa184fc3860f267af7b9` | `sha256:a49ae8ead5ee4d1bd29168c518e1172a4060cc55385f5320eb80791ec5db4e77` | `sha256:d5144ac9c0e47c89b43da1d2cfbe5dc8195c2201c66e5b33e9120b1adee22cb8` |
| `joined-reset-ack-loss-world-v3` | `sha256:ee7b75368c9929a93e879dbba0b5041573591b98062a196035ed7b53eca32678` | `sha256:3e4a7ee05bf2b28d4091c0f1eb46f798416b27880ad849e82e3e6b2f4a4514e9` | `sha256:dd29aa9c467a91ab4c7281d9a3b49bbb93ab34d2a0765d06d6c0a2ef1e2d49c8` | `sha256:1b0a892b46e044a3ea56aaf3c8bb915bd2d4d8db65c07897a1bd68fbff0f85fc` |
| `joined-close-commit-refusal-world-v3` | `sha256:e38c3feac6babb6d12e70bbd054a5ea0d4e8e04ff04255ad96a2b914d2a35a2a` | `sha256:a7e7e205e076d461a828dc6a36649b701627e333448b690e73a88dd615342740` | `sha256:fd433d31b972396654b671e6a0ad0763fbb77d0ebee10957935e4fceaa2da8fa` | `sha256:cd972f54c112b30d5f7d78506a33ecda806975389dc803efe29f5de26c4a1729` |
| `joined-close-ack-loss-world-v3` | `sha256:8f84f3d6efc0009899b3d375cd711d2f4a41cfc2b2edffadce454902954595ba` | `sha256:e51278438abc7e7cd4b04bc44d8f2d45278241226d41dbec10c2840cb0830804` | `sha256:f7155d55860c976af3396e86a5129967e15cbb7a226ce37a8e0db8cbcf2735e0` | `sha256:ebb0c5fb6a4109c2e01eaf6325ae3d885b5132689cdd5687adb6e81cf212d6de` |
| `joined-cancellation-commit-refusal-world-v3` | `sha256:b8795fee18c23ac7a2f47acdfdce0462c8d82042e5417e9129825e3c33b7e842` | `sha256:8714c30dae172fbc745414fcec8c2475d04e5dada92876a1c94cfd87ef12abd1` | `sha256:5a923b7ea4d3fb3aeb17cfbbc31ca585683602640c0fb5be572d696eeab2338e` | `sha256:7b1b2a26aba24e96a973043e73796cc469473b274e9ac0ba71f0f681ae799b82` |
| `joined-cancellation-ack-loss-world-v3` | `sha256:6570c9b94cbaa79b26c58d2750897eeb1e65279bc4c549f524554a7f06d5c0ae` | `sha256:d324d7d884db9ddcb3d69f182c7fc85ca609b669bffd9fc8514f45b04c078bb6` | `sha256:5e8f7248580e197ed620e02c5d2dccff068b24aab219cb149defc8070884a4aa` | `sha256:8619595bcda8270d5204123bf3564dbec503f65ea3d74c578464e44ff1b8bb79` |

## Why it matters

Hamsterdan CV21.DS2 needs accepted and folded to be separate reconstructible
cuts. It can now persist the detached acceptance or reconstruct it by exact
redelivery after `Engine.load`, without private Instance access and without
using broad `Engine.advance` reconciliation.

## Verification

- The related Engine, Instance, provider, persistence, observation, worker,
  generated-runtime, activity, and package-boundary matrix passed all 566 tests.
- The joined real-boundary DST file passed all 67 tests in isolation.
- `scripts/check release` passed all 2,591 tests in both the four-worker and
  fixed-order runs; the fixed-order run reported 17 expected qualification
  deselections.

## Follow-up

Hamsterdan must persist `AcceptedDelivery` or reconstruct it by offering the
same identity/source/token/scope after `Engine.load`, then call
`complete_delivery`. It must not substitute broad `advance()` for exact source
completion.
