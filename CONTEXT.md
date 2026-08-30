> Migrated from the Hermes design notebook. Current project ontology is
> governed by `docs/project/decisions/records/2026-07-29T2316Z-petrus-is-project-over-impetus-motus-and-arx.md`;
> evolve this glossary in place.

# Context

This document is the domain glossary for Petrus and its components. It should contain domain language only, not implementation plans or architectural decision rationale.

## Glossary

### Petrus

The public project and umbrella identity over Impetus, Motus, and Arx, anchored
at `petrus.run`. Petrus also names the one Python distribution, source root
`src/petrus`, and top-level namespace. A running Petrus system composes
Impetus's event History and Petri-net responsibilities with Motus's Activity
responsibilities. Petrus-level subsystems such as Agenticus may compose those
components without becoming another foundation. Arx may connect to that system
without becoming runtime state or collapsing the components' responsibilities.

### Impetus

The Petrus component and `petrus.impetus` subpackage for Binding, DSL, History,
History Store, Instance, Petrinet, and Selection. Public concepts live in their
defining ownership modules; `petrus.impetus` exports no concept facade.

### Motus

The Petrus component and `petrus.motus` subpackage for Activity, Dispatch,
Transport (including ZeroMQ), and Worker. It gets Activity work executed across
local or remote arrangements. `petrus.motus` exports no concept facade.

### Arx

The human-facing companion to current Petrus: an editor, inspector, debugger,
simulator, and navigable map of authored Nets, semantic History and state,
data movement, and operational embodiment. Arx reduces the cognitive load of
understanding and adapting complex Petrus systems. It follows current Petrus
without making presentation state canonical History or collapsing Arx into
Impetus or Motus, and may expose reusable views to Petrus-based applications.

### Agenticus

The optional Petrus-level `petrus.agenticus` composition subsystem for reusable
agent infrastructure: Agent Connection custody, Agent Programs, agent-work
lifetimes, runtime profiles, capability-scoped Hands, Episode Attachment,
effect fences, and host capability registration. Agenticus may depend on
Impetus and Motus; neither depends on it. It is not a fourth foundational
component, a universal Agent abstraction, or an owner of canonical History.

### Agent Connection

A host-installation-owned logical grant to one provider account/profile, with
an authority epoch and custody policy. Agenticus provides encrypted custody,
bounded materialization, refresh reconciliation, revoke, and erase mechanisms;
the host remains the principal. An Agent Connection is not a raw token, Agent
Home, runtime process, workspace, Thread, or provider session.

### Agent Program

The structure and policy that progresses agent work. A program may be owned by
an official provider runtime, an application harness, or an Impetus Net. These
forms are distinct profiles rather than implementations of one universal
Agent. A program is not its model, connection, live runtime, Thread, or Hands.

### Agent Runtime

One supervised live embodiment of an Agent Program under an explicit runtime
profile, selected Agent Connection, and attachment arrangement. It has an
incarnation rather than durable agent identity and does not imply that Brain
and Hands are collocated.

### Thread

The durable lineage of related agent work. It can outlive runtimes, Episodes,
and territories. It is not a workspace, Agent Home, provider process, provider
session, canonical Petrus History, or universal transcript format.

### Continuation

Provider- or program-specific state that allows compatible runtime work to
continue a Thread. Agenticus preserves explicit compatibility and opaque
custody where needed; it does not define one cross-provider Continuation
format.

### Episode

One bounded run of an Agent Program against a selected Continuation and Episode
Attachment. An Episode contains Turns and has explicit deadlines, cancellation,
fencing, settlement, and cleanup outcomes. It is not a provider session or a
Motus territory lease.

### Turn

One bounded progression step within an Episode: model/program input, zero or
more tool proposals, and an accepted append/result according to that program's
contract. Turn shape remains runtime-profile-specific where providers differ.

### Hands

The capability-scoped tool plane available to an Agent Program. Hands owns
versioned tools, grants, deadlines, cancellation, attachment epochs, staged
writes, fencing, transition, and cleanup evidence. It may operate through a
Motus territory but does not own that territory's provider lifecycle.

### Episode Attachment

The Agenticus composition that binds one Episode's Hands and capability epoch
to a narrower Motus territory attachment. It does not collapse Agent Home,
Thread, workspace, provider session, or territory into one Session concept.

### Effect Proposal

A provider-neutral request for the host's effect boundary to perform an
externally consequential action under explicit authority and target-head
fences. Agenticus can define proposal and recovery contracts; the host owns
business policy and provider-specific Effect Gateways.

### Impetus Kernel

The compatibility-era name for the semantic center, now formally **Petrinet
Kernel**. Use Petrinet Kernel where the concept boundary matters.

### Petrinet Kernel

The semantic center exposed at `petrus.impetus.petrinet`: `Net`, tokens and
markings, enabledness, timer-maturation
calculation, and pure token routing. Record-carrying firing lifecycle remains
temporarily Instance-owned, and replay is History-owned. Candidate Selection,
activities, bindings, History and History Store, PostgreSQL, dispatch, workers,
process addresses, hosts, and sessions are outside it. `Engine` is the running
provider-neutral composition around exactly one durable Instance.

### Library, not framework

A design constraint: Impetus and Motus should provide composable primitives and optional high-level entry points, but should not own the host application's lifecycle. Users should be able to assemble, replace, or bypass the default layers. Arx connects as tooling rather than owning that lifecycle.

### Petri-net core

The lowest-level coordination engine responsible for Petri-net semantics such as places, transitions, arcs, colored tokens, markings, enabledness, firing, deterministic token movement, and replayable state evolution.

### Net definition

