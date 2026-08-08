  # Net Schema

This document specifies the structure of an Impetus **net definition**: the
declarative, language-neutral description of process topology and coordination
semantics. How a net executes is specified in `firing-semantics.md`; how
declared symbols bind to code is specified in `handler-contract.md`; how
execution is recorded is specified in `event-history.md`.

## Net definition vs net instance

A **net definition** describes process topology and coordination semantics:
places, transitions, arcs, token/color types, guards, subnet boundaries, and
transition contracts. It contains no concrete external behavior — no GitHub
clients, LLM calls, worker queues, or deployment choices [CONTEXT.md].

A **Petrinet Instance** (publicly `Instance`; the current pre-release root alias
`NetInstance` is scheduled for removal) is a durable execution of a `Net`, with concrete
tokens, a current marking, event history, timers, and recorded activity results
[CONTEXT.md]. Many independent Instances of one Net run concurrently, each
with its own marking and canonical history. There is no single global net;
Instances communicate through identified messaging, never shared state. The
older process analogy is superseded as formal ontology while its per-Instance
history, isolation, messaging, and single-writer invariants remain
[DR 2026-07-21 concept-first-ontology-boundaries].

## Explicit schema, never derived

The Impetus core requires a well-defined explicit net schema. The core MUST NOT
derive the net from handlers; handlers bind to transitions in an
already-defined schema [ADR 0011]. Higher-level pipeline or handler-first APIs
may exist later as optional layers that *produce* explicit net definitions, but
they do not define core semantics [ADR 0011].

## Nodes

A **node** is a place or a transition — nothing else. Arcs, guards, handlers,
timers, and initial markings are not nodes [ADR 0024]. Places and transitions
share the same node namespace within each parent scope, so a node address
identifies exactly one node without a node-kind discriminator [ADR 0015].
Authors must avoid local name collisions between a place and a transition;
validation rejects them [ADR 0015].

## Places

A place is a location that holds colored tokens [CONTEXT.md]. A place MAY
declare one nominal **color** as an authoring default for its token domain; an
untyped place holds tokens of any color. During flattened-net construction, a
place color is resolved once onto each otherwise-untyped incident arc. An
explicit arc color must match a typed place or validation rejects the conflict.
The runtime therefore continues to execute one effective arc-inscription
contract with no place lookup during enabledness or routing
[DR 2026-07-27 place-colors-compile-to-effective-arc-inscriptions].

A typed place's initial marking MUST contain only its declared color; validation
rejects a mismatch before recording initial History. A place with no outgoing
arcs remains a legal accumulator (e.g. a counter summed by a projection). The
token types known to a composed net are derived from place colors, arc
inscriptions, handler contracts, and initial markings [CONTEXT.md].

A place MAY carry an optional **role** annotation: `input` (externally
fed/boundary-start), `output` (emitted results/boundary output), `control`
(coordination, gates, joins, limits, retries, leases, scheduling state), or
`regular` (ordinary domain data). An unannotated place is treated as `regular`
for display and tooling. Roles never affect enabledness or firing semantics —
a place remains an ordinary place [ADR 0027].

Places have no time-related behavior; timers belong to transitions
[ADR 0005] (see `firing-semantics.md`).

## Transitions

A transition is a process step that may fire when enabled; transitions are the
only things that fire [CONTEXT.md]. A transition has **no implementation
kind**. Terms such as agent, human, webhook, polling, or activity describe
bindings or handlers, not transition types in the net [ADR 0003]. The same net
definition remains portable across handler implementations [ADR 0003].

A transition MAY declare:

- **guards** — pure booleans over the full firing binding, each declared as a
  named symbol or an inline CEL expression [ADR 0021, DR 2026-07-07
  arc-filters-and-guards-cel-or-named-both-pure];
- **a handler symbol** — a scoped name identifying the expected handler [ADR 0021];
- **timer declarations** — time-based enablement constraints [ADR 0005].

Symbols are declarations, not code: concrete implementations are supplied
through an implementation mapping validated before the process can run
[ADR 0021] (see `handler-contract.md`); inline CEL compiles at instantiation,
the same fail-fast boundary. A transition with no handler symbol
uses default passthrough behavior [ADR 0010, ADR 0022].

### Source transitions

