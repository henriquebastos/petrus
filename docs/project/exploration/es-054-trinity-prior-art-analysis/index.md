---
artifact: exploration
code: ES-054
title: Trinity prior-art analysis against Petrus
status: Completed
status_reason: >-
  Pinned source inspection established that Trinity is a fleet control plane and
  isolated execution platform for CLI coding agents, while Petrus is a durable
  process runtime whose Petri-net state and append-only History are canonical.
  Trinity is useful prior art for an optional host/operations layer and for
  Agenticus runtime custody, but does not justify replacing Petrus semantics or
  promoting a current roadmap item.
created_at: "2026-08-15T04:36:24Z"
updated_at: "2026-08-15T04:40:27Z"
source_context: >-
  {"sources":[{"type":"github","url":"https://github.com/Abilityai/trinity/tree/499cac04a1bd3c4a9cca074a198387e03140eb56","label":"AbilityAI Trinity v0.8.5 at inspected commit 499cac04a1bd3c4a9cca074a198387e03140eb56"},{"type":"workspace","path":"README.md","label":"Current Petrus repository and retained architecture records"}]}
trigger: "Navigator requested analysis of AbilityAI Trinity against Petrus."
promotes_to: []
promoted_to: []
promoted_at:
---

# Trinity prior-art analysis against Petrus

## Inquiry

What does AbilityAI Trinity actually implement, how does it compare with
current Petrus rather than Petrus's aspirations, what should Petrus learn from
it, and which apparent similarities would violate Petrus's settled ownership
boundaries if copied?

## Executive conclusion

**Trinity and Petrus are adjacent systems, not alternative implementations of
the same runtime.**

- **Trinity runs a fleet of agents.** It is a self-hosted control plane that
  creates isolated Docker environments, schedules work, admits executions,
  invokes one CLI-agent runtime per container, tracks mutable execution rows,
  and gives operators a web/API/MCP product around that fleet.
- **Petrus runs durable processes.** It owns explicit Petri-net process state,
  records every firing in one append-only History per Instance, separates
  semantic truth from Activity custody, and can replay without re-running
  handlers. An agent is one possible handler implementation, not the durable
  subject.

The shortest product distinction is:

> **Trinity runs agents in production; Petrus runs durable processes in which
> agents may participate.**

This makes Trinity strongest exactly where Petrus has deliberately stopped:
fleet provisioning, environment isolation, global admission, operator APIs,
dashboards, governance, and deployment. Petrus is strongest exactly where
Trinity declines ownership: explicit workflow semantics, canonical process
history, deterministic replay, transition concurrency, and durable identity
independent of one agent session or container.

Trinity should therefore be treated as:

1. **strong prior art for an optional host/control-plane product above
   `Engine`;**
2. **useful implementation evidence for Agenticus runtime/container adapters;**
3. **a product-experience benchmark for deployment and operations;** and
4. **not a model for Impetus orchestration truth.**

No current Petrus roadmap change follows. Existing decisions already reserve
the relevant seam: many Engines may be hosted by a higher scheduler, Workers
remain replaceable operational capacity, provider infrastructure owns their
lifecycle, and a future optional read/operations layer may join provenance-
specific facts without becoming canonical.

## Research baseline and evidence labels