A declarative description of process topology and coordination semantics. A net definition contains places, transitions, arcs, token/color types, guards, subnet boundaries, and transition contracts. It does not contain concrete external behavior such as GitHub clients, Slack clients, LLM calls, browser automation, worker queues, or deployment choices. The Impetus Kernel requires an explicit net definition; handlers bind to transitions in the net rather than deriving the net from handler order.

### Petrinet Instance

The formal durable execution of a `Net`: concrete tokens, current marking,
timers, activity lifecycle facts, and one canonical semantic history. The
public name is `petrus.impetus.instance.Instance`; no project or component root
provides a concept alias. Each Instance is isolated, has one
history writer, and coordinates with other Instances by identified messaging
rather than shared marking or shared semantic history.

### Net instance

Compatibility-era wording for Petrinet Instance. Prefer **Instance** in new
public APIs and **Petrinet Instance** when naming the formal concept.

### Engine

The live composition that creates or resumes and drives exactly one Instance:
one canonical History Store, Dispatch, writer fence and transaction fate when
required, clock, Candidate Selection, and advancement lane. Several Engines
host distinct Instances and Histories; Fabric connects those Instances rather
than sharing their state. The writer fence prevents accidental duplicate live
hosts for one Instance. It is not a fleet, a multi-Instance supervisor, or a
public Authority concept. Providers may supply stronger construction,
notification, and transaction guarantees without renaming or subclassing the
complete Engine concept.

One `Engine.advance()` turn applies at most one normal whole Action after
finite first-load reconciliation, then returns control to its host.
`DriveOutcome.ready` asks the host to re-drive immediately after an applied
Action (the conservative re-drive may discover quiescence), `waiting` means
conservative policy is holding for an outstanding Activity, and
`next_maturation` is the earliest timer deadline. Waiting and timer scheduling
are host-owned; Engine advancement does not sleep. Direct `Engine.deliver()`
is the universal fast canonical ingress door and may accept a small identified
envelope whose resulting net state dispatches a later fetch Activity.

### Application surface host

An optional outer composition layer that supplies HTTP, SSE, CLI, browser,
authentication, projection, and attach surfaces around one or more Instances.
It is distinct from both Instance coordination and Fabric.

### Process address

The stable identity of one independently authoritative net instance as a
communication endpoint. It never names the instance's current worker, runner,
orb, provider session, or execution location.

### Fabric

The inter-Instance protocol plane for transport-neutral envelopes and reply
routes, discovery, exposed-source grants, durable inboxes and receipts, retry,
and correlation. Fabric state is routing and protocol truth, not a global
semantic history. Inbound messages enter recipient semantics only through
identified source delivery; outbound messages leave through activities.

### Delivery receipt

The Fabric fact that one stable delivery identity was accepted by a
recipient's canonical ingress occurrence. It does not mean the recipient
understood the message, completed the requested process, or performed an
external effect; those are separate causal facts.

### Process call

A scoped delegated-work lifecycle over Fabric in which an existing
addressed process receives a request and returns one correlated result or
error. The caller's net owns its wait and decides what the reply means. A call
does not create or imply ownership of an independently durable child process.

### Process spawn

A lifecycle that claims one independently durable child identity and
authorized process address from a stable parent-scoped spawn identity. Spawn
records lineage but does not start or drive a child Instance; the child's own
canonical history and status begin when its host opens it. Spawn and call
share Fabric but are not one API or lifecycle.

### Node

A place or transition in the Petri-net graph. Arcs, guards, handlers, timers, and initial markings are not nodes.

### Place

A location that holds colored tokens in a Petri net. A place may declare one nominal color as its token-domain authoring default; an untyped place holds tokens of any color. Flattening resolves a declared place color onto otherwise-untyped incident arcs once, preserving arc-only enabledness and routing at runtime. Explicit arc colors still narrow heterogeneous untyped places. A place may carry an optional non-semantic role annotation (`input`, `output`, `control`, `regular`) for tooling/readers; roles do not affect firing semantics.

### Place role

An optional annotation on a place. The working roles are `input` for externally fed or boundary-start places, `output` for emitted-result or boundary-output places, `control` for coordination/gates/joins/limits/retries/leases/scheduling state, and `regular` for ordinary domain-data places. If omitted, a place is treated as `regular` for display/tooling purposes. Place roles do not change Petri-net enabledness or firing semantics.

### Arc

A directed connection between two node paths using `from` and `to` endpoints. An arc must connect either place → transition or transition → place. Place → transition arcs are input arcs and may have consume/read/inhibit modes. Transition → place arcs are output arcs and describe produced tokens. In the flattened net, arcs are first-class graph citizens addressed with a typed URI using a `from->to` shape, such as `arc:/review/pending->/review/start`. Multiple arcs between the same endpoints are allowed; when endpoint identity is ambiguous, the arc URI uses an optional or generated fragment, such as `arc:/review/pending->/review/start#claim-review` or `arc:/review/pending->/review/start#$0`.

### Arc inscription

The typed expression on an arc that describes token color/type and cardinality, plus an optional arc filter. An authored arc without a color receives its incident place's declared color during flattening; if neither declares one, it remains unrestricted. Arc inscriptions should stay simple; they do not bind handler argument names. Cross-token conditions and correlation logic belong in transition guards, not in a single arc's filter.

### Arc filter

An optional pure, single-token boolean on an input arc that selects which tokens of the declared color the arc admits. A filter sees exactly one token — which may be an aggregate token type carrying nested data — and is written as an inline CEL expression or a named pure symbol. Filters, like weight, apply to every input arc mode: on a consume or read arc a filter narrows which token is selected; on an inhibitor arc it gates on the absence of a matching token. A filter never transforms token data and never spans tokens; multi-token correlation lives in a guard.