A **source transition** has **no input arcs**. It is the entry point for
discrete external events (webhook, signal, poll result, human decision,
child-instance message): the runtime delivers an external event to a specific
source transition, its handler turns the delivered payload into typed token(s),
and its output arcs route them by color into places [DR 2026-07-08
source-transition-ingress]. Source-ness is a **structural** property (arc
shape), not an implementation kind [ADR 0003] and not a place/role annotation
[ADR 0027].

A source transition is **excluded from the scheduler's enabled-candidate set**:
it never auto-fires and never fires spontaneously; it fires only on external
delivery (see `firing-semantics.md` §Scheduling). A source transition with an
armed event-projection registration is the structural *awaiting* marker
for the termination status rule [DR 2026-07-08 termination-instance-status-rule].
Because output-arc color contracts route by type and unmatched tokens are
leftover [DR permissive-flow-defaults], one general source transition can
demultiplex mixed incoming events to different places with no extra machinery.

## Arcs

An arc is a directed connection between two nodes, modeled with `from` and
`to` endpoints [ADR 0016]. Valid arcs connect place → transition (input arcs)
or transition → place (output arcs); validation MUST reject place → place and
transition → transition [ADR 0016]. Convenience constructors such as
`inputArc(place, transition)` may exist, but they compile to the same
`from`/`to` representation [ADR 0016].

### Input arc modes

Arc mode applies **only to input arcs** [ADR 0017]. The core supports exactly
three modes [ADR 0006]:

- **consume** — requires matching token(s) and consumes them when the transition fires;
- **read** — requires matching token(s) for enablement and firing binding, but does not consume them;
- **inhibit** — requires the *absence* of matching token(s) for enablement.

Reserve arcs are deliberately not core; leases, retries, timeouts, and
side-effect claims are execution-runtime responsibilities [ADR 0006].

### Inscriptions

**Inscriptions are narrowing annotations; authored arcs are untyped by
default** [DR 2026-07-07 permissive-flow-defaults]. At flattened-net
construction, an otherwise-untyped arc incident to a typed place receives the
place's color as its effective inscription. An arc that remains untyped after
resolution admits any token (weight one by default). Declaring an arc color
narrows an untyped place's flow; a filter narrows an input arc further
[DR 2026-07-27 place-colors-compile-to-effective-arc-inscriptions].

An input inscription may express the required token color/type and cardinality,
plus an optional **filter**: a pure, single-token boolean that selects which
tokens of the declared color the arc admits [ADR 0018, DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure]. A filter is written as an inline
CEL expression or a named pure symbol, and sees exactly one token — which may
itself be an aggregate color carrying nested typed data [DR 2026-07-07
aggregate-token-type-single-type-per-token]. The filter, like weight, applies to
every input arc mode — consume, read, and inhibit; an inhibit filter gates on the
absence of a *matching* token. Inscriptions MUST NOT bind handler argument names;
argument resolution belongs to the transition/handler contract [ADR 0019].
Cross-token conditions and correlation logic span multiple arcs and therefore
live in transition guards, never in a single arc's filter [ADR 0018].

Output arcs do not have consume/read/inhibit modes; each output arc carries an
**output inscription** — a routing contract naming the token color/type it
admits into its target place (untyped after place-color resolution = admits
anything) [ADR 0017,
DR 2026-07-07 output-production-per-arc-contract-handler-supplies-tokens,
DR permissive-flow-defaults]. The **handler supplies the actual output tokens**
(keyed by destination); the runtime deposits only handler tokens whose color
and destination match an output arc, so different arcs may carry different
payloads from one firing (heterogeneous fan-out). Under the default
`passthrough` handler, each consumed token is forwarded through every admitting
output arc [DR 2026-07-07 passthrough-is-a-default-handler-color-routed]. The
inscription is a checkable contract, not a token factory; complex output
shaping belongs in the handler, never in inscription inference
[ADR 0018, ADR 0010].
Note an explicit difference from the oracle here: the Petrus engine deposits
ONE merged token to ALL output places of a firing (fan-out duplicates the same
payload to every branch), a known outlier versus per-arc output contracts
[Petrus oracle]. Impetus specs the per-arc position: output production is
described per output arc by its own inscription, with the handler supplying the
actual tokens keyed by destination [ADR 0017, DR 2026-07-07
output-production-per-arc-contract-handler-supplies-tokens]. Golden-trace
fixtures that pin the oracle behavior are tracked as debt
(`docs/project/debt/items/2026-07-07T1730Z-golden-traces-encode-oracle-merged-token-fanout.md`).

