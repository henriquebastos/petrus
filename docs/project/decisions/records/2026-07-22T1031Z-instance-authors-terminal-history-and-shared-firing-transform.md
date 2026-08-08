---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - ES-009 D11 clause 1 only, where the Absurd transaction-mode worker loop included the Impetus semantic append in the worker-held transaction
  - CV3 DS4 provisional 1's pending status on authority-side versus worker-side canonical terminal append
related:
  - docs/project/decisions/records/2026-07-15T0110Z-absurd-execution-substrate.md
  - docs/project/decisions/records/2026-07-22T0245Z-engine-is-one-live-instance-composition.md
---

# Instance authors terminal History and a shared history-independent firing transform

## Question

Who authors canonical Activity terminal facts after a Worker reports an
operational outcome, and should Direct and Activity completion continue through
separate record-carrying code or one shared firing transform independent of
History?

## Decision

Direct and Activity transitions share one Petri firing lifecycle and the same
begin/complete movement semantics. Their only completion difference is how the
completion projection is obtained: Direct completion uses the deterministic
projection, while Activity completion uses the accepted Activity outcome. The
Activity path additionally records request and outcome facts around that common
lifecycle.

A Worker produces only an operational terminal outcome report. It never appends
canonical semantic History directly. The one live Engine receives the report;
its Instance-side authority validates and accepts it and assigns canonical
semantic ordering and time where applicable. Instance remains the single
canonical History writer for `ActivityCompleted`, `ActivityFailed`, firing
movements and effects, and terminal firing facts.

This decision supersedes **only ES-009 D11 clause 1's worker-side semantic
append shape** in the 2026-07-15 “Adopt Absurd as CV3's execution-adapter
substrate” record: its transaction-mode loop said that `complete_run` and “the
Impetus semantic append” commit or vanish in the Worker-held transaction. It
also resolves CV3 DS4 provisional 1 in favor of the authority/Instance-side
canonical append. D11's Absurd selection, caller-provided transaction mode,
claim/handler/checkpoint/`complete_run` operational atomicity, doorbell,
reconciliation, concurrency, pinning, fallback, and every other clause remain
unchanged. Absurd task, run, claim, lease, and related operational state remain
distinct from canonical History.

Commission a bounded Technical Story to extract one shared
**history-independent firing transform** for Direct and Activity begin/complete.
The transform returns Petri movements and effects without constructing History
`Record` objects or depending on `impetus.history`. Instance converts those
effects into the byte-identical current canonical records, appends them with the
current atomic boundaries, and folds committed movements into live state.

“History-independent” names an implementation property. Do not call the
transform “pure firing”: `Direct` is the settled transition-completion term.
The extraction must not create separate Direct and Activity firing engines,
change lifecycle semantics, canonical authorship, record classes or
discriminators, payloads, ordering, replay bytes, or transaction behavior.

This record does not decide whether source-initiated Activity transitions are
legal. That restriction is separate and remains outside DEC-039.

## Rationale

One shared movement lifecycle preserves the Petri meaning that already unifies
Direct and Activity transitions while separating semantic calculation from
durable narration. Keeping History construction and append at Instance preserves
the single-writer invariant, canonical ordering, current acceptance/freeze
boundaries, and the operational-versus-semantic boundary around Workers and
Absurd.

History independence lets the Petrinet Kernel remain a leaf and makes the
firing semantics independently reusable without inventing a second lifecycle.
Routing the change as a bounded Technical Story keeps the approved direction
separate from implementation authority and requires byte-for-byte evidence
before the debt can close.

## Options Considered

- **Instance-side canonical append plus a shared history-independent transform
  — chosen.** Preserves one writer and one lifecycle while removing the
  Petrinet-to-History pressure.
- **Worker-side canonical append.** Rejected: it gives operational executors
  canonical semantic authorship and splits ordering, validation, and writer
  fate away from the one live Engine and Instance.
- **Keep record-carrying firing indefinitely.** Rejected as the direction:
  it leaves complete Petrinet firing semantics coupled to History. The
  implementation remains unchanged until the Technical Story passes its
  lifecycle and equivalence gates.
- **Separate Direct and Activity firing engines.** Rejected: projection origin
  does not create two Petri movement lifecycles.
- **Call the extraction “pure firing.”** Rejected because “Direct” already
  names transition completion and “history-independent” states the intended
  implementation property precisely.

## Consequences

- CV3 remains pending ratification as a whole, but its terminal-authorship
  question is no longer pending: CV3 DS4's authority-side implementation is
  the accepted canonical shape.
- Workers and Dispatch may durably manage operational outcomes, attempts,
  claims, leases, and recovery, but only Instance accepts those outcomes into
  semantic History.
- The firing-seam debt has an approved payment direction and a planned bounded
  Technical Story; it is not resolved or actively being paid by this record.
- Acceptance for the refactor must prove exact record sequence and encoded-byte
  equality, golden replay, backend transaction parity including PostgreSQL and
  Absurd recovery/atomicity, and unchanged Direct/Activity movement semantics.
- DEC-035 subsequently ruled per-Instance Candidate Selection semantics. This
  record did not decide them; the later ruling now governs.

## Review Trigger

Return to the Navigator if the extraction requires a new semantic abstraction
beyond Petri movements/effects, changes any History or transaction assertion,
cannot serve Direct and Activity through one lifecycle, weakens Instance's sole
canonical authorship, or makes source-initiated Activity legality necessary.
