---
status: Decided
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-07T2119Z-passthrough-is-a-default-handler-color-routed.md
  - docs/project/decisions/records/2026-06-23T0312Z-hermes-adr-0021-schema-declares-guard-and-handler-symbols.md
---

# Permissive flow defaults: anything is allowed, then shape down

> **Amended 2026-07-27** by [DR
> place-colors-compile-to-effective-arc-inscriptions]: places remain untyped by
> default but may declare one nominal color as an authoring default, compiled
> once onto otherwise-untyped incident arcs. Explicit arc colors continue to
> narrow heterogeneous places. Every other permissive-flow clause stands.

## Question

The ES-004 re-evaluation surfaced a strictness question: must places declare
accepted colors, must arcs declare types, is a consumed token that matches no
output arc an error, and are sink transitions legal? More generally: is the
net strict by default and loosened by annotation, or permissive by default and
narrowed by annotation?

## Decision

**Permissive by default; types, filters, weights, and guards are narrowing
annotations — "anything is allowed, then shape down."**

- **Places are untyped by default.** A place can hold tokens of any type. It
  may declare one nominal color as an optional authoring default, not a duty.
- **Authored arc inscriptions are untyped by default.** A place color supplies
  an otherwise-untyped incident arc's effective color at flattening. An arc
  still untyped afterwards admits any token; an explicit arc color narrows an
  untyped place's flow, and a filter narrows further.
- **Leftover consumption is allowed.** A consumed token that no output arc
  admits is simply consumed — not a validation error, not a runtime error.
- **Sink transitions are legal.** A transition with zero output arcs consumes
  and produces nothing — the explicit, visible way to end a flow.
- **Accumulator places are legal.** A place with no outgoing arcs may receive
  tokens indefinitely (e.g. a counter: each firing deposits one more token;
  the runtime or a projection sums them later).
- **Enforcement posture: validation run, not static typing.** Correctness is
  checked when a net instance is built — resolve the flattened net, validate
  bindings, run the instantiation-time validation pass ("whatever is declared
  on the net must have embodiment through code" [ADR 0021]). Errors surface
  early at instance build, not via a static type system over the schema.
  Where untyped flow weakens what tooling can prove, validators MAY warn;
  adding types restores the proofs.

## Rationale

The Navigator: "This is not a pure Petri net environment — it is a Petri net
structure to allow a runtime to work. I don't want to assume what people want
to do with the runtime." Strict defaults force users to set everything
explicitly on all arcs and re-introduce the if/else programming the net is
supposed to replace. Permissive defaults mean things just flow; users shape
the flow down with types, filters, weights, and guards where it matters — one
uniform mechanism instead of special cases. The validation-run posture is
Petrus production practice ("it works quite well" for missing handlers/guards)
rather than an unproven static-analysis ambition.

## Consequences

- `spec/net-schema.md` places/inscriptions sections amended; CONTEXT.md
  updated.
- Dropping tokens silently by *accident* is still discouraged style — the
  sink transition is the idiomatic explicit drop — but the runtime does not
  police it.
- Static-analyzability trade-off is accepted and noted for the velocitron
  alignment conversation (their `{type, destination}` contracts lean
  strict-by-default).
- ES-004 arguable placements 1 and 2 are resolved by this record together
  with [DR passthrough-is-a-default-handler-color-routed].

## Review Trigger

If accidental token loss becomes a recurring debugging pain in practice,
revisit whether validators should warn (never error) on unroutable
consumption.