**VELOCITRON-ALIGNMENT (input side, decided):** velocitron arcs carry
`{type, predicate, mode}` with an inline-CEL-or-named predicate. Impetus adopts
the same shape — an arc **filter** (CEL or named symbol) — and extends the
encoding to guards, with two deliberate differences: (1) both filters and guards
are **pure** in Impetus (velocitron permits impure guards); impurity lives only
in handlers, and external state enters the net by projection [DR 2026-07-07
purity-invariant-and-projection]; (2) the filter and weight apply to all arc
modes including inhibit (weighted inhibitors match the Petrus `is_satisfied`
rule; velocitron rejects weight on inhibit). Cross-token correlation still lives
in guards in both systems. Status: decided for Impetus and aligned with Matt
(ES-003, 2026-07-07) [DR 2026-07-07 arc-filters-and-guards-cel-or-named-both-pure].

### Arc identity

Multiple arcs between the same endpoint pair are allowed (e.g. consume + read
+ inhibit relationships, or different colors) [ADR 0029]. The canonical arc
URI is endpoint-derived, `arc:/review/pending->/review/start`; when the
endpoint pair is ambiguous, a fragment disambiguates — an author-supplied arc
ID (`#claim-review`) or a deterministic generated fragment (`#$0`)
[ADR 0029]. Arc identity does not depend on mode/color/cardinality, so
changing an inscription does not necessarily change identity; stable public
references should use explicit arc IDs [ADR 0029].

## Completion condition

A net MAY declare one **completion condition**: a pure boolean predicate over
the marking, written as an inline CEL expression or a named pure symbol —
the same expression tier as filters and guards [DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure]. It is a net-level declaration
with canonical NetUri fragment `#completion` [ADR 0024, ADR 0025]. The
condition **never affects enabledness or firing** — like place roles, it
changes what the runtime reports, never what fires [ADR 0027 discipline,
DR 2026-07-08 termination-instance-status-rule]; it supplies the *done*
judgment of the derived instance status (see `firing-semantics.md`
§Termination). Declaring it is optional (permissive default); without it the
runtime cannot distinguish COMPLETED from STUCK and reports a neutral
TERMINATED, which validators MAY warn about [DR permissive-flow-defaults
posture]. The validation run checks that the condition's place references
resolve and that a named symbol has embodiment [ADR 0021].

## Colored tokens and markings

A **colored token** carries typed data; its **token color** is the type/schema
associated with it. Colored tokens unify control flow and data flow
[CONTEXT.md]. The **marking** — the distribution of colored tokens across
places — is the first-class state of a net instance [ADR 0012, CONTEXT.md].
For reference, the Petrus oracle stores markings as per-place FIFO token
queues: consume pops from the front, deposit appends [Petrus oracle].

## Addressing

- **NetPath** is a first-class static address object, not an arbitrary string:
  composable, inspectable, validated strictly at load/instantiation time
  [ADR 0013]. A NetPath addresses only place and transition nodes; internally
  all resolved paths are absolute, while authoring APIs may accept relative
  references that resolve against a root path or net context [ADR 0014].
- **NetUri** addresses any addressable part of the composed net; NetPath is
  the node-address subset of NetUri [ADR 0023]. Arc endpoints and markings key
  by NetPath; implementation mappings and diagnostics may use NetUri
  [ADR 0023].
- Guard and handler symbols are scoped to their declaring net/subnet or
  transition and resolve to fully qualified addresses during composition
  [ADR 0022].
- The working canonical syntax uses **typed URI schemes** for graph citizens —
  `place:/review/pending`, `transition:/review/start`,
  `arc:/review/pending->/review/start` — with declarations anchored on their
  owner via fragments: `transition:/review/start#handler`,
  `transition:/review/start#guard:isReady`, `place:/review/pending#initial`
  [ADR 0026, ADR 0024].
- A handler and every authored guard occurrence have canonical identities. A
  named guard uses `#guard:name`; an anonymous or inline guard at absolute
  zero-based authored position `N` uses `#guard:$N`. Leading `$` is reserved
  for generated names, and duplicate named guards on one transition are
  invalid because they would claim one URI [DR 2026-07-28
  transition-behavior-declarations-have-occurrence-identities].
