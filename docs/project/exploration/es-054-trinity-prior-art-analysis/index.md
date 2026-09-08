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

# 1 Trinity prior art

## 1a Conclusion

Trinity operates agent fleets. Petrus owns durable processes in which agents
may participate. The completed comparison identified useful host and Agenticus
operations patterns, with no adoption, integration, support expansion, or
roadmap promotion.

Revisit this source when a concrete multi-Engine host, operator journey, or
runtime qualification needs it. Existing Petrus ownership remains authoritative:
[architecture](../../../../spec/OVERVIEW.md),
[product principles](../../../product/principles.md), and
[current Agenticus support](../../../runtime-guide.md#2-agenticus-support-matrix).

## 1b Historical baseline

The comparison inspected [Trinity v0.8.5 at `499cac0`](https://github.com/Abilityai/trinity/tree/499cac04a1bd3c4a9cca074a198387e03140eb56)
and Petrus at `9f0191ea7c8c96555f1b4aa5221af159cccf44a2` on 2026-08-15.
It used code, tests, schemas, deployment files, and architecture records.
`[D]` below means inspected source, `[I]` an inference, and `[P]` a proposed
Petrus application. The comparison did not deploy Trinity or qualify its
operational claims. Current releases may differ from this pinned baseline.

## 1c What the source established

| Concern | Trinity evidence at the pinned revision | Petrus implication |
| --- | --- | --- |
| Process meaning | [`CLAUDE.md`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/CLAUDE.md#L159-L160) leaves pipeline progression to agent-side skills and files. `[D]` | Preserve Net Instance and History as durable process authority. Agent files and session resume cannot replace semantic replay. `[I]` |
| Fleet lifecycle | [Docker service](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/docker_service.py) and [Compose](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docker-compose.yml) own environments, volumes, setup, health, and process controls. `[D]` | An optional host/provider layer may own this work above Engines. Dispatch remains custody; it does not become fleet provisioning. `[P]` |
| Runtime adapters | [`AgentRuntime`](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docker/base-image/agent_server/services/runtime_adapter.py) declares capabilities, interactive/headless behavior, readiness, sessions, transcripts, and costs. `[D]` | Qualify each Agenticus profile's provenance, result persistence, credentials, timeout, process cleanup, and environment-loss behavior separately. `[P]` |
| Admission and backlog | [Capacity manager](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/capacity_manager.py) uses Redis slots and limits; [backlog](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/backlog_service.py) uses SQL overflow, breakers, and repair. `[D]` | Global admission and fairness belong to a many-Engine host. Copying the state topology requires its reconciliation costs too. `[I]` |
| Terminal races | [Execution service](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/task_execution_service.py#L1750-L1786) uses CAS before capacity release and follow-on effects. `[D]` | Preserve idempotent operational settlement while keeping Instance-side canonical acceptance distinct. `[I]` |
| Operator records | [Execution schema](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/db/schema.py#L231-L278) combines status, cost, transcript, retry, lease, and session in mutable rows. `[D]` | Useful read-model ideas; rows, Docker state, Redis, and session files do not form one replayable process History. `[I]` |
| Reconnect | [Event bus](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/event_bus.py) has bounded Redis retention, cursors, per-client queues, and resynchronization gaps. `[D]` | Join operational views with provenance and explicit gaps. Presentation delivery remains separate from correctness-critical History. `[P]` |
| Governance | [Audit service](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/src/backend/services/platform_audit_service.py#L58-L150) provides platform audit, optional hash chains, filters, and retention. `[D]` | Audit is separate governance evidence. Writes are best-effort and hash chaining is off by default; neither proves canonical durability. `[I]` |

Trinity supplied a broader operator product at that revision: authentication,
roles, credential injection, schedules, webhooks/chat, fleet views, intervention,
logs, cost, deployment, and recovery documentation. Petrus's pre-release library
had a narrower supported Agenticus route. That product difference matters,
but no feature count decides semantic correctness. `[D/I]`

## 1d Limits that affect reuse

1. Trinity's reconnect stream can trim or drop messages and requires explicit
   resynchronization; shutdown and Redis loss have bounded fallback behavior.
2. Its [security requirements](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/memory/requirements/security.md#L313-L416)
   record incomplete credential isolation and network egress control. Docker,
   rather than model compliance, is the containment boundary. `[D]`
3. Pull/work-stealing and retry-with-prior-trace were continuing work in the
   [target architecture](https://github.com/Abilityai/trinity/blob/499cac04a1bd3c4a9cca074a198387e03140eb56/docs/planning/TARGET_ARCHITECTURE.md).
   Selected sink guards existed, but a model's reading of a prior trace does
   not establish that an external effect can safely repeat. `[D/I]`
4. Runtime health, Activity outcome, provider report, and canonical terminal
   acceptance are separate facts. A platform status row must not collapse them.
5. Arx may display joined projections. Its retained boundary toward live
   Petrus systems is read-only; optional host command APIs remain another owner.

## 1e Reuse and next decision

The proposed operator experiment is small: list hosted Instances, show exact
History position and status, join Dispatch/Worker facts with provenance and
staleness, distinguish reported and accepted terminals, and recover the view
after a cursor gap. `[P]` A concrete consumer must request that experiment
before it becomes work.

[DEC-038](../../decisions/records/2026-07-22T1930Z-dispatch-snapshots-heartbeat-details-observation-remains-optional.md)
sets the more specific stream trigger: a concrete operator product must need a
durable event stream beyond the available owner snapshots.

A future Agenticus profile can use the source as a qualification checklist:
exact installation identity, least-capable defaults, readiness, session limits,
credential and tool boundaries, result/transcript/cost evidence, process-tree
cleanup, terminal persistence before reply, and retained-environment recovery.
These are comparison recommendations, not newly supported capabilities.

The completed inquiry requires no new decision record. Keep fleet scheduling,
placement, autoscaling, mandatory Docker/Redis, and agent-owned process truth
out of the semantic runtime. Any Trinity integration needs a separately scoped
journey and explicit Instance/Activity/execution/session correlation.