Trinity was inspected at exact commit
[`499cac04a1bd3c4a9cca074a198387e03140eb56`](https://github.com/Abilityai/trinity/tree/499cac04a1bd3c4a9cca074a198387e03140eb56),
whose repository version is `0.8.5`. Petrus was inspected at current local
commit `cac247d184933eea9e06c4a086b2396bc6e78407`. The comparison reads code,
schemas, tests, deployment composition, contributor invariants, and retained
architecture—not only marketing pages.

Claims use these labels:

- **[D] Direct** — stated or implemented in inspected source.
- **[I] Inferred** — interpretation from direct evidence.
- **[P] Proposed** — Petrus recommendation; not current behavior.

Repository popularity, commit count, and release packaging are maturity
signals, not correctness proofs. Trinity's breadth and deployment history are
not evidence that its orchestration model should replace Petrus's, just as
Petrus's stronger semantic model is not evidence that it already provides a
fleet product.

## The category distinction

```text
Trinity

trigger / chat / schedule
          │
          ▼
mutable execution row ──► admission / backlog / breaker
          │
          ▼
one isolated agent container ──► Claude Code / Gemini CLI / Codex
          │
          ▼
agent-owned session, files, tools, and optional pipeline state


Petrus

identified delivery / enabled binding / host advance
          │
          ▼
one authoritative Engine + durable Instance
          │
          ├──► canonical append-only History + replayable marking
          │
          └──► Activity request ──► Dispatch / replaceable Worker
                                      │
                                      ▼
                                 reported outcome
                                      │
                                      ▼
                          Instance-side canonical acceptance
```

Trinity's own contributor invariant makes the distinction explicit: it says
“Trinity ≠ DAG engine,” assigns stage advancement, retries, recovery, and
escalation to an agent-side heartbeat skill, and exposes only read-only files
for pipeline introspection. See
[`CLAUDE.md` lines 159–160](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/CLAUDE.md#L159-L160)
and the implemented
[`scheduling` requirement](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/memory/requirements/scheduling.md#L372-L419).
**[D]** The agent is the sole writer of pipeline instance state; Trinity never
mutates it. **[D]**

Petrus makes the opposite product choice. The durable subject is one net
Instance, and `event History + marking → enabled transitions → selected firing
→ recorded result → new marking` replaces the agent's hidden loop. Replay
re-applies recorded token movements without executing handlers. See
[`spec/OVERVIEW.md`](../../../../spec/OVERVIEW.md) and
[`docs/product/principles.md`](../../../product/principles.md). **[D]**

Neither choice is an implementation accident:

- Trinity deliberately leaves application process semantics inside an opaque
  and mutable agent environment so the platform can remain agent-flexible.
- Petrus deliberately extracts process semantics from the agent so process
  identity, recovery, inspection, and composition survive agent/runtime
  replacement.

The systems can therefore coexist in a stack, but substituting one for the
other changes the unit of durability and authority. **[I]**

## Capability matrix

| Capability | Trinity v0.8.5 | Current Petrus | Judgment |
| --- | --- | --- | --- |
| Durable subject | Agent, execution row, container files/session, and agent-owned pipeline state | Net Instance with one canonical History and marking | Different ontology, not feature parity |
| Workflow semantics | Explicitly agent-owned; no backend DAG executor | Runtime-owned colored Petri-net firing semantics | Petrus's primary differentiation |
| Canonical replay | No single replayable process log; mutable projections and runtime artifacts | Replays History without rerunning handlers | Petrus stronger |
| Execution record | Rich mutable `schedule_executions` row with status, cost, transcript, lease, retry, source, and session | Canonical Activity/firing records plus owner-specific operational Dispatch state | Different purposes; Trinity stronger as an operator read model |
| Terminal races | Atomic CAS protects one execution row and gates side effects | Instance alone authors canonical terminal History; late/duplicate terminals are rejected or quarantined | Both strong locally; Petrus has the clearer semantic authority boundary |
| Agent environments | One hardened Docker container per agent; persistent workspace volumes | Local processes and experimental territory/Attachment compositions; no fleet container product | Trinity substantially stronger |
| Runtime adapters | Claude Code, Gemini CLI, and Codex with declared capability matrix | Profile descriptors plus one narrow supported scripted Pi A2 route and experimental qualification surfaces | Trinity substantially more productized |
| Admission/capacity | Redis slots, per-agent limits, persistent backlog, fleet ceiling, breakers | Bounded local Dispatch custody; host owns multi-Instance scheduling | Trinity stronger at fleet operations |
| Retry/recovery | HTTP retry, status CAS, callback replay, slot/lease reapers, pull-mode work in progress, agent trace proposal | Frozen Activity execution policy, leases/epochs, heartbeat details, retries, reconciliation, canonical acceptance | Petrus stronger at stable execution semantics; Trinity broader operationally |
| External-effect guarantee | Recognizes at-least-once difficulty; partial sink guards and target retry-with-trace design | Explicit at-least-once contract, downstream idempotency/reconciliation, canonical ambiguity/quarantine | Petrus's current contract is more coherent and less agent-judgment-dependent |
| Event/history stream | Bounded Redis Stream for WebSocket delivery; durable task-event rows with best-effort wake | Uncompacted canonical per-Instance History; optional observation is non-authoritative | Different roles; do not conflate |
| Audit/governance | Users, roles, permissions, credential injection, platform audit, guardrails, retention, operator queue | Semantic History and scoped interfaces; no broad user/governance control plane | Trinity substantially stronger |
| Observation UX | Production web UI, REST, MCP, CLI, fleet dashboards, logs, costs, health | Protocol snapshots/pages plus separate read-only Arx companion | Trinity stronger operationally; Arx remains the right Petrus presentation owner |
| Scheduling inputs | Cron, webhooks, chats, channel integrations, agent delegation, bounded loops | Host calls `advance`, `wait`, and identified `deliver`; Fabric remains prototype | Trinity stronger as an application platform; Petrus more composable |
| Distribution | Docker Compose control plane, Redis, optional PostgreSQL, isolated containers; pull/work-stealing target is still evolving | Local-first execution, durable stores, Workers/transports, independently authoritative Instances; Fabric unfinished | Different maturity and topology |
| Local-first | Docker and several services required | Same semantic model can run in one Python process | Petrus stronger for embedding and minimal operation |
| Deterministic simulation | No process-semantic simulation | Bounded simulation and language-neutral golden traces | Petrus stronger |
| Multi-agent structure | Manifests, permissions, delegation, shared sessions/folders, events | Agents are handler/runtime choices; inter-Instance Fabric prototype | Trinity stronger as a fleet/social product; Petrus avoids making “agent” core ontology |
| Deployment product | One-command install, Compose stack, CLI, docs, releases, upgrade practices | Python package/source checkout; pre-release and unpublished | Trinity substantially stronger |

## What Trinity actually owns

### 1. Isolated fleet lifecycle

Trinity is first a control plane around Docker. Agent status is read from
Docker containers and labels, not an in-process registry, and one container is
the security, filesystem, runtime, and failure-containment boundary. See
[`docker_service.py` lines 33–79](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/docker_service.py#L33-L79)
and architectural invariant “Docker as Source of Truth” in
[`architecture.md`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/memory/architecture.md#L1120-L1122).
**[D]**

Its Compose deployment includes backend, frontend, MCP server, scheduler,
Redis, log collection, volumes, network separation, health gates, optional
PostgreSQL, and access to the Docker socket for agent lifecycle. The backend
itself is hardened with dropped capabilities and `no-new-privileges`; agent
containers add their own runtime controls. See
[`docker-compose.yml`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docker-compose.yml).
**[D]**

This is much more than Motus Dispatch. Dispatch offers work, preserves Attempt
custody, rejects stale epochs, and collects outcomes; it intentionally does not
create Workers, place them, inject provider credentials, manage their images,
or operate their fleet. DEC-037 explicitly assigns those responsibilities to
DevOps/provider infrastructure. **[D]**

### 2. A uniform execution envelope around heterogeneous CLI agents

Trinity's in-container `AgentRuntime` contract normalizes interactive and
headless execution, session continuity, MCP configuration, runtime readiness,
model context, transcripts, and cost reporting. Capability declarations default
conservatively, and unknown runtime names fail rather than silently selecting a
different engine. See
[`runtime_adapter.py` lines 20–38](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docker/base-image/agent_server/services/runtime_adapter.py#L20-L38),
[`lines 127–179`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docker/base-image/agent_server/services/runtime_adapter.py#L127-L179),
and
[`lines 182–225`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docker/base-image/agent_server/services/runtime_adapter.py#L182-L225).
**[D]**

Claude Code, Gemini CLI, and Codex are real supported product adapters rather
than catalog declarations. Codex, for example, has explicit session continuity,
result-file durability, process-group containment, credential sanitization,
runtime-specific guardrail limits, and estimated cost. **[D]**

This is the closest direct overlap with Agenticus. Trinity's reusable lesson is
not its exact Python ABC, but the shape of the qualification evidence:

- declare capabilities rather than infer them from runtime names;
- separate environment readiness from an execution result;
- make installation/runtime provenance visible;
- define one typed terminal envelope at the environment boundary;
- qualify process cleanup, session continuity, credentials, cost evidence, and
  result recovery per runtime.

Agenticus already follows several of these principles through profile
descriptors, installation ownership, runtime protocols, Attachments, and
qualification-only support claims. Trinity demonstrates how far the product
surface must go before “runtime support” feels operational rather than merely
structural. **[I]**

### 3. Admission, backlog, and failure containment

Trinity creates an execution row, acquires capacity, starts activity tracking,
calls the agent with retry, persists a sanitized terminal, closes activity
tracking, and releases capacity through one service path. See
[`task_execution_service.py` lines 1–17](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/task_execution_service.py#L1-L17)
and
[`lines 886–944`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/task_execution_service.py#L886-L944).
**[D]**

Capacity is an explicit product concern:

- Redis sorted sets own current per-agent slots;
- a bounded Redis list exposes in-memory chat pressure;
- SQL rows own persistent task overflow;
- admission clamps per-agent limits to a fleet ceiling;
- an optional per-agent dispatch breaker refuses known-unhealthy work before it
  poisons the backlog; and
- release drains the next persistent item.

See
[`capacity_manager.py` lines 1–36](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/capacity_manager.py#L1-L36),
[`lines 230–405`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/capacity_manager.py#L230-L405),
and
[`backlog_service.py` lines 1–24](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/backlog_service.py#L1-L24).
**[D]**

This is the strongest evidence for a future Petrus host layer. One `Engine`
must still compose exactly one authoritative Instance, but an application host
may eventually need inventory, registration, capacity budgets, admission,
fairness, and process supervision across many Engines. Existing Petrus
decisions put those concerns above `Engine`; Trinity shows a credible product
that lives there. **[I]**

It does **not** show that `Engine`, `Instance`, or Dispatch should own them.
Trinity itself has paid heavily for split SQL/Redis/container state and runs
watchdogs, cleanup sweeps, canary invariants, and reconciliation to keep those
operational projections aligned. Copying those concerns into Impetus would
increase semantic coupling without acquiring Trinity's operator product.
**[I]**

### 4. Mutable execution projection, not replayable process truth

Trinity's `schedule_executions` table is operationally rich: status, timestamps,
message, response, error, source identity, model, cost, transcript, retry,
queue, lease, claimant, redelivery, session, and channel correlation all live
on one mutable row. See
[`schema.py` lines 231–278](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/db/schema.py#L231-L278).
**[D]**

Trinity protects terminal races well within that model. Terminal updates are
atomic compare-and-set operations; only the winning writer closes activities,
records breaker outcomes, releases slots, and emits terminal events. Duplicate
or late callbacks therefore do not double-release capacity or duplicate
follow-on effects. See
[`task_execution_service.py` lines 784–812](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/task_execution_service.py#L784-L812)
and
[`lines 1750–1786`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/task_execution_service.py#L1750-L1786).
**[D]**

That is valuable operational engineering, but it is not Petrus History:

- the row records a latest projection rather than an immutable sequence of all
  process facts;
- current truth is deliberately divided among SQL, Redis, Docker process
  registries, session JSONL, agent files, and callbacks;
- no marking or enabled-transition state can be rebuilt from that row; and
- replay may resume a provider session, but cannot reconstruct and explain a
  general multi-stage process without trusting the agent's private state.

Trinity's own architecture calls `schedule_executions.status` a CAS-guarded
projection and says the agent process registry is runtime authority for whether
work is running. It also records an uncovered standalone-scheduler status-writer
race. See
[`architecture.md` line 387](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/memory/architecture.md#L387).
**[D]**

Petrus's separation between canonical History and owner-specific operational
state is therefore the more coherent base for long-lived business processes.
Trinity's rich execution row is nevertheless a much better operator projection
than Petrus currently ships. **[I]**

### 5. Observation and audit are product features, not semantic truth

Trinity has a real-time Redis Stream for WebSocket clients, reconnect cursors,
bounded catch-up, per-client queues, authorization-aware replay, and explicit
`resync_required` gaps. See
[`event_bus.py` lines 1–28](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/event_bus.py#L1-L28)
and
[`lines 53–65`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/event_bus.py#L53-L65).
**[D]**

Its contract is honestly liveness-favoring rather than lossless: the stream is
approximately trimmed, outbound overflow drops, slow client queues force
resynchronization, shutdown may leave events behind, and Redis outage uses only
a small process-local fallback. **[D]** This is good prior art for an optional
operations feed because it distinguishes resumable delivery from current-state
repair. It is not a candidate for canonical Petrus History. **[I]**

Trinity also has a broad append-only platform audit table, user/agent/MCP actor
attribution, exports, filters, retention, and an optional hash chain. The
marketing phrase “tamper-evident audit trail” needs one qualification: hash
chaining is disabled by default and audit writes are best-effort so they never
block the primary operation. See
[`platform_audit_service.py` lines 58–70](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/platform_audit_service.py#L58-L70)
and
[`lines 94–150`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/platform_audit_service.py#L94-L150).
**[D]**

This does not weaken Trinity's value as prior art; it clarifies provenance:

- Petrus History is correctness-critical semantic truth.
- Trinity audit is governance evidence about platform operations.
- Trinity's WebSocket stream is reconnectable presentation delivery.
- Docker/Redis/SQL/session files retain their own operational authority.

A future Petrus operations product should preserve exactly those distinctions
rather than offering one ambiguous “event stream.” **[P]**

### 6. Governance and operator experience

Trinity has production surfaces Petrus does not attempt today:

- user authentication, roles, sharing, agent-scoped API keys, and MCP access;
- encrypted credential injection and rotation;
- schedules, public webhooks, Slack/Telegram/WhatsApp inputs, and chat sessions;
- agent lifecycle, fleet views, health, costs, logs, timelines, and monitoring;
- operator queue and human intervention surfaces;
- read-only mode, tool budgets, timeouts, infrastructure-injected guardrails,
  audit, retention, and soft deletion;
- CLI deployment and management; and
- system manifests for creating related agents, permissions, schedules, and
  shared views.

These are the main reasons Trinity looks like a complete “agent platform” while
Petrus still correctly describes itself as a pre-release library/runtime.
**[D]** They are not cosmetic. The product value is the integrated operating
experience, not any one queue or adapter. **[I]**

Trinity's own security requirements also expose honest limits. Credential
isolation and network egress controls are incomplete, and the Docker boundary—
not model compliance—is the real containment layer. See
[`security.md` lines 313–416](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/memory/requirements/security.md#L313-L416).
**[D]**

## Where Petrus is structurally stronger

### Explicit process state instead of an opaque agent loop

Petrus makes places, tokens, transition enabling, binding, selection, begin/end
firing, and lifecycle scopes explicit. The runtime can explain why work is
enabled, awaiting, completed, or stuck without asking an agent to interpret its
own files. Trinity intentionally cannot: it knows an execution and an agent,
while any multi-stage meaning remains an agent-owned file and heartbeat skill.
**[D]**

This is not merely a visualization advantage. It makes deterministic code,
human work, external events, and agents composable under one process model.
Trinity's product ontology remains agent-centric. **[I]**

### One canonical history and deterministic replay

Every Petrus firing—including pure ones—records explicit token movements.
Activities add observed request and terminal facts. Replay never invokes a
handler and does not need provider session state. Derived marking and status
are rebuildable projections. **[D]**

Trinity has many durable records, but no single record set can recreate agent
pipeline meaning, container filesystem state, a CLI session, and fleet
operational state. Its session resume is provider continuity, not workflow
replay. **[I]**

### Identity survives workers, containers, and provider sessions

One Petrus Instance retains authority while Attempts expire, Workers restart,
and Activity implementations move. Dispatch tracks custody, and the Instance
accepts or quarantines reported terminals at a canonical History position.
Lifecycle scope identity is `(name, generation)` and resolves replacement races
by append order, not container/session identity. **[D]**

Trinity is improving toward leased pull/work-stealing execution, but its current
production path still contains runtime-specific asynchronous eligibility and
provider-session sentinels. Its target architecture explicitly describes
pull/work-stealing and retry-with-prior-trace as continuing work. **[D]**

### Honest external-effect semantics

Petrus states external effects are at-least-once and does not infer that
canceling custody means an effect did not occur. Stable downstream idempotency,
lookup-first reconciliation, retention, and explicit compensation remain
integration responsibilities; uncertain deliveries and late outcomes can be
quarantined as facts. **[D]**

Trinity recognizes the same impossibility. Its shipped sink-level effect guards
cover selected mediated actions, while its target direction proposes retrying
agents with prior traces and using deterministic gates or humans for
irreversible effects. See
[`TARGET_ARCHITECTURE.md` lines 602–612](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/planning/TARGET_ARCHITECTURE.md#L602-L612).
**[D]** The proposal is pragmatic for an agent platform, but a model's judgment
about prior trace cannot replace Petrus's canonical record of semantic facts.
It belongs inside an Activity implementation or application policy, not in
Impetus replay. **[I]**

### Local embedding and language-neutral semantics

Petrus can run its full semantic model in one Python process with in-memory
components, then move execution to durable stores and remote Workers without
changing process semantics. Its normative model and golden traces are
language-neutral. Trinity requires Docker and a multi-service platform because
environment operation is its product. **[D]**

### Simulation and authored semantic inspection

Petrus can inspect, render, and simulate the process definition independently
of executing a provider. Trinity can inspect fleet and execution status but
does not own enough process meaning to simulate an agent-defined workflow.
**[D]**

## Where Trinity is substantially ahead

### A product, not only a runtime

Trinity has a polished installation route, web UI, REST and MCP APIs, CLI,
operator documentation, versioned releases, deployment composition, screenshots,
and multiple user entry points. Petrus is explicit that package metadata remains
`0.0.0`, no PyPI publication is claimed, and support is pre-release. **[D]**

### Real isolated agent operations

Trinity's agent container is a qualified environment with persistent storage,
runtime setup, process cleanup, readiness, health, credentials, tools, logs,
SSH, result callbacks, and runtime-specific failure mapping. Petrus has strong
execution and qualification primitives, but only one deliberately narrow
supported Agenticus route and experimental evidence beyond it. **[D]**

### Fleet-wide admission and containment

Trinity already answers operational questions Petrus delegates to a host:

- Is this agent/container running and ready?
- How much per-agent and fleet capacity is available?
- Should new work queue, reject, or probe a recovering agent?
- Which executions are queued, running, stale, terminal, or orphaned?
- What should be reclaimed after backend or container failure?
- Which runtime/build/configuration is deployed?

Petrus's answer is correctly “the host/provider owns most of this,” but no
first-party product yet supplies that host. **[D]**

### Governance around autonomous code

Trinity treats authentication, access, credentials, audit, guardrails, human
escalation, retention, and costs as first-class product needs. Petrus protects
semantic boundaries and avoids credentials in durable state, but does not
provide a comparable administrative plane. **[D]**

### Failure-derived engineering maturity

Trinity's code and architecture contain many explicit race closures, cleanup
invariants, dual-store reconciliation paths, canaries, callback replay rules,
stale-slot recovery, deployment caveats, and source-specific timestamps. The
complexity is partly a cost of its mutable multi-store architecture, but it is
also evidence of operating the product against real failure modes. **[I]**

Petrus should learn from those failure classes before building a host product,
without importing the same state topology prematurely. **[P]**

## Transferable ideas by Petrus owner

### Impetus: preserve the current boundary

No Trinity control-plane concept should enter Impetus. In particular:

- agent/container lifecycle is not semantic Instance lifecycle;
- mutable execution status is not canonical History;
- CLI session resume is not replay;
- fleet capacity is not Candidate Selection;
- container health is not Activity success/failure;
- platform audit is not firing History; and
- agent-owned pipeline files must not become an alternative source of Petrus
  process truth.

The useful Impetus lesson is negative: Trinity validates the value of keeping
provider/fleet complexity outside the semantic kernel. **[I]**

### Motus: reuse operational patterns selectively

Motus already owns the narrower correctness-critical mechanics Trinity also
needed: attempts, lease/custody, heartbeat/deadline behavior, stale claimant
refusal, terminal idempotency, and replacement. Useful patterns to consider only
when a concrete Dispatch/Worker need triggers them are:

- one typed, provenance-rich worker terminal envelope;
- CAS/idempotent settlement before any release or downstream operational side
  effect;
- explicit machine-readable operational failure taxonomy;
- bounded redelivery and correlated-failure controls;
- backlog repair/reconciliation commands; and
- health/capability snapshots that remain advisory rather than authoritative.

Current Local Dispatch and Engine terminal acceptance already satisfy much of
the semantic requirement through a different design. There is no reason to add
a second generic execution-row abstraction. **[I]**

### Agenticus: strongest direct learning opportunity

Trinity's runtime adapter and base image provide the most applicable prior art.
Future Agenticus work can compare each profile against this evidence checklist:

1. installation identity and exact provenance;
2. capability declaration with least-capable defaults;
3. readiness distinct from catalog presence;
4. interactive versus headless execution contract;
5. session continuity and its durability limits;
6. MCP/tool configuration and credential boundary;
7. result/transcript/cost evidence;
8. timeout and process-tree cleanup;
9. terminal persistence before environment reply; and
10. environment loss, replacement, and retained-territory reconciliation.

Petrus should retain its stricter distinction between a profile descriptor,
qualification evidence, experimental composition, and supported route. Trinity
shows the operational destination, not a reason to weaken that support matrix.
**[P]**

### Future host/control plane: use Trinity as a reference design

If Petrus later commissions a concrete operator product, Trinity is strong prior
art for:

- an API that starts and tracks application-owned executions;
- many-Engine registration, admission, fairness, and capacity budgets;
- environment/Worker lifecycle provider adapters;
- fleet inventory and build/runtime capability reporting;
- provider, Worker, Dispatch, and History projections joined with provenance;
- reported-versus-canonically-accepted terminal state;
- reconnect cursors plus explicit gap/resynchronization semantics;
- bounded backlog, breaker, redelivery, and cleanup policies;
- cost/log/artifact links that remain operational evidence; and
- authentication, authorization, audit, retention, and operator intervention.

The layer should be optional and should keep operating authority separate from
semantic authority. Existing DEC-037 and DEC-038 already define this shape. A
concrete product requirement—not Trinity's existence alone—remains the trigger
for designing it. **[P]**

### Arx: consume joined projections, never become the mutating control plane

Arx may learn from Trinity's timeline, fleet grid, execution detail, health,
cost, and operator-facing information architecture. Its own product principles
already allow semantic, operational, provider, and application views to be
joined if provenance remains visible. **[D]**

Arx must not copy Trinity's lifecycle mutation surface. The retained Arx
boundary is read-only toward live Petrus systems; a future host service may
provide command APIs, while Arx can visualize the result. Presentation must not
become authority. **[D]**

## Patterns to copy, adapt, or reject

### Copy the lesson

- **Capability declarations.** Consumers should ask what a runtime/environment
  supports rather than switch on its brand name.
- **Deployment provenance.** Build, runtime, image, and profile identity should
  be visible to operators.
- **One terminal chokepoint.** Idempotent terminal acceptance should gate
  release, breaker updates, and notifications.
- **Gap-aware reconnect.** A cursor outside retention must produce an explicit
  resynchronization instruction, not silent incompleteness.
- **Operational failure taxonomy.** Capacity, auth, transport, timeout, lease
  expiry, and semantic Activity failure should not collapse into one string.
- **Failure containment.** Environment and subprocess cleanup deserve profile-
  specific qualification, not optimistic process termination.
- **Product runbooks.** Installation and operational recovery are part of the
  feature, not postscript documentation.

### Adapt to Petrus ownership

- Adapt Trinity's execution dashboard into provenance-aware views over History,
  Dispatch, Worker/provider, and application sources—not one mutable truth row.
- Adapt admission and breaker patterns into a future host, never Engine-local
  fleet policy or Impetus semantics.
- Adapt container/runtime custody into Agenticus environment providers, where
  an existing Activity invocation borrows the environment without making it
  canonical.
- Adapt audit/governance as a separate platform record joined to, but not
  confused with, semantic History.
- Adapt multi-agent manifests only as host/application composition; do not add
  “agent” as a transition kind or shared semantic authority.

### Reject

- Reject the agent as Petrus's durable process owner.
- Reject private CLI session state as workflow recovery truth.
- Reject agent-written pipeline files as canonical orchestration state.
- Reject mutable execution rows as replacements for History.
- Reject Docker/process health as proof of semantic execution state.
- Reject fleet scheduling, placement, or autoscaling inside `Engine`.
- Reject a mandatory Docker/Redis control plane for local Petrus use.
- Reject making Arx responsible for lifecycle mutation.
- Reject copying Trinity feature breadth before one concrete Petrus operator
  journey identifies the smallest valuable slice.

## Product and strategy implications

### Position Petrus below and across agent platforms, not as another one

Competing with Trinity feature-for-feature would move Petrus away from its most
defensible idea and into a mature, integration-heavy product category. Petrus
should position itself as the semantic execution substrate that agent platforms
do not provide:

- durable process identity beyond one agent/container/session;
- explicit, inspectable, concurrent process structure;
- deterministic replay and simulation;
- provider-neutral Activities with replaceable custody; and
- equal support for agents, deterministic code, humans, and external events.

Trinity's own “not a DAG engine” invariant makes that positioning concrete.
**[I]**

### A combined architecture is plausible, but not yet recommended work

A future product could compose the strengths without merging authority:

```text
┌──────────────────────────────────────────────────────────────┐
│ Optional Petrus host/control plane                           │
│ admission · inventory · environments · governance · APIs    │
│                         Trinity is strong prior art here      │
└─────────────────────────────┬────────────────────────────────┘
                              │ hosts many
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Petrus Engines / Instances                                   │
│ Petri semantics · canonical History · replay · lifecycle     │
│                         Petrus remains authoritative here     │
└─────────────────────────────┬────────────────────────────────┘
                              │ dispatches Activities
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Workers / Agenticus environments / provider runtimes         │
│ leases · isolated custody · CLI agents · result evidence     │
│                         both projects provide useful patterns │
└──────────────────────────────────────────────────────────────┘

Arx observes and joins all three planes with provenance; it owns none.
```

Trinity itself could theoretically host agents that submit work to a Petrus
application, or a Petrus Activity could borrow a Trinity-managed agent
environment. Either direction would require explicit Instance, Activity,
execution, session, and terminal-correlation identities. It is not a current
recommendation because there is no demonstrated user journey that needs this
integration. **[I/P]**

### If a follow-up exploration is commissioned

Do not ask “which Trinity features should Petrus clone?” Ask:

> What is the smallest operator journey that current Petrus owners cannot
> complete through existing host composition and read-only Arx protocols?

A useful first bounded journey might be: list hosted Instances, show each exact
History position and status, join active Dispatch Attempts and provider/Worker
facts with staleness, distinguish reported from accepted terminals, and repair
the view after a cursor gap. That would test the optional operations-plane seam
without commissioning infrastructure placement, mutation, or autoscaling.
**[P]**

The trigger already exists in DEC-038: return when a concrete operator product
requires a durable event stream rather than owner snapshots. Trinity is evidence
for what such a product eventually needs, not evidence that Petrus has reached
that trigger. **[I]**

## Disposition

1. **Retain Petrus's process-centered ontology and canonical History.** Trinity
   reinforces rather than weakens this differentiation.
2. **Do not adopt Trinity wholesale or create a current roadmap story.** The
   category mismatch would push fleet concerns into settled semantic owners.
3. **Use Trinity as named prior art** when a concrete host/operations or
   Agenticus environment story is planned.
4. **Keep Arx read-only** and let it learn from Trinity's operator information
   design rather than its mutation APIs.
5. **Revisit only on evidence:** a real multi-Engine host deployment, a concrete
   operator journey, or a runtime profile whose qualification needs an isolated
   environment lifecycle.

This completes the requested comparison without changing runtime code,
roadmap commitment, decision state, or support claims.