- **Runtime history addresses** (URIs for events, firing occurrences, tokens,
  marking snapshots) may exist for tooling, audit, and debugging only; core
  execution operates on explicit records and indexes, never on URI-shaped
  history references [ADR 0028]. That is: history URIs are minted *from*
  records for display and cross-referencing; execution APIs accept typed
  records and IDs (`firingOccurrenceId`, `eventId`, …) and never parse URIs to
  locate runtime state [ADR 0028, ADR 0035].

The canonical URI form is **ASCII**: `->` is the canonical arc-endpoint
spelling (not merely display), and reserved characters are percent-escaped
within segments; the full escaping table is kernel-revealed
[DR 2026-07-08 addressing-uri-syntax-and-public-surface]. **NetPath** is the
primary public node-addressing surface (schemeless, structured); typed `NetUri`
is the canonical serialized/diagnostic form, used where any addressable part —
not just a node — must be named [ADR 0023, DR addressing-uri-syntax-and-public-surface].

## Flattened net

Nested nets and subnets compile into a **flattened net**: a flat set of
addressed places, transitions, arcs, and declarations for efficient execution
and lookup [ADR 0012, CONTEXT.md]. In the flattened net every declaration —
including anonymous ones — receives a deterministic canonical NetUri
[ADR 0025]. The flattened net exposes typed indexes: a node dictionary keyed
by NetPath, a declaration dictionary keyed by NetUri, and binding-oriented
indexes for handler, guard, timer, and initial-marking declarations
[ADR 0025, ADR 0026].

Generated declaration URIs (`transition:/x#handler`, `place:/p#initial`) are
**internal by default** — for bindings, diagnostics, and tooling, not a primary
user-facing surface [ADR 0025, ADR 0028,
DR 2026-07-08 addressing-uri-syntax-and-public-surface].

For transition behavior, the flattened net indexes the one handler declaration
and every ordered guard occurrence by canonical `NetUri`. An anonymous behavior
declaration has an explicit language-neutral marker rather than a fabricated
local symbol. This first executable identity slice does not yet claim complete
indexes for filters, timers, completion, or initial markings [DR 2026-07-28
transition-behavior-declarations-have-occurrence-identities].

### Python authored-net frontend

The Python reference package provides `petrus.impetus.dsl` as an authoring frontend,
not a second runtime schema or part of the independent Petrinet Kernel.
`NodeSpec` (`PlaceSpec` and `TransitionSpec`), `ArcSpec`, and `ConnectionSpec`
retain the minimal authored information needed before lowering.
`NetSpec` owns one mutable authored definition and may serve as the root or as
a reusable definition stamped at a destination `ScopeSpec`. `NetBuilder`
recursively composes one root `NetSpec` and snapshots the effective authored
graph into an immutable `BuiltNet`, whose `net` is the canonical flattened
`Net`; canonical construction remains the one topology-validation and
place-color-resolution boundary.

`destination.stamp(source)` records a live reusable-definition stamp.
Every build sees the source's current authored state, while prior `BuiltNet`
snapshots remain immutable. Each destination owns field-selective node
overrides that cannot mutate the source or a sibling stamp. Stamping a
new source at the same destination replaces the complete inherited body and
clears those overrides. A destination with directly authored content refuses
stamping rather than silently erasing or merging ownership. Parent topology
wires explicitly to nodes under the returned destination scope. Nested
stamps flatten recursively; cycles and child completion declarations
fail composition. `NetSpec.copy()` instead captures an independent flattened
authored snapshot and retains no live source relationships.

`PlaceSpec(color)` and `TransitionSpec(handler=..., guards=..., timers=...)`
configure and return the same stable `NetSpec`-owned node identity. A later bare
reference therefore retains prior configuration, while every `>>` expression
still authors a new arc and preserves multiplicity. Identical repeated
configuration is idempotent and conflicting declaration fails.
`PlaceSpec.override(color=...)` and
`TransitionSpec.override(handler=..., guards=..., timers=...)` deliberately
change only supplied fields of an existing explicit or inherited configuration;
omission preserves, while `None` or an empty tuple explicitly clears its field.
Override collections replace atomically rather than append or merge. An
override is not an upsert, and all supplied values normalize before the
effective immutable configuration record changes. Configuration recorded after
topology applies when the builder next compiles, without mutating an earlier
`BuiltNet` snapshot. Node specs are rejected explicitly at callable handler and
guard boundaries rather than being mistaken for behavior callables. The former
whole-record `replace_transition` authoring path is removed.