### Output inscription

The inscription on an output arc: a routing contract naming the token color/type the arc admits into its target place. It is not a token factory — the transition's handler supplies the actual output tokens, keyed by destination, and the runtime deposits only handler tokens whose color and destination match an output arc. Different output arcs may therefore carry different payloads from one firing (heterogeneous fan-out). When a transition has no handler, it is default-bound to the pure `passthrough` handler, which forwards each consumed token through every admitting output arc (arcs left untyped after place-color resolution admit anything).

### Arc mode

The way an input arc participates in transition enablement and firing. Arc mode applies only to arcs from place → transition. Impetus currently recognizes consume arcs, read arcs, and inhibitor arcs.

### Consume arc

An input arc that requires matching token(s) and consumes them when the transition fires.

### Read arc

An input arc that requires matching token(s) for enablement and token/firing binding, but does not consume them.

### Inhibitor arc

An input arc that requires the absence of matching token(s) for a transition to be enabled.

### Transition

A process step in a Petri net that may fire when enabled. Transitions are the only things that fire. A transition has no intrinsic implementation kind at the net level. Terms such as agent, human, polling, webhook, or activity describe bindings or handlers, not transition types.

### Initiation

A derived transition facet determined by its marking/source relationship, not
a declared transition kind. Source initiation occurs through identified
delivery; marking initiation occurs through an enabled binding.

### Completion

A derived transition facet: **Direct** when completion is a local deterministic
projection, or **Activity** when it crosses the Petri-agnostic activity seam.

### Direct

The canonical name for completion without an activity. “Pure” may still
describe a callable property, but it is not the completion-facet name.

### Transition timer

A time-based enablement constraint declared on a transition. A transition timer may delay enablement by a duration or delay enablement until a specific time. Timer semantics are declared in the net definition and observed by the driving runtime. Places do not have time-related behavior. A timer is evaluated per firing binding: a duration timer matures a binding measured from the youngest recorded entry instant among the binding's bound tokens; an absolute timer matures at its declared instant. Timer state is derived from the marking and recorded History, never stored. Timer maturation is a recorded event; maturation enables a binding, while Candidate Selection and whole-action DrivingPolicy decide whether it begins.

### Clock watermark

The per-Instance virtual clock: the driver-assigned, monotonically non-decreasing instant of the latest appended History record. "Now" for enablement — live and during replay — is the clock watermark; semantic time advances only when records are appended, and the net runtime never reads a wall clock. Real clocks, durable wakeups, and record timestamping belong to the driving runtime.

### Colored token

A token carrying typed data. Colored tokens unify process control flow and data flow. A token has exactly one token color; that color may be an aggregate token type.

### Token color

The type or schema associated with a colored token.

### Aggregate token type

A token color whose data structurally contains other typed fields — for example a `PaymentOrder` color that holds an invoice, a payment, and source/destination accounts. A token still has exactly one type; an aggregate is that single type, not a bag of several. Filters and guards read an aggregate's nested fields directly, with no runtime type inspection. Splitting an aggregate back into its typed fields is `unpack`, a pure stdlib shaping handler (structural projection). Assembling several inputs *into* an aggregate is construction, a user or reusable-component handler's job — there is deliberately no stdlib `pack` (it would be a hidden expression language and would couple the net to type construction).

### Marking

The first-class state of a net instance: the distribution of colored tokens across places. The marking is the time-blind view of the token queues; equal tokens are indistinguishable in it (tokens are values — no identity, no provenance).

### Token queue

The tokens at one place, in FIFO order, each paired with its entry instant. NOT a set: duplicates are legal and order is significant. Owns front-most-equal-occurrence removal (a consume removes the earliest token equal to the requested one) and positional reads. The marking is its time-blind view; the entry instants are its time view — one structure, two projections.

### Entry instant

The recorded instant a token entered its place — the instant of the movement record that deposited it. The anchor a duration timer matures from. Derived from movement records, never stored independently.

### Net path

A first-class static address object for a place or transition node inside a hierarchical net definition. A net path describes the node's position in the composed Petri net. Places and transitions share the same node namespace within each parent scope, so a net path identifies exactly one node without requiring a separate node-kind discriminator. `NetPath` is the node-address subset of `NetUri`: every net path can be represented as a net URI, but not every net URI is a net path. Internally, resolved net paths should be absolute, though authoring APIs may support relative net path references that resolve against a root path or net context.

### Relative net path

An authoring-time reference to a place or transition node that must be resolved against a root path or net context into an absolute net path during validation or compilation.

### Schema reference

Deprecated working term. Prefer **Net URI** for the broader address of any addressable schema element.

### Net URI

A fully qualified address for any addressable part of the composed net. `NetPath` is the subset of `NetUri` that addresses place and transition nodes. Impetus uses typed URI schemes as the working canonical syntax for graph citizens, such as `place:/review/pending`, `transition:/review/start`, and `arc:/review/pending->/review/start`. Parallel same-endpoint arc occurrences receive deterministic pair-local fragments (`#$0`, `#$1`); their filter declarations use declaration-kind-first fragments (`#filter:$0`, `#filter:$1`), while a unique arc's filter uses `#filter`. Broader net URIs may address declarations anchored on their owning graph citizen with fragment syntax, such as `transition:/review/start#handler` or `place:/review/pending#initial`. In the composed/flattened net, every declaration has a canonical `NetUri`, even if it was anonymous or minimally named at authoring time.

### Declaration

An addressable schema element attached to a net or graph citizen, but not itself a node. Examples include handler declarations, guard declarations, arc-filter declarations, timer declarations, and initial marking declarations. Authoring APIs may allow anonymous declarations, but the composed/flattened net assigns every declaration a deterministic canonical `NetUri`.

