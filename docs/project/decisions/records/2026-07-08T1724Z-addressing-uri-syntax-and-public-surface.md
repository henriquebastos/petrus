---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-06-25T1428Z-hermes-adr-0026-typed-net-uri-schemes-and-anchored-declarations.md
  - docs/project/decisions/records/2026-06-24T1129Z-hermes-adr-0023-netpath-is-node-address-subset-of-neturi.md
  - docs/project/decisions/records/2026-07-02T0847Z-hermes-adr-0028-runtime-history-addresses-are-for-tooling-not-execution.md
---

# Addressing: ASCII-canonical URIs, NetPath as the public surface, declarations internal

## Question

Three addressing OPENs in `net-schema.md`: (1) URI escaping/canonicalization
and whether `->` is canonical; (2) when public APIs use `NetPath` vs typed
`NetUri`; (3) how visible generated declaration URIs should be.

## Decision

- **ASCII-canonical URI syntax.** The canonical URI form is ASCII: typed
  schemes `place:/…`, `transition:/…`, `arc:/a->/b`, with `->` the **canonical**
  arc-endpoint spelling (not merely display) and reserved characters
  (`/ # : ? ->` and whitespace) percent-escaped within path segments. Unicode is
  not part of the canonical form. The full escaping table is a kernel-revealed
  detail; the principle (ASCII-canonical, reserved-char escaping, `->` canonical)
  is fixed [ADR 0026].
- **NetPath is the public node-addressing surface.** Public APIs accept and
  return `NetPath` (the schemeless, structured node address) as the primary type
  users read and write; typed `NetUri` is the canonical serialized/diagnostic
  form and is used where any-addressable-part (not just a node) must be named
  [ADR 0023]. A `NetPath` always has a `NetUri` form; APIs may accept either.
- **Declaration URIs are internal by default.** Generated declaration URIs
  (`transition:/x#handler`, `place:/p#initial`) are for bindings, diagnostics,
  and tooling — not a primary user-facing surface. They are addressable but not
  foregrounded in ergonomic APIs [ADR 0025, ADR 0028].

## Consequences

- `net-schema.md` three OPENs closed with the above.
- Escaping edge cases and the exact public-API type signatures remain
  kernel-revealed but are constrained by these principles.

## Review Trigger

Revisit when the kernel defines the escaping table or the public API surface and
an ASCII/`->`/NetPath-first choice proves ergonomically wrong in practice.
