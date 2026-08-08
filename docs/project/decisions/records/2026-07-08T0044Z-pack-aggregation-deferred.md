---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-08T0043Z-unpack-stdlib-handler-projection.md
  - docs/project/decisions/records/2026-07-07T2119Z-passthrough-is-a-default-handler-color-routed.md
  - docs/project/decisions/records/2026-07-07T1620Z-aggregate-token-type-single-type-per-token.md
  - docs/project/decisions/records/2026-06-21T1417Z-hermes-adr-0012-separate-net-runtime-from-execution-runtime.md
---

# No stdlib `pack`; aggregation stays a user handler

## Question

Should there be a stdlib `pack` shaping handler that constructs an aggregate
token from several input tokens (the inverse of `unpack`
[DR unpack-stdlib-handler-projection]), letting AND-join and correlation join
combine without a user handler?

## Decision

**No.** `pack` is **not** part of the stdlib shaping-handler library. Aggregation
— constructing a new aggregate token from several inputs — is done by a **user
(or reusable-component) handler**, ordinary code at the binding layer. There is
no built-in the net leans on for construction.

This may be revisited **only if it becomes clearly, concretely necessary in the
future** — a high bar, not a default-someday.

## Rationale

Two reasons, the first decisive:

1. **Hidden expression language.** A stdlib `pack` — construction driven by a
   field mapping in or near the net — is exactly the drift the
   [DR passthrough-is-a-default-handler-color-routed] review trigger was written
   to catch ("watch for a hidden expression language past ~3 stdlib members").
   The trigger fired here, and the answer is no. The Navigator: keep this off the
   system unless a future need makes the direction really clear. `unpack`
   survives because it is pure *projection* (reads fields that already exist,
   not Turing-complete); `pack` is *construction*, the side that grows into a
   DSL.
2. **Layer coupling.** Pack is type construction — building a typed value
   requires invoking the aggregate type's constructor, which is binding/runtime
   knowledge. A stdlib `pack` in the pure net leaks construction into net
   semantics, against [ADR 0012] and library-not-framework.

## Consequences

- Aggregation remains fully expressible — as a user or reusable-component
  handler [ADR 0002]. Nothing is lost; only the *built-in* is refused.
- AND-join / correlation join (ES-004 TF-30/TF-35) keep their combine handler,
  now confirmed as the intended shape, not a tax.
- The stdlib shaping-handler family is capped in practice at `passthrough` +
  `unpack` unless the review trigger is deliberately reopened.

## Review Trigger

Reopen only on a clear, recurring, concrete need for handler-free aggregation
that cannot be met by a reusable-component handler — and only after re-examining
the hidden-expression-language risk head-on. Absent that, the answer stands.