### Flattened net

An internal representation where nested nets or subnets are compiled into a flat set of addressed places, transitions, arcs, and declarations for efficient execution and lookup. The flattened net should expose dictionaries or indexes of uniquely identifiable parts, such as a node dictionary keyed by `NetPath` and a declaration dictionary keyed by `NetUri`.

### Enabledness

The condition under which a transition is eligible to fire, based on the current marking, arcs, guards, token availability, and time semantics.

### Admitted

A token passing an input arc's admission test: the inscription's color (nominal match) narrowed by the arc's optional filter.

### Selection

The tokens one arc takes from one place for a firing binding — a `(place, tokens)` pair, tokens in FIFO-scan order of admitted positions.

### Head selection

The first `weight` admitted tokens of a queue, scanned front-to-back: always the first alternative that candidate enumeration considers.

### Offer

An input arc's whole answer to a marking, one of three outcomes: **Veto** (an inhibitor found its matching tokens, or a consume/read arc fell under weight — the transition is gated out), **Satisfied** (an inhibitor is clear; the arc contributes nothing), or **Alternatives** (every admitted combination of selections, with their timer anchors). A transition's candidates are the cross product of its arcs' offers, then guards, then timers — the enabledness conditions in linear form.

### Guard symbol

A scoped name declared in the net schema to identify a guard required by a transition. The symbol must resolve to a fully qualified schema reference and be mapped to a concrete guard function before the process can run.

### Guard

A pure boolean function, mapped to a schema-declared guard symbol or written as an inline CEL expression, that participates in transition enabledness. A guard is transition-level: it sees the full firing binding across all input arcs and is where cross-token correlation and joins live, since a single-arc filter cannot span tokens. Like a filter, a guard is pure — it reads the selected tokens and returns true or false with no side effects and no external calls. Process side effects live in handlers; external state a guard needs is brought into the marking by recorded projection.

### Handler symbol

A scoped name declared in the net schema to identify the handler expected by a transition. The symbol must resolve to a fully qualified schema reference and be mapped to a concrete handler implementation before the process can run. If a transition declares no handler symbol, the binding layer default-binds it to the library's pure `passthrough` handler — a default binding, not an engine special case.

### Implementation mapping

The binding-layer mapping from schema-declared guard and handler symbols to concrete guard and handler functions. Multiple symbols may map to the same reusable function implementation.

### Firing

The occurrence of an enabled transition. A firing consumes or reads input tokens according to arc modes and produces output tokens from deterministic handler projection, including projection of a completed activity result for impure work. Every transition firing is semantically part of its Instance's one History, including passthrough, deterministic/internal, handled, side-effecting, and Worker-routed transitions.

### Firing occurrence

One durable semantic begin→terminal lifecycle for a firing Binding — the net's reservation and the correlation identity pairing its records in interleaved History. A firing occurrence may remain open while no code is currently running. It is not an operational retry: an impure occurrence produces one stable Activity invocation, which Dispatch may try through several operational Attempts. The reference API spells this value `FiringOccurrence`, and every record of one firing correlates by its `occurrence` field — shipped by the CV3 schema-2 migration.

### Firing outcome

The terminal semantic result of a completed firing occurrence. The reference API spells the successful value `FiringOutcome` (since the CV3 schema-2 migration); failed occurrences end through `FiringFailed`. Richer suspension, abandonment, and audited manual resolution remain later refinements.

### Firing binding

A concrete assignment of variables that satisfies all input arc inscriptions and guards for a transition. A transition may be enabled under many firing bindings at once.

### Enabled firing candidate

A transition plus firing binding that is valid under the current marking but has not necessarily been selected to begin firing.

### Scheduler

Temporary implementation vocabulary for the Planned Candidate Selection boundary.
Candidate Selection's ruled target is outside Petrinet Kernel and composed by
one Engine per Instance. Within the `BeginCandidate` action class it admits,
ranks, and chooses at most one existing Binding. The Planned initial policies
are First, Priority, and transition-level Round-Robin; the base contract
promises no universal fairness grain. State is an immutable proposal installed
only after begin commits and reconstructed from existing selections with
matching committed begin facts. The current `DrivingPolicy` retains
whole-action semantics: it chooses one complete safe action from the available
action surface. `Scheduler` remains only until Candidate Selection supplies its
replacement; DEC-040 assigns it no compatibility window.

### Selected firing occurrence

An enabled firing Binding chosen by Candidate Selection, accepted through the
whole-action policy, and recorded as a durable firing occurrence. Existing
selection and movement records explain the choice without a separate durable
Binding key.

### Batch

What a firing forwards by default: the binding's consumed selections flattened in input-arc order, or a source firing's delivered tokens. Read selections never join the batch.

### Peeked

Everything a binding holds — the batch plus its read selections. What guards evaluate over.

### Begin firing

The runtime step that starts a firing occurrence, records it durably, and consumes or accounts for input tokens according to the net semantics before delegating to the handler.

### End firing

The runtime step that ends a firing occurrence by atomically committing the token and delivery-registration effects projected from a completed activity result, or by recording explicit terminal failure semantics.

### Handler binding

A mapping from a handler symbol declared in a net definition to executable behavior. Handler bindings are outside the pure net definition.

### Activity binding

The cross-component reference from an Impetus-side impure handler to a concrete Motus Activity declaration, implementation version, and default execution configuration. The handler declaration address answers where the net requests behavior; the activity binding answers which Petri-agnostic implementation fulfills it. A broader URI family for activity and runtime bindings remains deferred.

### Activity definition

