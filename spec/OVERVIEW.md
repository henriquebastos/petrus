# Impetus — design overview

A narrative synthesis of the ratified model, for a reader who should understand
Impetus without reading every decision record. The four spec documents
(`net-schema`, `firing-semantics`, `event-history`, `handler-contract`) are the
normative reference; `docs/project/glossary/` holds the term definitions,
one file per term; this file is the map.

## The one idea

Impetus is an agentic Petri net runtime. Its thesis: **the durable thing is the
net, not the agent.** Where most systems put an agent and its private state at
the center, Impetus breaks the hidden `while not done` loop into explicit,
event-backed coordination — `event history + marking → enabled transitions →
selected firing → recorded result → new marking` — and lets an agent live
*inside* the net as one transition handler among many. Context, loop, history,
queue, and Worker are separate concepts (context is a view over history; the
loop is scheduling policy; history is durable truth; operational queues deliver
Activity work; Workers subscribe and DevOps provisions them), not one tangled
process. Queue routing belongs to live Engine configuration and never canonical
History.

## The net

A **net definition** is places, transitions, and arcs; a **net instance** is a
running execution with a marking (the distribution of colored tokens) and its
own event history. A **colored token** carries typed data and has exactly one
**color** (which may be an aggregate type with nested fields). Color matching is
**nominal** — an arc admits color `Payment` iff a token's declared color *is*
`Payment` — while filters and handlers read the token's data **structurally**.
A place may declare one nominal color as its authoring default; otherwise it
holds any token. Flattening resolves that default into effective incident arc
colors, while explicit arc colors narrow heterogeneous places.

## Flow: anything flows, then shape down

The default is **permissive** — arcs left untyped after place-color resolution
admit anything, tokens flow, sinks and accumulators are legal, a consumed token
matching no output arc is simply dropped. You **shape** the flow with narrowing
annotations: a place's ordinary color, an input arc's color + optional pure
**filter** (single-token, CEL or named symbol); arc modes
**consume / read / inhibit**; a transition **guard** (pure, over the whole
binding, where cross-token correlation lives); weights. A transition with no
handler is default-bound to the pure **`passthrough`** handler, which routes
each consumed token through every admitting output arc. One more pure stdlib
shaping handler is Decided but not yet implemented: **`unpack`** (project an
aggregate's fields to typed output arcs). There is deliberately **no `pack`**
— construction is a user handler's job, because a built-in constructor would
drift into a hidden expression language and couple the net to type
construction.

## Behavior lives in handlers

Transitions carry **no implementation kind**; "agent", "human", "webhook" name
*bindings*, not transition types. The load-bearing seam is the decoupling of a
transition from its handler: **every process side effect lives behind a
handler**; filters and guards are pure. A handler is server-side and
Petri-aware: a pure one projects its effects locally, an impure one prepares
one Petri-agnostic **activity** — the imperative work a worker executes — and
projects its frozen result back into the net. The **net runtime**
(Impetus-owned) owns net semantics and state; an **execution runtime** adapter
(local, Temporal, queues, …) runs the activities. Output is per-arc: each output
arc is a routing contract, the handler supplies the actual tokens keyed by
destination, so one firing can fan out different payloads to different branches.

## Firing and scheduling

A transition is **enabled** when its input arcs (with filters), inhibitors, and
guards are satisfied and its timers matured. Firing is a durable **begin/end
lifecycle** (consume at begin, produce at end) so handlers can take time, retry,
or run elsewhere. The ruled **Transition Selection** target is Engine-composed
per Instance and chooses at most one enabled Binding within a `BeginCandidate`
action. Planned initial policies are First, Priority, and transition-level
Round-Robin, while whole-action `DrivingPolicy` remains separate. Selection
state installs only after begin commits. Evaluation errors
skip the offending binding deterministically and surface a diagnostic, never
silently disabling a transition.

## The outside world, made deterministic

External state enters a net **only as tokens** (projection). Discrete events
arrive through a **source transition** (no input arcs): the runtime delivers an
event, the transition's handler turns it into typed tokens, output arcs route
them. Source transitions are **excluded from Transition Selection** — they fire only on
external delivery, so a source transition with an armed event-projection
registration is the structural *awaiting* marker. Continuous time enters through the **clock watermark** (the instant of
the latest recorded event; "now" never reads a wall clock). Because impurity is
recorded as facts, replay is deterministic.

## The event history is the source of truth

Each instance has **one append-only, uncompacted event history**. Every firing
is recorded — including pure ones — as **deterministic records** (token
movements are explicit, not deltas); impure work additionally leaves **activity
records** (observed facts, never re-run). So **replay re-applies recorded token
movements in order and never re-executes a handler** — uniform, scheduler-
independent, and possible without the handler code present. Derived views
(current marking, and a four-valued instance **status**: RUNNING / AWAITING /
COMPLETED / STUCK) are rebuildable projections, never the canonical truth.

An explicit **lifecycle scope** `(name, generation)` can own queued token
occurrences and firing occurrences. Canonical open/close/reset records make
generation replacement replayable: close discards exact queued occurrences,
reset atomically closes N and opens N+1, and consumed inputs are never restored
implicitly. History commits this business truth before Dispatch installs
recoverable operational cancellation fences. Proven-closed ingress is
acknowledged and dropped; uncertain-generation ingress and late terminal
reports are quarantined rather than silently retargeted. Append order—not
timestamps—decides every lifecycle race.

## An Instance is isolated durable state

Many Instances of one definition run independently, each with its own marking,
single-writer event history, credentials, and integrations. Instances
communicate through identified messages rather than shared marking or shared
semantic History. Distribution is therefore a **routing** problem (place
execution across machines), not a shared-state problem. The whole-action
coordination implementation is private pending Engine–Instance ownership
research; this specification does not define a public Authority concept.

## The shape of the thing

Impetus is **a library and a runtime, composed Unix-style — never a framework**:
small packages (core semantics, schema, binding, net runtime, adapters) plus a
runnable opinionated runtime built from them. It is **Python-first** with a
**language-neutral spec and golden-trace corpus**, so the Python kernel is the
reference binding and a future TypeScript binding validates against the same
traces.

## Current implementation and remaining work

The core semantics are ratified and the Python reference kernel is delivered.
The normative Impetus-native traces under `spec/traces/` exercise the canonical
Net-definition and History contracts without an external oracle. The current
runtime surface, operating profiles, and blocked boundaries are summarized in
the [project briefing](../docs/project/briefing.md) and
[roadmap](../docs/project/roadmap/index.md); retained structural costs and their
revisit triggers live in the [Technical Debt Ledger](../docs/project/debt/).

This overview is a map of the settled semantic model, not a current-work queue.
Future work should begin from those project indexes and then return to the four
normative specification documents for the contract being changed.
