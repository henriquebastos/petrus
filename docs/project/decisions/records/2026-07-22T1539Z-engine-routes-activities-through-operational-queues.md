---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - the required-capabilities clauses of the 2026-07-14 activity-invocation runtime-seam decision
  - CV3.DS4's queue-per-capability vocabulary and Worker capability-advertisement contract, while preserving its queue, Worker, Absurd, lease, recovery, and atomicity evidence
  - ES-035's typed requirement/offer facet recommendation
related:
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
  - docs/project/decisions/records/2026-07-21T0809Z-concept-first-ontology-boundaries.md
  - docs/project/decisions/records/2026-07-22T0245Z-engine-is-one-live-instance-composition.md
---

# Engine routes Activities through operational queues

## Question

Must Impetus define a portable Worker capability vocabulary and match typed
requirements against Worker offers, or can Activity execution use explicit
queue routing while deployment systems ensure that polling Workers have the
code, resources, services, and authority they need?

## Decision

Extinguish **Worker capability** as an Impetus concept and production term.
Impetus will not model or match generic capability, territory, grant, host
trait, environment facility, protocol, capacity, affinity, locality,
attestation, or fallback facets for Worker placement.

One live Engine composes operational Activity routing for its one Instance.
The smallest configuration is a default queue plus optional per-Activity queue
overrides:

```text
default_queue = "default"
activity_queues = {
    "transcribe_video": "gpu",
}
```

This supports, without new scheduling logic:

- one Engine using one default queue;
- many Engines sharing one default queue;
- an isolated Engine using its own default queue; and
- Engines using private defaults while routing selected Activities, such as
  transcription, to a shared specialized queue.

Queue choice is operational routing for load balancing, throughput, tenancy,
and execution isolation. It is not Candidate Selection, Petrinet enabledness,
Activity semantics, Worker ontology, or a semantic History fact. Queue routing
configuration is held by the live Engine composition and may change between
`close` and `load`. Outstanding canonical Activity requests are routed using
the current Engine configuration when dispatched or republished; History is
not reinterpreted or rewritten.

Workers explicitly subscribe to one or more queues and register the Activity
implementations they execute. Receiving an Activity with no registered
implementation fails loudly. Queue subscription is operational configuration,
not a security assertion or proof of eligibility.

DevOps and provider infrastructure are responsible for placing and
provisioning Workers with the required compute, architecture, accelerators,
models, software, network reachability, service access, credentials, workload
identity, concurrency, and capacity. Impetus does not reproduce that control
plane. For example, a Worker serving a transcription queue is provisioned with
its GPU and model and with authority to obtain the requested video; Impetus
does not match those properties.

Activity input may carry business resource references such as an S3 URI and
non-secret references used to obtain authority, such as a credential, grant,
or Vault identifier. Raw credentials and secrets do not enter token data,
`ActivityInvocation`, or canonical History. A Worker resolves references
through its provisioned workload identity, credential broker, Vault, proxy, or
provider adapter while executing the Activity. Dispatch may carry ephemeral
secret material operationally when an integration requires it, but that
material is never canonical process truth.

Canonical History records the Activity request and accepted outcome, not its
queue, Worker, capacity, placement, environment, or routing explanation. The
current `capabilities` fields in `ActivityInvocation` and
`ActivityRequested`, the `--capability` Worker CLI option, and capability-based
queue vocabulary are implementation residue to remove through the bounded
Technical Story. There is no deployed-data migration requirement; any
incompatible durable data must be refused rather than silently reinterpreted,
consistent with the Engine–Instance lifecycle decision.

Changing routing must not create simultaneous operational custody of one
occurrence on old and new queues. Before republishing an outstanding request
under changed routing, Dispatch must retire, cancel, or conclusively reconcile
old queued custody. This is a Dispatch recovery invariant. It adds no semantic
record and does not make queue identity canonical.

## Rationale

The CV3 Workshop A/B incident proved that Workers tied to incompatible worlds
must not consume the same work. It did not prove that Impetus needs a generic
placement language. Under this decision, the shared `default` queue was a
deployment-routing error: use distinct queues, or provision every Worker on a
shared queue to execute every Activity and resource reference that queue may
deliver.

This shape follows the demonstrated Activity seam. The canonical request says
what imperative work to perform and carries its business input; the queue says
where operational custody should be offered now. Keeping those separate lets
an operator stop an Engine, change shared, isolated, or specialized routing,
and load it again without changing the durable Instance or inventing queue
selection semantics.

The approach also preserves the infrastructure boundary. Labels do not grant
authority, attest a machine, install a model, or reserve a GPU. Existing
deployment and secret-management systems already own those jobs and can
enforce them directly.

## Options Considered

- **Typed requirement/offer facets.** Rejected as unnecessary Impetus
  complexity. It would duplicate deployment placement, trust, resource, and
  fallback policy without executable demand for a portable matcher.
- **Flat capability tags.** Rejected as source vocabulary. The current string
  is a queue-routing key wearing an overloaded name; namespacing the strings
  would retain the conceptual confusion.
- **Opaque provider handles resolved by a generic Impetus matcher.** Rejected
  as core design. Activities may carry ordinary resource or authority
  references, and provider adapters may resolve them, without a generic
  placement model.
- **Explicit operational queues and registered Activities — chosen.** It
  preserves the useful CV3 machinery, makes deployment responsibility honest,
  and keeps History independent of execution topology.

## Consequences

- `capability` is not adopted Worker or Dispatch ontology. Current production
  names remain temporary implementation residue only until the routed
  Technical Story removes them.
- Engine composition owns a simple default queue and per-Activity overrides;
  no recursive routing policy or Candidate-Selection-like subsystem is
  commissioned.
- Workers subscribe to queues and register Activities. DevOps ensures that the
  subscription and deployment are valid.
- Different customers or workloads may share queues, use private queues, or
  combine private defaults with shared specialized queues without affecting
  canonical History.
- Queue changes between Engine runs are allowed. Dispatch recovery must prove
  exclusive custody while rerouting outstanding work.
- Resource and non-secret authority references may be Activity input; secrets
  remain operational and externally enforced.
- DEC-037 still owns Worker registration, incarnation, heartbeat, fencing,
  drain, revocation, and reconnect. This record does not adjudicate it.
- DEC-038 still owns operational Observation and Attempt shapes. This record
  does not adjudicate it.

## Review Trigger

Return to the Navigator if a concrete Activity cannot be routed safely with a
default queue plus per-Activity overrides; if correctness requires queue
identity in semantic History; if rerouting cannot preserve exclusive
operational custody; if a provider cannot enforce resource or authority access
outside Impetus; or if an executable deployment demonstrates a need for
portable resource matching rather than ordinary queue and provisioning
configuration.