A typed, Petri-agnostic Activity implementation produced by `@activity`. It carries the callable's resolved named-parameter and return annotations, its `ActivityDeclaration`, and the payload converter used around operational execution. It consumes a canonical parameter-name mapping from `ActivityInvocation`, decodes typed Python arguments before calling the authored function, and encodes the return value back to a canonical Activity result. It does not know about nets, arcs, bindings, tokens, History, or Dispatch transport encoding.

### Payload converter

The structural operational seam that decodes one canonical Activity parameter value into the Python type named by its annotation and encodes the typed return value back into a detached JSON-faithful value. The default converter preserves canonical JSON values; the dataclass converter handles top-level dataclass construction and serialization with JSON fallback. Applications may supply narrower converters without changing Engine, Dispatch, Worker, or Instance. Provider wire encoding remains Dispatch-owned and is not this seam.

### Handler

A server-side callable implementation bound to a transition. A pure handler projects firing effects locally. An impure handler deterministically prepares one Petri-agnostic activity invocation from the immutable firing binding, then projects the frozen activity result into token and delivery-registration effects. An explicit Activity handler owns that Petri-aware contract directly; an ordinary handler may instead be derived from an Activity definition plus an unambiguous typed arc shape. Initially one impure handler maps to exactly one independently recoverable activity; durable sequences expand into transitions separated by intermediate places. Multi-activity handlers are considered but deferred.

### Derived Activity handler

The public Petri-aware `ActivityHandler` implementation that derives ordinary `prepare` and `project` behavior from a typed Activity definition and one transition's arc inscriptions. Each named Activity parameter must map one-to-one to a weight-one consume/read input arc by nominal type-name/color equality; the return type must match every output arc, with repeated matching arcs producing once per arc. Inhibitors may gate without becoming arguments. Missing, ambiguous, reused, weighted, or unmatched typed shapes are refused at composition rather than guessed. Explicit Activity handlers remain the escape hatch for joins and reshaping, business identities, conditional or multi-color routing, delivery-registration effects, and other semantics the net shape cannot derive.

### Default transition behavior

The behavior of a transition with no handler symbol declared: the binding layer default-binds it to the library's pure `passthrough` handler — a default binding, not an engine special case. Passthrough is color-routed forwarding: each consumed token is forwarded, unchanged, through every output arc that admits it (a typed output arc admits its color, an untyped output arc admits anything); a token admitted by N arcs is deposited into N places. Consumed tokens admitted by no output arc are simply consumed — allowed, not an error; read and inhibit selections contribute nothing. Passthrough never merges, splits, or retypes tokens. Any packing, unpacking, filtering, projection, or type transformation must be expressed with an explicit handler (a stdlib shaping handler such as `unpack`, or a user handler) outside the net schema.

### History

One Instance's canonical semantic timeline. Every transition firing contributes
to History, regardless of whether the transition is passthrough,
deterministic, handled, side-effecting, or routed to an external Worker.
History is append-only and uncompacted, like a tracing log; projections,
indexes, snapshots, summaries, and rollups may be derived from it but do not
replace it. Records serialize by the ratified public schema (one JSON object
per record, the record-type name as discriminator; a record's node field is
spelled by its role — place, transition, or source). Avoid *journal*, *firing
journal*, and storage/provider names as synonyms for History.

### History Store

The capability that preserves one Instance's History through the structural
`HistoryStore` append/read contract. Product profiles name failure and
transaction boundaries: **In-Memory History Store**, **Local History Store**,
and **Transactional History Store**. Current implementations are
`InMemoryHistoryStore`, `JsonlHistoryStore`, `SqliteHistoryStore`, and
`PostgresHistoryStore`. Memory, filesystem/JSONL, SQLite, and PostgreSQL are
implementation substrates, not product capability names. “Local Durable” is
not a profile: local crash, process, and power-loss boundaries must be stated
explicitly.

### History record

A semantic record that explains process evolution in History. The record
categories include external event delivered, timer matured, firing candidate
selected, firing begun, tokens consumed/read/accounted, Activity requested,
Activity completed/failed, firing completed, tokens produced,
delivery-registration effects, lifecycle-scope open/close/reset, scoped ingress
disposition, terminal quarantine, and firing failed. Queue scheduling, claims,
leases, heartbeats, and individual Activity Attempts are operational state,
not canonical History. Exact semantic queue-entry identity and scope provenance
do belong to History so duplicate-valued token occurrences can be replayed and
cleaned independently. Impetus does not split canonical History into
correctness versus observability categories; the same semantic timeline
supports correctness, replay, fork, audit, debugging, and observability.

### Lifecycle scope

The immutable durable identity `(name, generation)` that owns one explicit
generation of queued token occurrences and firing occurrences. A scope opens
canonically, closes with exact queued-occurrence cleanup and in-flight
cancellation, or resets atomically by closing N and opening N+1. Append order,
not record timestamps, resolves races. Generation does not replace firing
occurrence, invocation, correlation, idempotency, business ownership, or
provider authority identities. A scope value contains no credentials, clients,
closures, Activities, Engines, or mutable host capability.

### Lifecycle cancellation fence

The recoverable Dispatch instruction projected from an already committed
`ScopeClosed` or `ScopeReset` record for one exact Activity invocation. History
is the business truth and Dispatch custody is operational: no fence becomes
visible before canonical commit, and Engine load repairs missing fences before
republishing live outbox work. Pending custody may retire; claimed or running
custody is fenced against future accepted execution or terminal reporting.
The fence is not hard interruption and never proves an ambiguous external
effect did not occur. Local Dispatch can retain an exact report from an already
fenced claimant for canonical quarantine. Absurd treats a Worker report after
provider cancellation as stale and may eventually clean provider tombstones;
canonical repair can rematerialize absent cancelled custody, while stable
downstream idempotency, reconciliation lookup, and compensation remain the
application's responsibility. Inline and In-Memory Dispatch keep this
operational state only for their process lifetime.

