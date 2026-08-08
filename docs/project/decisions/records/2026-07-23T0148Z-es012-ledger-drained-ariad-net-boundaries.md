---
status: Decided
raised: 2026-07-12
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - ES-012 D2's unresolved choice between a canonical join field and a chip parameter
  - ES-010's level-triggered "cadences = enabledness" mapping
  - the ariadnet probe's consume-the-story checkpoint parking hypothesis
  - treating either ariadnet or the overnight Absurd/ZeroMQ spikes' provisional implementation choices as adopted conventions
related:
  - docs/project/decisions/records/2026-07-22T2147Z-cv3-ratified-runtime-convergence-routed.md
---

# ES-012's ledger is drained into bounded Ariad-net design

## Question

Which findings from the digest and throwaway ariadnet experiments should shape
the future Ariad net, and which provisional implementation and transport choices
should remain evidence rather than become doctrine? Does resolving those
questions close ES-012 and remove its gate from CV4?

## Decision

Close and archive ES-012 after draining its five remaining design rows and the
overnight residuals as follows.

### Correlation is configured structure, not new kernel semantics

Correlation belongs in ordinary Net coordination structure. A reusable
component or chip may accept a correlation key as configuration and instantiate
an ordinary, visible pure guard in the resulting Net. Existing Binding and guard
resolution then determine compatible candidates.

Do not add a dedicated Petrinet `join` field or new kernel semantic. The
experimental `join_on` helper demonstrates the need but is not adopted as the
canonical public API. A future component interface may choose its own honest
configuration spelling while producing inspectable Net structure.

### A cadence pays for an explicit edge

A cadence is a small stateful Net pattern whose edge produces enabledness. Its
state may be a consumed counter or control token. A cadence is therefore not
raw level-triggered enabledness, and the Petrinet Kernel gains no new
edge-trigger primitive. The ariadnet livelock result is retained as evidence
for why the pattern must represent the edge explicitly.

### Story content and checkpoint control remain separate

A story awaiting judgment stays in the Narrative Field, visible and able to
continue thickening. A separate gate/control token records checkpoint phase and
story identity. Promotion or archive may later consume the story; pause may
release control state while leaving the story present. Temporary routing state
does not belong in the story payload, and the probe's consume-the-story parking
shape is rejected as doctrine.

### Marking coordinates; the Story Desk narrates

Instance marking and canonical History own coordination truth. The Story Desk
owns narrative content. Tokens carry identifiers or references, and handlers
project between those layers. Restart reconstructs coordination from canonical
state without rewriting or re-deciding narrative work.

The current evidence does not prove reconciliation for documents edited outside
the Engine, reusable chip packaging, or generated views replacing manually
edited documents. Out-of-band document edits require a future identified
ingress/reconciliation design; documents do not become a competing coordination
authority by default.

### Only bounded ariadnet findings carry forward

Carry forward these findings:

- cadence state is coordination state;
- crash/replay preserves the marking–narrative ownership split;
- N-way judgment gates work through typed verdicts;
- reusable checkpoints need a correlation-key parameter; and
- invalid verdicts fail loudly before becoming routable tokens.

Reset-at-parking, park-by-consume, correlation guard spelling, and component
parameter structure are governed by the preceding decisions rather than
independently ratified. Do not promote the probe's exact filesystem Story Desk,
first-line string parsing, completion predicate, transition naming as scheduling
policy, token-dropping broken lens, or a universal rule that rationale belongs in
canonical History. Rationale and conversation-content placement remain part of
DEC-027's session/transcript boundary and are not decided here.

### Overnight method and transport residue remains evidence

The evidence-clearing fork remains closed unratified under D1. The Absurd
harness layout and latency methodology remain experiment evidence. ZeroMQ
ROUTER/DEALER, high-water-mark, IPC-limit, and WebSocket findings remain
transport evidence for future attach/client work. History replay over ZeroMQ is
deferred until snapshot-plus-tail replay performance becomes Delivery work;
first-class `ws://` status is deferred to future attach/client work where
packaging is material.

The Q7 timeline proposal remains historical evidence; its obsolete “CV3
selection pending” framing is not current doctrine. Authority, capability,
worker-side terminal append, and compatibility claims already superseded by
DEC-034 through DEC-040 and DEC-020 retire only in those decisions' exact
scopes. No experiment-specific mechanism becomes a project-wide convention by
this disposition.

## Rationale

The experiments established useful semantic boundaries but were intentionally
throwaway implementations. Promoting their helper spellings or filesystem and
transport details would turn examples into architecture. The selected shape
keeps the Petrinet Kernel small: ordinary guards and explicit state express the
coordination, while reusable construction may package those patterns without
adding hidden kernel concepts.

Keeping story content in the Narrative Field and separate checkpoint control in
the marking preserves both anthropocentric visibility and deterministic replay.
It also makes the unresolved out-of-band edit problem explicit instead of
quietly granting documents a second source-of-truth role.

## Options Considered

- **Adopt the experimental helpers and parking shape wholesale.** Rejected:
  `join_on`, consume-the-story parking, parsing, and filesystem choices are
  local scaffolding, not demonstrated universal contracts.
- **Dispose only the two CV4-blocking rows.** Rejected: leaving the remaining
  provisional list open would keep ES-012 active without a live question that
  belongs there.
- **Promote bounded semantic findings and retire/defer the mechanism residue —
  chosen.** This preserves what the experiments taught without freezing their
  implementation.

## Consequences

- ES-012's learning and decision ledger are complete; the story is Archived.
- ES-010 carries the settled correlation, cadence, checkpoint, and
  coordination/narrative boundaries while remaining an active design-first
  exploration.
- CV4 no longer waits on ES-012 D2–D5 or D8. It still waits on DEC-027 and on
  future client/attach work before slicing.
- Reusable component/chip API design, document ingress/reconciliation, and the
  exact rationale/session boundary remain future work rather than inferred
  rulings.
- Digest and ariadnet remain executable evidence. Their current APIs are not
  promoted into production by this decision.

## Review Trigger

Revisit the kernel posture only if a concrete designed Net cannot express its
correlation or cadence semantics through ordinary guards and explicit state.
Revisit document reconciliation when an identified external editor must update
narrative artifacts concurrently with a running Engine. Route session and
transcript placement through DEC-027 rather than reopening this ledger.
