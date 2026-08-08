# Handler Contract

This document specifies how behavior attaches to an Impetus net: symbol
declarations, implementation mappings, typed handler contracts, guards, and
the runtime split that executes them. Net structure is specified in
`net-schema.md`; when handlers run is specified in `firing-semantics.md`; how
their execution is recorded is specified in `event-history.md`.

## Library, not framework

The contract below is constrained by the library-not-framework rule: Impetus
provides composable primitives and optional high-level entry points, but never
owns the host application's lifecycle [ADR 0001]. The host's deployment model,
server, CLI, worker process, queue, and storage remain host concerns unless
explicitly opted into through a composable package [ADR 0001]. Impetus ships
both a library and a runnable runtime, as separate composable artifacts
Unix-style — the runtime is one consumer of the library packages among several
[DR 2026-07-06 library-plus-runtime-unix-composition].

## Bindings, not kinds

A transition is just a transition; it has **no implementation kind** at the
net level [ADR 0003]. "Agent", "human", "webhook", "polling", and "activity"
are descriptions of *bindings* — a transition may be bound to a handler
implemented with deterministic code, an agent, a human interaction, browser
automation, a Temporal activity, a webhook adapter, a polling function, or any
other callable mechanism [ADR 0003]. Say "transition bound to a Slack polling
handler", never "Slack polling transition" [ADR 0003]. This
transition↔handler seam is the load-bearing extension point of the whole
design [DR 2026-07-06 handlers-own-logic-no-cel-initially].

## Symbols and implementation mappings

The net schema declares **guards** (named symbols or inline CEL expressions —
see §Guards) and **handler symbols** on transitions; concrete functions are
supplied separately through an **implementation mapping** (binding set)
[ADR 0021]. The binding/validation layer MUST verify that every declared
symbol has a corresponding implementation — and every inline expression
compiles — before the process can run [ADR 0021]; missing bindings fail
fast at validation, not mid-firing (production precedent: per-transition
errors at runtime construction [Petrus oracle]).