### Scoped ingress disposition

The canonical answer when identified ingress cannot enter an active exact
lifecycle generation. A target proven closed is acknowledged and dropped. A
bare scope name or exact generation not provable from History is quarantined
and is never reinterpreted as the current generation. Exact redelivery is
acknowledged; reuse of the identity with conflicting content fails loudly.
Quarantine is a durable audit disposition, not a generic queue: Petrus does not
release or retarget it, and application reconciliation is explicit.

### Deterministic net/runtime record

A History record describing replayable Petri-net evolution, such as timer maturation, selected firing, firing begun/completed, token consumption/read/accounting, token production, and marking/state boundaries. These records allow state inspection and replay without re-running side effects.

### Activity record

A History record describing non-deterministic or externally executed work in process terms. The canonical lifecycle is `ActivityRequested` followed by `ActivityCompleted` or `ActivityFailed`. The request freezes the exact logical instruction before Dispatch; completion freezes the typed external result before deterministic handler projection. During replay, these records are observed facts rather than side effects to re-run. Enqueueing, claims, leases, heartbeats, retry scheduling, and individual Activity Attempts belong to operational Dispatch state and logs.

### Record taxonomy

Reader vocabulary for History's record kinds: **initiation** records mint a firing occurrence's id (candidate selected, external event delivered); **boundary** records open and close the occurrence (firing begun; the terminal completion or failure); **movement** records are tokens crossing the marking (consumed, read/accounted, produced, initialized); **activity** records request external work and freeze its completed/failed outcome; **effect** records are delivery-registration opens/closes. Serialized records correlate by the `occurrence` field (the CV3 schema-2 migration retired `attempt` from the wire); the activity family is the shipped spelling of category — `HandlerResultRecorded` is retired. Records name the world's event in past tense, never the ledger's own act.

### Worker operational log

An execution-layer log or trace for Worker and queue mechanics such as queue polling, lease/ack/nack, Worker startup/shutdown, sandbox/container details, stdout/stderr, resource usage, and delivery failures. Worker operational logs should correlate to canonical Activity/firing records but are not themselves canonical History.

### Typed handler

A handler whose input and output token types are declared by the handler implementation/contract. Typed handlers let users write ordinary typed code while the binding layer validates that transition arcs can supply the required token types.

### Generic token-set handler

A fallback handler style that receives the selected token set or context bag directly when precise typed input contracts are unavailable or intentionally avoided. The handler is then responsible for interpreting the token data.

### Simple handler

A small handler function intended to keep common data shaping or deterministic behavior easy to write while staying separate from the declarative net schema.

### Activity

The Motus unit of Petri-agnostic imperative work executed by a Worker for an impure handler. An Activity receives ordinary typed input and execution metadata, may perform external side effects, and returns a typed result or terminal execution failure. It never receives a live `Instance`, marking, History, topology, token selection, delivery registration, or output-arc contract. Initially one impure handler maps to exactly one Activity; multi-Activity handlers and a nested durable call stack are deferred.

### Activity invocation

The immutable logical instruction prepared by a server-side handler for one firing occurrence. It carries the activity binding reference, typed input, resolved execution policy, correlation identity, and provider idempotency identity—but no Petri-net token selection, queue, Worker placement, or topology. `ActivityRequested` records it before dispatch and acts as the authoritative outbox. Server-side occurrence history separately preserves the complete consumed/read binding snapshot for deterministic preparation and projection. Several operational activity attempts may execute the same invocation without creating another firing occurrence or idempotency identity.

### Activity attempt

One operational try by a Worker to execute an Activity invocation. Dispatch owns its identity, lease epoch, deadline, renewal, expiry, reassignment, checkpoint acceptance, and stale-epoch refusal. Long-running Activity code heartbeats the current epoch and may attach an operational recovery checkpoint. Claims, heartbeats, checkpoints, backoff, and attempt failures remain outside canonical History. Exhausting the frozen execution policy produces the canonical `ActivityFailed` terminal fact after Instance-side acceptance.

A Worker-facing Attempt may carry the durable Instance identity that authorized
the logical execution. That identity is execution scope, not Activity business
input: it lets shared Worker infrastructure select host-composed implementations
and lets operational terminals wake the owning Instance. It never carries an
Engine, marking, credentials, clients, callables, or mutable ambient context.

### Activity result

The typed, Petri-agnostic output returned by an activity. `ActivityCompleted` freezes it in canonical history before the server-side handler deterministically projects it into token and delivery-registration effects. A business refusal is a completed typed result. An exhausted operational failure is a classified `ActivityFailed`; a handler may explicitly project it through deterministic `project_failure`, while handlers without that opt-in retain `FiringFailed` and halt.

### Activity failure

A safe durable operational failure value carrying a bounded message,
provider-neutral kind, JSON-faithful details, retryability, and optional
retry-after guidance. Retryability classifies the failure independently of
whether the frozen execution policy permits another Attempt. Only terminal
failure enters canonical History; failed Attempts remain Dispatch state.

### Activity execution policy

The immutable policy frozen into one Activity invocation. It defaults to one
Attempt and may opt into bounded deterministic exponential backoff, a renewable
heartbeat timeout, per-Attempt start-to-close, and aggregate schedule-to-close.
The current deterministic policy accepts zero jitter only and bounds every
duration at 1,000,000,000 seconds for provider-neutral representability. A
provider must refuse deadline fields it cannot enforce soundly rather than
approximate them.

