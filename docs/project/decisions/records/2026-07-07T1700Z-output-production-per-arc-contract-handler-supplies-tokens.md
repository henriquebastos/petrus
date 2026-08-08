---
status: Decided
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-06-21T1717Z-hermes-adr-0017-arc-mode-applies-only-to-input-arcs.md
  - docs/project/decisions/records/2026-06-21T0842Z-hermes-adr-0010-no-handler-default-behavior-is-passthrough-only.md
  - docs/project/decisions/records/2026-07-07T1620Z-aggregate-token-type-single-type-per-token.md
  - docs/project/decisions/records/2026-07-07T1710Z-passthrough-identity-and-homogeneous-broadcast.md
---

# Output production: per-arc routing contract, handler supplies the tokens

## Question

[ADR 0017] says each output arc carries its own inscription (per-arc output),
departing from the Petrus oracle that deposits one merged token to all output
places. But the spec never defined *how* a produced token's data is derived.
This record concretizes the output model.

## Decision

- **Each output arc's inscription is a routing contract, not a token factory.**
  It names the token color/type the arc admits into its target place — a
  statically-checkable `{type, destination}` contract.
- **The handler supplies the actual output tokens**, keyed by destination place.
  At end firing the runtime deposits only handler-supplied tokens whose color and
  destination **match** an output arc's inscription; a token that matches no
  output arc is rejected.
- **Heterogeneous fan-out is native.** Because each arc is an independent
  contract and the handler emits per-destination tokens, one firing may deposit
  *different* payloads to different branches (e.g. an `ApprovalNotice` to
  `approved` and a `LedgerEntry` to `ledger`). One token, one type per deposit
  [DR aggregate-token-type].
- **No shape inference.** The runtime never derives output tokens from
  input/output shapes; shaping lives in the handler [ADR 0010]. The inscription
  constrains only *where* and *of what type* output may land.
- **When a transition declares no handler**, output follows the passthrough rule
  [DR passthrough-identity-and-homogeneous-broadcast], the only case where the
  runtime produces tokens without a handler.
- **The Petrus merged-token-to-all behavior is rejected** as the Impetus
  contract. It duplicates one merged payload to every output place (output-arc
  weight ignored) and cannot express heterogeneous fan-out.

This adopts velocitron's `ProduceTemplate` shape (output arc = routing contract;
handler returns `outputTokens: {place: [tokens]}`), which is the same per-arc
position [ADR 0017] already takes.

## Rationale

Forced by the input-side decisions: shaping lives in handlers, CEL is for pure
filters/guards only (never output), and tokens are one-type aggregates. The
engine therefore must not compute output tokens — the handler does — and the arc
is the contract that makes fan-out statically checkable. This matches velocitron,
minimizing upstream divergence, and gives heterogeneous fan-out that the Petrus
oracle cannot.

## Consequences

- The net schema's output inscription is a `{type, destination}` contract; the
  handler contract returns tokens keyed by destination; the runtime validates and
  deposits against the contracts.
- **Golden traces:** `fork_join` (transition `split`) and `awaiting_termination`
  (transition `begin`) pin oracle merged-token fan-out and must be regenerated or
  re-derived under this model; single-output fixtures stay valid. Add positive
  heterogeneous-fan-out fixtures that the oracle cannot produce. Tracked as
  follow-up.
- Output-arc weight semantics (upper-bound contract vs ignored) to finalize with
  the handler contract; Petrus ignores output weight, velocitron routes per
  handler token.

## Supersedes

Concretizes [ADR 0017]; does not supersede it. Explicitly rejects the Petrus
merged-token-to-all output as the Impetus contract.