The mapping is not one-to-one: multiple schema-declared symbols may map to the
same reusable function implementation with different names or configuration
[ADR 0021]. A transition with no handler symbol is **default-bound to the
library's pure `passthrough` handler** — a default binding, not an engine
special case; a small family of pure stdlib shaping handlers may grow beside it,
selectable like any handler symbol — `unpack` (structural projection of an
aggregate token's fields to typed output arcs) is Decided; there is no stdlib
`pack` — aggregate construction stays a user/reusable-component handler
[ADR 0021, ADR 0010, ADR 0002, DR 2026-07-07
passthrough-is-a-default-handler-color-routed, DR 2026-07-08
unpack-stdlib-handler-projection, DR 2026-07-08 pack-aggregation-deferred]
(see `firing-semantics.md`).

Symbols are **scoped** to the net/subnet or transition that declares them, so
reusable subnets can use local names (`prepare`, `isReady`) without global
collisions; during composition and validation, scoped symbols resolve to
fully qualified URI addresses such as `transition:/review/start#handler` and
`transition:/review/start#guard:isReady` [ADR 0022, ADR 0026]. Implementation
mappings can then target declaration URIs or indexes derived from them
[ADR 0025].

Symbols are **transition-local names, subnet-qualified** on resolution
[ADR 0022]. A transition **may declare multiple guards; they compose as
conjunction** — the transition is guard-enabled iff all return true, and order
is irrelevant because guards are pure [DR 2026-07-08
handler-symbols-guards-and-nominal-color-matching]. An implementation mapping
**may bind a symbol to a reusable function with configuration** (parameterized;
the same function bound under different names/config) [ADR 0021].

Every handler declaration and authored guard occurrence also has a canonical
identity. The handler uses `transition:/path#handler`; a named guard uses
`#guard:name`; an anonymous or inline guard at absolute authored position `N`
uses `#guard:$N`. `$` is reserved for generated names and duplicate named
guards on one transition are invalid. A mapping may bind an exact declaration
URI, while a named declaration may instead use its bare local symbol to share
one implementation deliberately. Supplying both for one declaration is
ambiguous and fails before execution; anonymous declarations require exact URI
binding [DR 2026-07-28
transition-behavior-declarations-have-occurrence-identities].

The Python authored-net frontend may carry a `@direct` callable specification
or normalize a callable in guard position as a typed predicate until canonical
`Net` construction. It then writes an anonymous handler or guard marker into
the canonical declaration and places the adapted implementation in `BuiltNet`
under that declaration's exact `NetUri`. It never derives declaration identity
from `callable.__name__`. Callable position or an explicit advanced Petri-aware
wrapper selects the semantic flavor before signature inspection; signatures
are inspected only inside the selected typed transformation/predicate adapter
[DR 2026-07-28
python-dsl-compiles-authored-specifications-to-canonical-nets].

## The handler contract

A **handler** is a server-side, Petri-aware callable implementation bound to
a transition: it receives relevant token data and execution context and
produces token data, registration effects, or failure events. A pure handler
projects its firing effects locally. An impure handler deterministically
prepares one Petri-agnostic **activity invocation** from the immutable firing
binding and later projects the frozen activity result into net effects; the
activity — not the handler — is what a worker executes [DR 2026-07-14
activity-invocation-runtime-seam, CONTEXT.md]. The **handler
implementation/contract is the source of truth
for its typed inputs and outputs** [ADR 0020]. The net schema does not
duplicate transition input declarations to name handler arguments or repeat
type signatures [ADR 0020]; arc inscriptions stay structural (color/type +
cardinality [ADR 0018, ADR 0019]).

When a handler binds to a transition, the binding layer validates that the
transition's incoming/outgoing arcs can satisfy the handler's declared
input/output contract [ADR 0020]. For **typed handlers**, selected tokens are
resolved by matching the handler's required input types against the incoming
arc token types; the handler receives typed arguments per its own
contract/signature [ADR 0020]. For fallback cases, a **generic token-set
handler** receives the selected token set or context bag directly and
interprets it itself [ADR 0020, CONTEXT.md]. If multiple incoming arcs supply
the same token color, the binding layer requires disambiguation through
handler contract metadata, transition-local configuration, or a generic
token-set handler — never arc-level argument names [ADR 0020, ADR 0019].

Language-specific cleverness (e.g. the Petrus oracle's `get_type_hints`-based
kwargs extraction) belongs in a binding, not in this spec
[DR 2026-07-06 implementation-language-python-first; Petrus oracle].

**Color matching is nominal; data access is structural.** An arc admits color
`Payment` iff a token's declared color *is* `Payment` (a name match); filters,
guards, and handlers then read the token's structured data (including aggregate
fields) structurally [DR 2026-07-08 handler-symbols-guards-and-nominal-color-matching,
DR aggregate-token-type]. Per-language contract declaration remains a
binding-layer detail [ADR 0020, DR 2026-07-08 kernel-deferred-spec-details].
The Python reference binding provides one narrow derived form: a typed
transformation or predicate over concrete dataclass parameters, each matched
uniquely to one effective weight-one consume/read arc by nominal color. A
transformation's concrete dataclass result must match every weight-one output
arc; a predicate must declare and return exact `bool`. Source transitions,
collections/weighted selections, ambiguous same-color inputs, unions,
heterogeneous outputs, and registration effects require an explicit
Petri-aware binding instead of inference [DR 2026-07-28
production-typed-transform-binding].

## Guards

A **guard** is a pure boolean over the full firing binding, declared as a
named symbol (a boolean function bound through the implementation mapping) or
an inline CEL expression (compiled at instantiation); it participates in
enabledness by returning true or false over peeked (unconsumed) tokens
[ADR 0021, CONTEXT.md, DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure]. Cross-token conditions and
correlation live in guards, not arc inscriptions [ADR 0018].

