# Product Principles

What Petrus preserves when trade-offs appear. Petrus is the project over the
settled Impetus, Motus, and Arx components and the one `petrus` Python
distribution and namespace. Impetus and Motus retain their conceptual
ownership through `petrus.impetus` and `petrus.motus` subpackages. These
principles are grounded in the decision corpus; supersede deliberately, don't
erode.

## Principles

### The net is the durable thing, not the agent

Everyone else centers the agent and its state. In Impetus the durable truth is the net instance — event History + marking — and agents live within it as handler flavors. Any feature that makes an agent's private state authoritative over History is moving backwards.

### One history, no hidden loops

Every firing — passthrough or side-effecting — belongs to one per-instance, append-only event history. If a behavior cannot be explained from the history, the design is wrong, not just the code. Context is a view over history: rebuildable, reprocessable, forkable. No component may own a loop whose state can't be reconstructed from the log.

### Append-only and uncompacted, forever

Corrections are new events. Compaction never touches the canonical log — projections, snapshots, and summaries are derived, disposable, rebuildable. Retention/archival is an operational concern, distinct from semantic compaction. Future tools (process mining, forking, meta-workflows) depend on records we refuse to destroy today.

### Record facts, even inconvenient ones

External events are recorded as history facts whether or not any transition consumes them — production taught us that silently dropped webhooks become ledger compensation later. Side effects are observed facts in history, never recomputed during replay. Interrupted work is terminalized explicitly; proven-closed ingress and late terminals are dispositioned durably rather than silently lost or retargeted. Nothing dangles.

### Capture before meaning

At a source boundary, preserve what the source said durably and with provenance before interpretation assigns meaning. Raw source content is untrusted data, not instructions. Infrastructure-owned cursors define processing progress; at-least-once overlap is made safe through idempotence. Coverage gaps remain explicit and repair closes only when missing evidence actually arrives—not when a request succeeds or a time span merely claims completeness. Source archives may remain territory outside an Instance's canonical History; downstream interpretation Nets consume them independently and replayably.

### Handlers are code; the seam is sacred

Transitions decouple from side-effect implementations through named symbols and bindings — a seam already proven on a durable execution substrate and retained by Petrus for any substrate. Filters and guards are pure (inline CEL for the trivial, a named symbol of ordinary reusable code for the rest). Server-side handlers bridge Petri semantics to Petri-agnostic activities; activities contain the imperative side effects workers execute. Ingress adapters touch external transports and source transitions locally project their identified deliveries. The outside world affects the net only after becoming recorded tokens. We never force users to bypass our design to get real work done — the named-symbol escape hatch means there is no DSL ceiling.

### Anything is allowed, then shape down

Defaults are permissive: untyped places hold any token, arcs left untyped after place-color resolution admit anything, and flow just flows through the default passthrough handler. A place may declare its ordinary token domain once; flattening compiles that color onto otherwise-untyped incident arcs. Explicit arc colors still narrow heterogeneous places. Types, filters, weights, and guards shape flow but are never declaration duties. Correctness is enforced by the instantiation-time validation run, not a static type ceremony. Impetus is not a pure-Petri-net environment; it is Petri-net infrastructure for a runtime, and it does not presume what people will do with it.

### Progressive disclosure, not semantic reduction

The common path should make one readable flow file enough to compile, inspect,
validate, and put a process into first motion. Application clients, agent
machinery, credentials, persistence, and placement compose behind or beside
that flow instead of overwhelming it. Convenience is a frontend over the same
canonical Net, History, Activity, and authority model—not a second runtime or
an implicit call-stack workflow. Every generated topology remains inspectable,
and advanced authors may descend deliberately to the lower-level Petrus APIs
without losing validation or replay. Lower cognitive cost before lowering
capability.

### Useful with zero agents

The runtime must remain fully valuable running only deterministic code and humans. Nothing in the core may assume a transition is agentic. Agents are for judgment; deterministic work is code.

### Local-first, distribution-ready

One machine runs the full model — same semantics, same history, same workers. Distribution scales the same model by routing execution across a grid; it never switches to a different model. No required infrastructure that makes local operation second-class.

### Authority is local; coordination is addressed

Every net instance owns its canonical history, marking, and writer authority.
Independent instances communicate through authenticated, identified source
delivery and activity effects—not shared memory, direct marking mutation, or a
global semantic history. Routing, discovery, inboxes, and receipts are protocol
state around the sacred ingress/activity seams. Process identity survives its
current worker, runner, provider session, and execution location.

### Compose, don't own

Impetus and Motus compose into a runtime, never a framework that owns the host's lifecycle. Arx connects to that runtime without becoming its lifecycle owner or canonical state. All three Petrus components retain distinct conceptual responsibilities even when an application integrates them. Where durability guarantees are needed, the store — not the process — is the unit of ownership we reach for first.

### Arx follows current Petrus

Arx exists to lower the human cognitive cost of designing, understanding,
simulating, observing, debugging, and adapting current Petrus systems. Current
Petrus contracts and component ownership govern its models. Arx may join semantic, operational, provider, and application views into
one navigable experience, but it preserves their provenance and never turns
presentation into authority. Build one demonstrated cognitive improvement at a
time without shrinking the companion vision permanently to visualization or
live watching.

## Questions to Answer

Still genuinely open:

- **Writer enforcement across future profiles**: PostgreSQL and SQLite Engine
  constructions now prove store/filesystem-backed fencing for their supported
  profiles, while in-memory and JSONL retain narrower single-owner assumptions.
  A future multi-host History Store must earn its own store-level fence rather
  than reopening whether the library form can enforce ownership at all.