### Dispatch

The Motus capability that preserves operational Activity custody and reports
operational terminal outcomes to one Engine/Instance. The Engine-facing
`Dispatch` structural contract has exactly `dispatch` and `collect`; Worker
claim, heartbeat, lease, and report ergonomics are not part of that protocol.
Dispatch may own queue publication, claims, leases, Attempts, retry/backoff,
reconciliation, and operational telemetry, but it never authors canonical
History or owns Worker process lifecycle. Instance alone accepts outcomes and
authors canonical Activity and firing terminal records.

The product profiles are **Inline Dispatch**, **In-Memory Dispatch**, **Local
Dispatch**, and **Durable Dispatch**. `InlineDispatch` executes synchronously
and buffers terminal outcomes only in-process. `InMemoryDispatch` decouples
publication and collection in RAM. Local Dispatch persists custody across a
local process restart; `LocalDispatch` is the current production SQLite
implementation.
Durable Dispatch supports separately placed Workers through provider-backed
queues, Attempts, leases, heartbeat/checkpoint state, and terminal persistence;
`AbsurdDispatch`, built on PostgreSQL, is the current provider implementation.
Absurd and PostgreSQL are not the Dispatch concept. Recovery is at-least-once,
so external effects may repeat; no profile claims exactly-once effects.

### Net runtime

The Impetus Kernel runtime responsible for validating and instantiating net definitions, maintaining markings, computing enabled firing candidates, performing begin/end firing semantics, deriving timer maturations over the clock watermark, recording activity lifecycle facts, and integrating handler-projected effects back into the net. Choosing when to apply scheduler policy, delivering wakeups, and dispatching activities belong to the driving runtime above it.

### Driving runtime

The coordination layer that drives an Instance from above through the
firing-occurrence seam. It applies composable policy to safe whole Actions,
begins selected occurrences, invokes server-side handler preparation,
dispatches Activity invocations, accepts later Activity results and
deliveries, invokes server-side handler projection, and advances recorded
time. Mutation of one `Instance` is serialized; activities may run
concurrently outside that writer.

One advancement call applies at most one normal Action after finite first-load
reconciliation. It reports whether immediate work remains and the next timer
deadline rather than waiting internally. Clock observation is nonblocking;
the host owns wakeups, sleeps, and async multiplexing. The Instance retains
maturation derivation and the clock watermark, so enabledness reads only
recorded facts. Both shipped policies alternate already-buffered ingress with
eligible internal work; custom policy owns its own fairness. If a custom
policy first chooses an immature wall-clock action, it may be called once more
with only that unavailable action removed from the same Snapshot; the turn
still applies no more than one Action.

`Coordinator` is private implementation of the Engine advancement lane. The
legacy `Runner` is retired; maintained operational hosts create or load and
advance a resident public Engine instead. Durable Activity request, Dispatch
acknowledgement, Activity completion, source delivery, and deterministic
projection remain separate events. Real parallelism stays a Worker/substrate
concern outside the serialized Engine lane.

### Sensor

An ingress adapter that offers identified deliveries to armed source
transitions. An Engine Sensor is a prompt, nonblocking observation of
already-available process-local ingress and may be consulted on every
advancement turn. It must not wait for an external API. Blocking pull work is
modeled as an Activity, normally behind an explicit timed control/cursor
place; durable pushed ingress retains broker/webhook custody and enters through
`Engine.deliver()`.

A Sensor may normalize observations and choose a declared coalescing rule
(for example one delivery identity per file-content version). If it learns an
answer before canonical acceptance, it must retain and re-offer that answer
with the same stable delivery identity across later observations or restart
when its substrate supports recovery. The single writer, not the Sensor's
cache or current token presence, enforces idempotent acceptance. Accepted
deliveries are recorded ingress and replayed; Sensors, like handlers and
clocks, are live-side code re-supplied at resume, never replayed. This is an
at-least-once boundary and does not imply exactly-once external effects.

### Correlation identifier

An identity relating several firing occurrences or activity invocations to one broader business operation, such as a payment order. It is not the exact invocation identity and does not by itself make an external call safe to repeat.

### Idempotency key

The stable provider-facing identity of one logical activity invocation. Operational retries of that invocation retain the key. A later business retry creates a new activity invocation and idempotency key even when it keeps the same broader correlation identifier.

### Worker definition

Motus deployment configuration naming the operational queues a Worker subscribes to and the Activity implementations it can execute, plus concurrency and polling. A Worker may use a host-supplied resolver to select an implementation by durable Instance identity and Activity name; an explicit `None` answer falls back to its ordinary default implementation mapping. Cohesive Activity modules, overlays, decorators, clients, and credentials remain live host composition and are reconstructed from configuration rather than serialized into Dispatch. An Activity implementation may declare its default heartbeat timeout; the effective value is resolved and frozen in the invocation's execution policy before dispatch rather than chosen by the Worker at runtime. DevOps/provider configuration supplies compute, accelerators, software, service access, authority, capacity, placement, process health, scaling, and termination. A Worker imports Activity implementations rather than a runnable Net definition and does not invent retry, idempotency, routing, or reconciliation policy.

### Activity queue routing

Operational Engine configuration consisting of one default queue plus optional exact per-Activity queue overrides. Queues provide load balancing, throughput sharing, tenancy isolation, and specialized execution pools without entering `ActivityInvocation` or canonical History. Several Engines may share a default queue, each may use an isolated default, or private defaults may share selected specialized queues. Routing may change between Engine close and load; Dispatch must reconcile old custody before republishing outstanding work to a different queue.

### Worker instance

