# 1 Product principles

These principles guide Petrus design choices. Impetus owns net semantics and
History; Motus owns Activity execution; Arx owns human-facing editing and
inspection. Consequential changes to these constraints belong in the
[decision records](../project/decisions/index.md).

## 1a The net instance owns durable state

A net instance's History and marking are authoritative. Agents participate
through handlers and Activities; their private state cannot override History.
The runtime must remain useful for deterministic code and human work without
any agents. Use agents for judgment and code for deterministic operations.

## 1b Make execution explainable from History

Every firing belongs to one per-instance, append-only History. Context,
snapshots, and summaries are rebuildable views of recorded facts. A component's
execution loop must not hide state needed to reconstruct the process. Derived
context can be reprocessed and forked while canonical History remains linear.

Corrections append new events. Canonical History remains uncompacted;
projections and summaries may be replaced. Operational retention and archival
are separate from semantic compaction. Future inspection, process mining,
and forking depend on preserving the original facts.

## 1c Record external facts and their disposition

Record external events even when no transition consumes them. Preserve
observed Activity results so replay does not repeat effects to discover their
outcomes. Terminalize interrupted work explicitly, and record the disposition
of proven-closed ingress and late terminal reports.

At a source boundary, capture source content durably with provenance before
interpreting it. Treat raw content as untrusted data. Infrastructure-owned
cursors track progress; idempotence makes overlapping delivery safe. Keep
coverage gaps explicit until the missing evidence arrives. A successful fetch
or a declared time span alone does not prove completeness. Source archives may
live outside canonical History and feed independent interpretation Nets.

## 1d Keep handlers and Activities composable

Transitions bind to implementations through named symbols. Filters and guards
are pure; they may use inline CEL or named reusable code. Handlers bridge
Petri-net bindings to Petri-agnostic Activities, which perform external effects.
Ingress adapters receive external data, and source transitions project their
identified deliveries into tokens.

Named implementations keep ordinary code available when the authoring syntax
cannot express a domain operation. The host supplies implementations without
putting execution infrastructure into the net's semantic model.

## 1e Start with permissive flow

Untyped places accept any token. Arcs without a color after place-color
resolution also accept any token, and the default passthrough handler routes
flow. A place can declare a token domain; flattening applies that color to
otherwise-untyped incident arcs. Explicit arc colors can narrow heterogeneous
places. Types, filters, weights, and guards constrain flow when needed.
Instantiation-time validation enforces correctness.

## 1f Make the common path approachable

One readable flow file should be enough to compile, inspect, validate, and
reach first motion. Clients, credentials, persistence, placement, and agent
machinery compose around the flow. Convenience must preserve the canonical
Net, History, Activity, and authority model. Generated topology stays
inspectable, and authors can use lower-level APIs without losing validation
or replay. This is a design goal; the roadmap records what remains to deliver.

## 1g Preserve local operation and explicit authority

A single machine runs the same semantics, History, and Worker model used by a
distributed host. Distribution routes execution without changing that model
or making local operation depend on remote infrastructure.

Each instance owns its marking, writer authority, and canonical History.
Independent instances communicate through authenticated, identified source
delivery and Activity effects. Routing, discovery, inboxes, and receipts are
protocol state; they cannot mutate another instance's marking or create a
global semantic History. Process identity survives its current Worker, runner,
provider session, and execution location. Fabric's unfinished prototype does
not establish a general support claim for this design.

## 1h Let applications own their lifecycle

Impetus and Motus compose into a library runtime. Applications own the hosting
lifecycle; Arx connects without becoming the canonical state or lifecycle
owner. Each component retains its responsibilities when integrated. Durable
ownership is enforced at the store where the chosen profile supports it.

## 1i Arx follows current Petrus contracts

Arx helps people design, inspect, simulate, observe, debug, and adapt Petrus
systems. It can join semantic, operational, provider, and application views
while preserving their provenance. Presentation never grants execution or
History authority. Develop demonstrated improvements incrementally while
retaining the broader editor and debugger purpose.

## 1j Open design boundary

PostgreSQL and SQLite Engine profiles have store or filesystem writer fencing.
In-memory and JSONL profiles retain narrower single-owner assumptions. Any
future multi-host History Store must establish its own store-level fencing
and failure guarantees.
