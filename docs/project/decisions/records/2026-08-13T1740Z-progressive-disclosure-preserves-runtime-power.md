---
status: Decided
raised: 2026-08-13
decided: 2026-08-13
deciders:
  - henrique (Navigator)
supersedes:
related:
  - ES-055
  - ES-056
  - docs/product/principles.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
  - docs/project/decisions/records/2026-08-03T2130Z-flat-json-is-the-canonical-net-definition-interchange.md
---

# Progressive disclosure preserves runtime power

## Question

Should Petrus improve developer experience by simplifying its runtime model, or
by placing a much simpler authoring and first-motion experience over the full
runtime while retaining explicit lower-level access?

## Decision

Preserve Petrus's full runtime power and every honest low-level escape hatch.
Improve developer experience through progressive disclosure above the existing
Net, History, Activity, and authority boundaries; do not weaken those
boundaries or replace them with implicit host-language control flow.

The target is **one readable flow file to first motion**. A Hamsterdan-scale
application should express its Petri-net architecture radically more simply
than it does today. HTTP and GitHub clients, agent machinery, credentials,
storage, dispatch, and host infrastructure may be imported or composed behind
or beside the flow. They do not all have to live in that one file. “One file”
names the authored flow/application surface, not canonical runtime state or a
single-file deployment constraint.

Any higher-level surface must lower deterministically to inspectable canonical
topology and keep validation, replay, resume, source explanation, and explicit
failure behavior available. Advanced authors must be able to descend to lower
Petrus layers for unusual topology or execution needs. Generated authoring may
produce reviewable source or canonical artifacts but must never auto-execute
them.

## Rationale

Petrus already owns capabilities that lightweight imperative workflow tools
discard: explicit topology, canonical History, durable Activity custody,
replay, lifecycle scopes, observation, and separately placed Workers. Removing
those capabilities would solve the wrong problem. The problem is that the
common adoption path currently exposes too much assembly before a developer
can see a process move.

Hamsterdan's authoring experiments provide stronger evidence than a small demo.
Twenty-seven workflow-authoring experiments lowered higher-level values onto a
frozen Petrus runtime without one runtime change. The resulting candidate
layers retain a generic low-level net floor, function-shaped blocks, optional
sugar, static advice, deterministic composition refusals, and canonical
lowering. The companion experience study found substantial accidental topology
around shared control state while preserving every product rule in a simpler
control/fold/gate model. These are candidate designs, not promoted APIs, but
they establish that simplicity can be sought above the runtime.

Deer Workflow supplies the complementary adoption evidence: one generated file
can move immediately and be watched live, but its call stack replaces an
inspectable durable artifact. Petrus should pursue the immediacy without paying
that semantic price.

## Options Considered

- **Simplify the runtime until the common path becomes small.** Rejected. It
  would remove real capability and make advanced or long-lived applications
  reconstruct durability, ambiguity, replay, and authority outside Petrus.
- **Keep the current assembly experience because the runtime is necessarily
  powerful.** Rejected. Runtime depth does not require every adopter to compose
  every layer manually before first motion.
- **Build progressive disclosure over the existing runtime — chosen.** One
  simple path compiles to the same artifacts and permits deliberate descent to
  lower layers.

## Consequences

- Developer-experience proposals are judged by the complete authored journey,
  not by runtime feature deletion or source-line reduction alone.
- A one-file route must identify its History Store, Dispatch, durability, and
  observation behavior honestly. In-memory motion may be useful but must never
  be described as durable.
- The flagship complexity test is a Hamsterdan-scale flow, not only a toy
  sequence. It must retain domain decisions while moving clients, provider
  mechanics, and infrastructure assembly out of the flow architecture.
- Existing CV8, CV10, CV11–CV18 capabilities remain foundations. A candidate
  adoption Value may compose them without reopening their semantic decisions.
- This ruling does not select a concrete authoring syntax, runner owner,
  default storage profile, presentation protocol, or Agenticus convenience
  API. ES-056 owns that cohesive candidate map.
- No runtime, roadmap, or release implementation is authorized by this record.

## Review Trigger

Revisit if a Hamsterdan-scale executable probe demonstrates that the target
cannot be achieved without a specific kernel change, or if progressive
disclosure prevents an advanced author from expressing or inspecting behavior
that the current lower-level APIs support.