Connections use only Python's `>>`: a default connection is
`place >> transition`, while an explicit consume, read, or inhibit inscription
uses `arc(...)`, `arc.read(...)`, or `arc.inhibit(...)`. The DSL factory does
not accept a mode parameter; the canonical schema retains `ArcMode`. Tuples
deterministically expand fan-in or fan-out. `>` is not part of the grammar
because Python comparison chaining cannot safely carry a pending inscription.
Dynamic `s` navigation remains a path-local authoring view; reusable semantics
begin only with explicit `ScopeSpec.stamp(...)`. Authored `NodeSpec` paths are
private construction state. `abs(node)` explicitly projects the node's path
relative to its owning `NetSpec`; a reusable source handle therefore does not
identify any destination occurrence. Runtime identity remains the canonical
`NetPath`/`NetUri` produced by composition. The Python adapter may project a
class supplied as a place or arc color to its nominal `__name__`; the canonical
schema still receives only `Color` strings
[DR 2026-07-27 place-colors-compile-to-effective-arc-inscriptions, DR
2026-07-28 python-dsl-compiles-authored-specifications-to-canonical-nets, DR
2026-07-28 reusable-net-specifications-stamp-at-scopes].

Attribute scope navigation is preferred for ordinary Python identifiers.
`scope[segment]` addresses exactly one non-empty segment when a path name
collides with authoring vocabulary such as `p`, `t`, `s`, or `stamp`; dots are
rejected because one item access cannot silently introduce several scopes.

`direct(...)` or `@direct` marks a pure typed transformation for local
execution and preserves concise `handler=function` transition spelling. An
ordinary callable in `guards` is a pure typed predicate by DSL rule; no guard
decorator is required. Named strings and inline `Cel` remain direct guard
declarations, a scalar guard normalizes to a one-element tuple, and mixed
tuples retain authored order. Existing low-level `Binding` callables use the
advanced `petri_handler(...)` and `petri_guard(...)` escape hatches rather than
being confused with typed domain functions. External work remains an Activity
and may be declared by name for late host binding. Callable specifications
lower to anonymous canonical declarations only after `Net` has validated
topology and resolved place colors. `BuiltNet` keeps the resulting code in
immutable declaration-URI-keyed handler and guard maps, never in canonical
`Transition` values [DR 2026-07-28
transition-behavior-declarations-have-occurrence-identities].

### Python Graphviz presentation

The Python reference package presents a canonical `Net` through
`petrus.impetus.petrinet.dot`; it does not add rendering behavior to `Net` and does
not accept the DSL's `BuiltNet` wrapper. Deterministic DOT generation follows
the canonical place, transition, and arc order. Presentation code queries
`Arc.is_consume`, `Arc.is_read`, and `Arc.is_inhibit` rather than exposing the
schema's `ArcMode` enum. A separate local adapter may invoke Graphviz for SVG,
PNG, or PDF output.

Node labels may show declaration summaries, and an optional `Marking` overlay
may show token counts only. Presentation MUST NOT inspect token data, compute
enabledness, or persist structural meaning. In particular, visual clusters
derived from the first `NetPath` segment are grouping aids over the already
flattened graph; they do not create subnet, composition, or runtime semantics
[DR 2026-07-28 canonical-net-graphviz-rendering-is-presentation-only]. A
source transition may be marked from the canonical structural judgment
`Net.is_source`; this identifies an external ingress door, not one universal
process start. The reference renderer gives those transitions a heavier dashed
outline while retaining the ordinary transition color. Rich labels visually
separate the leaf node name from secondary color/declaration metadata. Their
dynamic text is HTML-escaped; ordinary DOT attributes remain quoted. An
anonymous declaration may carry an optional callable display name. That hint
is excluded from equality and hashing, does not participate in declaration
URIs or runtime binding, and lets presentation surfaces distinguish callable
handlers and guards without fabricating canonical symbols.

**DEFERRED (kernel):** Source maps — tracing flattened-net elements back to
their authoring file/subnet/mount/symbol — are a tooling/debug feature with no
core-semantics impact; the model is deferred to kernel/editor time
[DR 2026-07-08 kernel-deferred-spec-details].