A running process replica of a Worker definition. It may have a stable operator label and has an ephemeral incarnation per process boot; a network reconnect by the same process retains that incarnation, while restart mints another. Motus requires no durable Worker Registry: queue polling offers capacity, DevOps owns process lifecycle, and Dispatch owns correctness-critical Attempt leases. Worker presence, claims, heartbeats, checkpoints, and resource telemetry are operational state.

### Process

A runnable composition of a net definition, handler and Activity bindings,
History Store, Dispatch, configuration, policies, and secret references. A
self-contained process package may colocate topology, server-side handlers,
Activity declarations/implementations, and default policies while Worker
definitions import only the Activities they serve.

### Reusable component

A packageable Petrus process component that should expose its net definition, default bindings, and process convenience entry point separately. This generic composition term is distinct from the named Impetus, Motus, and Arx project components.

### Subnet

A reusable Petri-net component with a defined interface that can be composed into larger nets.

### Token type ledger

A registry of token colors/types known to a composed net. It helps detect type conflicts and can support type-mediated subnet composition. The exact boundary between formal core and composition layer remains unresolved.

### Handler result

The current synchronous API envelope containing token and delivery-registration effects returned by a handler. It remains shipped compatibility vocabulary, but it is not a separate target worker protocol or durable lifecycle. In the target seam, `ActivityCompleted` freezes external output and the handler projects it directly into movement/effect records plus `FiringCompleted`; no additional `HandlerResultProduced` or `HandlerCompleted` record is needed.

### Deterministic replay

The property that, given the same external events, activity lifecycle facts, and timer events in the same order, a net instance reaches the same state.

### External event

An event originating outside the net instance, such as a webhook, poll result, human decision, activity result, or timer maturation, that is recorded and then used to advance the net.

### Projection

The principle that external world state and events enter a net only as tokens in the marking, never as imperative reads inside filters or guards. Because external conditions are represented as tokens, gating on them is structural — a pure filter, an inhibitor arc, or a control place — which keeps filters and guards pure and enablement replay-deterministic.

### Event projection

The projection primitive: an ingress adapter offers an identified external delivery to a source transition. Acceptance durably records the event and its begun source occurrence without projecting it; a later exact completion locally and atomically projects only that occurrence into typed tokens and delivery-registration effects, and its output arcs route the tokens into places. Replay can reconstruct the accepted unfinished occurrence without private runtime state. Recoverable impure work begins in ordinary downstream handled transitions — enforced: a source transition cannot bind an `ActivityHandler`, and its plain-callable handler is classified as a pure local projection. Delivery identity is recorded on the accepted fact and enforced at the delivery door: exact redelivery reconstructs an unfinished acceptance or returns the prior acknowledgement after completion, with no second semantic fact or token, and the identity check precedes registration validation.

### Source transition

A transition with no input arcs — the entry point for external events. The runtime delivers an identified external fact to a specific source transition; local deterministic projection produces the entry tokens and delivery-registration effects, and output arcs route tokens by color. Source-ness is a structural property (arc shape), not an implementation kind and not a place role. A source transition is excluded from the scheduler's enabled-candidate set: it never auto-fires, firing only on external delivery. A source transition with an armed delivery registration is the structural awaiting marker for instance status.

### State projection

A pattern built on event projection: a standing external condition is kept mirrored as a token in a place, refreshed by repeated event projections when the world changes, so filters or inhibitor arcs can gate on the current condition purely. It is event projection used to maintain a mirror, not a separate mechanism.

### Delivery registration

A binding/runtime-layer record that the runtime may still deliver an external event to a source transition of a net instance — a webhook route, poller, human-task handle, or child-instance signal. A delivery registration is identified by its source transition and a caller-chosen key, and a source transition may hold several, each closable on its own. Delivery registrations are per-instance, opened at instantiation or from an accepted result/projection, and closed by results/projections or runtime policy (seal, the close-all); open and close are recorded process facts. A runtime connection participates in instance status only if it can still deliver; connection health, credentials, and worker mechanics are operational concerns. The public and serialized family is `DeliveryRegistration` / `DeliveryRegistrationOpened` / `DeliveryRegistrationClosed` — the CV3 schema-2 migration executed the ruled rename [DR 2026-07-14 delivery-registration-terminology].

### Quiescent

The state of a net instance in which no firing candidate is enabled under the current marking, no firing occurrence has begun without ending, and no firing binding has a derived future timer maturation. Quiescence is the trigger for deriving instance status, never the verdict itself.

### Instance status

A derived, four-valued projection over a net instance's recorded history — never stored as independent truth: RUNNING while not quiescent; when quiescent, COMPLETED if the declared completion condition holds, else AWAITING if any delivery registration is armed, else STUCK (or the neutral TERMINATED when no completion condition is declared). Status is re-evaluated on any history append, including delivery-registration close.

### Completion condition

An optional net-level declaration: a pure boolean predicate over the marking (inline CEL or a named pure symbol, the same expression tier as filters and guards) that supplies the *done* judgment of instance status. It never affects enabledness or firing; finalization on completion is runtime policy.

### Runtime history address

A possible tooling/audit/debugging reference to a runtime record such as an event, firing occurrence, activity result, token, marking snapshot, or timer record. Runtime history addresses may be useful for timelines, traces, logs, replay visualization, and external links, but they are not part of core Petri-net execution semantics.

### Integration subnet

A reusable subnet that coordinates interaction with an external system. The subnet models process coordination; the connector or handler performs the actual external calls.

### Connector

A library or adapter for talking to an external system such as GitHub, Slack, Jira, a browser, a filesystem, git, or a CLI. A connector does not own process orchestration.

### Human cooperation

A process pattern where a human provides a decision, authorization, credential refresh, or judgment required for a transition's bound handler to complete.
