---
status: Decided
raised: 2026-07-29
decided: 2026-07-29
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-28T1726Z-reusable-net-specifications-stamp-at-scopes.md
  - docs/project/decisions/records/2026-07-23T1739Z-correlated-inhibitors-use-explicit-binding-token-correlation.md
---

# libpetri is implementation prior art, not the Impetus runtime substrate

## Question

What role should debe/libpetri play for Impetus after a source-level comparison
of its Petri semantics, compiled executor, composition, Python binding,
verification, debugging, and multi-language conformance—and which apparent
feature gaps should enter current work?

## Decision

Retain libpetri as strong implementation and tooling prior art. Do not adopt it
as Impetus's runtime dependency, Petrinet Kernel dependency, general semantic
oracle, or current interoperability target.

Transpose techniques only through Impetus's canonical boundaries:

- a future compiled execution plan may derive disposable dense indices,
  reverse dependencies, dirty sets, and specializations from canonical `Net`;
  it never becomes semantic truth or durable state;
- the readable reference kernel and a shared semantic corpus remain the oracle
  for any optimized backend;
- structural analysis, conformance fixtures, and debugger/operator views derive
  from canonical `Net` and History and make their abstraction limits explicit;
- composition rewrites remain exhaustive, flatten to canonical `Net`, and do
  not merge Handler or Activity implementations;
- verifier architecture may be studied, but every Impetus proof relation must
  be rederived for Impetus semantics and return inconclusive/unknown outside
  its sound fragment.

Do not import libpetri event archives as History, environment-place injection
as ingress, process-local fresh names as durable identity, hard firing
deadlines, action-timeout fallback, transition-channel action composition,
cross-Instance place fusion, reset arcs, priority semantics, or variable
cardinality merely for parity.

Business-key correlation is already expressible by a pure Binding guard. The
Navigator separately commissioned a bounded design and implementation thread
because the current reference algorithm constructs the candidate cross product
before that guard rejects mismatches. That work may introduce a restricted
language-neutral equality declaration that prunes invalid Bindings before
construction and later supports indexing; it must preserve general guards and
must not impose one universal correlation field or hidden identity. Its exact
schema and implementation are owned by that thread's Ariad lifecycle, not
decided here.

Dynamic cardinality remains deferred. Impetus's arc weight covers fixed
`One`/`Exactly(n)` selection. `All` and `AtLeast(n)`-then-drain-all require a
concrete closed-batch process before consideration because current presence is
not evidence that all future members of a correlated business flow have
arrived.

## Rationale

libpetri validates several Impetus choices while solving a different problem.
It is a broad, fast, local executable CTPN toolchain with substantial analysis
and multi-language machinery. Impetus is a durable process substrate whose
authority is one canonical per-Instance History and whose external effects cross
Activity, Dispatch, and Worker custody. Adopting libpetri would retain nearly
all Impetus runtime layers while adding a translation boundary across divergent
arc, cardinality, timing, ingress, output, failure, and scheduling semantics.

The Navigator's learning progression clarified the useful separation:

- compilation pays static interpretation once and creates lookup/index
  structures; it does not change what a Net means and does not itself solve the
  combinatorial Binding cross product;
- correlation is a domain relationship first and an indexing opportunity
  second; the author already expresses arbitrary relationships through guards,
  while only a deliberately declared equality fragment can safely prune early;
- correlation answers *which* facts belong together and cardinality answers
  *how many*; neither proves that an open external producer has finished;
- tooling is the safest cumulative extraction path because it can remain a
  projection over the canonical model rather than widening runtime semantics.

## Options Considered

- **Use libpetri as the Python or Rust execution substrate.** Rejected because
  it lacks Impetus History, durable firing/activity recovery, source delivery,
  Worker custody, and Fabric, while imposing materially different semantics.
- **Use libpetri as the behavioral oracle.** Rejected except for a future
  explicitly named common subset; whole-runtime equivalence does not exist.
- **Match libpetri's Petri feature breadth now.** Rejected. Reset, dynamic
  cardinality, priorities, deadline intervals, and output trees need concrete
  Impetus pressure and independent semantic decisions.
- **Inspect arbitrary Python guards to discover correlation.** Rejected as
  fragile and non-portable. A specialization must be explicit and
  language-neutral.
- **Begin with tooling and preserve semantic feature questions separately.**
  Accepted; structural analysis and correlation have independent delegated
  threads and lifecycle ownership.

## Consequences

- The distilled libpetri reference is the durable source for comparisons,
  transposition candidates, Python DSL differences, and rejected imports.
- No current roadmap item acquires compilation or broad Petri-language parity.
- Analysis and correlation may progress independently without blocking one
  another; their threads own their own Ariad artifacts and checkpoints.
- A future compiler must support slow/reference fallback for new semantics so
  optimization never blocks language evolution.
- A future matrix or theorem tool must first establish that canonical output
  behavior has a fixed effect; output arc weight cannot be treated as
  production multiplicity.

## Review Trigger

Revisit the dependency/oracle disposition only if libpetri gains a durable
History/effect protocol compatible with Impetus or a concrete consumer requires
a named common interchange profile. Revisit compilation when profiles show
candidate discovery or repeated structural interpretation is material. Revisit
dynamic cardinality when a maintained closed-batch process cannot be modeled
truthfully with fixed weights, explicit closure evidence, or aggregate tokens.