Filters and guards are **pure** and each carry either an inline CEL expression
or a named pure symbol resolved through the binding layer: a filter sees one
token (per-arc), a guard sees the full binding (transition-level, where
correlation lives) [ADR 0018, DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure]. **Every process side effect lives
behind a handler** — for an impure transition, inside the one Petri-agnostic
activity it prepares (imperative, ideally reusable code); external
state a guard would need enters the marking by projection [DR 2026-07-07
purity-invariant-and-projection, DR 2026-07-14
activity-invocation-runtime-seam]. Because CEL is bound through a `CelAdapter` and
named symbols through the binding layer, inline expressions stay portable across
languages without schema changes — the seam is adapter-compatible
[DR 2026-07-06 handlers-own-logic-no-cel-initially].

**VELOCITRON-ALIGNMENT:** velocitron centers logic on arcs carrying CEL
predicates (pure, sandbox-safe, cross-language) with possibly-impure guards.
Impetus adopts the same idea — arc filters and guards each carrying inline CEL or
a named symbol — but makes **both pure**, with impurity confined behind handlers
(in the activities they prepare) and
external state entering by projection [DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure, DR 2026-07-07
purity-invariant-and-projection]. Status: decided for Impetus and aligned with
Matt (ES-003, 2026-07-07).

## Petrinet, activity, binding, and execution boundaries

Impetus separates concepts before runtime composition [ADR 0012, DR 2026-07-21
concept-first-ontology-boundaries]:

- **Petrinet Kernel** owns `Net`, Instance semantics, markings, enabledness,
  firing, and replay-derived state, but not Candidate Selection;
- **activity** owns Petri/history-agnostic `Activity`, `ActivityInvocation`,
  `ActivityFailure`, `ExecutionPolicy`, and result conventions;
- **binding** owns `Handler`, `HandlerResult`, and the Petri-aware
  `ActivityHandler.prepare/project` bridge;
- **dispatch/execution adapters** execute activity invocations —
  local inline/concurrent execution, Temporal, worker queues, distributed
  workers, or other substrates.

For an impure firing, the server-side handler prepares the activity
invocation, the begin batch freezes it as `ActivityRequested`, the execution
runtime dispatches and executes it and reports the terminal activity fact
back, and the server-side handler projects the frozen result before the net
runtime performs end firing and advances the marking [ADR 0012, DR 2026-07-14
activity-invocation-runtime-seam]. Temporal is an execution runtime option,
never the net runtime itself [ADR 0012]. An **activity** is the
Petri-agnostic unit of work a handler prepares and a worker executes — not a
kind of transition [ADR 0003, DR 2026-07-14 activity-invocation-runtime-seam,
CONTEXT.md]. The activity's terminal result is a durable observed fact; the
handler's deterministic projection is represented directly by the token,
registration open/close, and failure records it produces [ADR 0004, ADR 0034]
(see `event-history.md`). The shipped seam separates the phases exactly so:
an `ActivityHandler` binding's `prepare(binding)` freezes `ActivityRequested`
in the begin batch, an execution adapter (the shipped `InlineAdapter`, or a
real substrate) executes the invocation, `ActivityCompleted` freezes the
typed result before `project(binding, result)` commits the deterministic
projection; a plain callable binding is a pure projection with no activity
records. `HandlerResultRecorded` is retired. Canonical schema 3 carries no
Worker capability or queue-routing field in either `ActivityInvocation` or
`ActivityRequested`; Engine configuration routes by exact Activity name over
an operational default queue plus optional overrides.

## Reusable components

Reusable components expose three layers separately [ADR 0002]:

```txt
somethingNet()        — the declarative net/subnet definition only
somethingBindings(..) — default handler/guard implementations for that net
somethingProcess(..)  — convenience composition: net + default bindings + runtime/config
```

So a user can reuse a net with custom handlers, reuse handlers with a modified
net when contracts still match, swap local for remote execution, or replace an
integration library without changing process topology [ADR 0002]. A
**process** is the runnable composition of net definition, bindings, runtime
adapter, configuration, policies, and secret references [CONTEXT.md].
Encoding handler kinds into transition types was explicitly rejected
[ADR 0002, ADR 0003].
