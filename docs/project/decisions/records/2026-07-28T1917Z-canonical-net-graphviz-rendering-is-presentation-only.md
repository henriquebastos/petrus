---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - Navigator
related:
  - CV7
---

# Canonical-Net Graphviz rendering is presentation only

## Question

Where should a minimal inspectable net renderer live, what value should it
accept, and which details may it derive without changing Petri semantics?

## Decision

`impetus.petrinet.dot` accepts the canonical `Net`. DSL callers pass
`BuiltNet.net`; `Net` gains no rendering method. `to_dot()` deterministically
assembles DOT with only the standard library. `render()` writes DOT directly or
uses the local Graphviz `dot` executable for SVG, PNG, and PDF.

Dark/light styling, top-down/left-right layout, optional marking counts, and
first-segment scope clusters are presentation. They do not compute enabledness,
expose token data, modify the net, or imply persisted subnet/composition
semantics. The renderer queries the arc's semantic predicates (`is_consume`,
`is_read`, and `is_inhibit`) rather than coupling presentation to `ArcMode`.
Structural source transitions are marked as `source`, which identifies ingress
without claiming one universal start. Node names use 14-point bold primary text
and color/declaration metadata uses 9-point regular secondary text. Graphviz
HTML-like labels carry that hierarchy with escaped dynamic content; other DOT
attributes remain quoted. Source transitions use a heavier dashed outline in
the ordinary transition color. Anonymous callable declarations may retain the
callable's `__name__` as an optional display hint, shown in concise labels and
identified as anonymous in tooltips. The hint is explicitly non-semantic: it
does not affect equality, hashing, declaration URIs, or runtime binding.

## Rationale

Canonical `Net` is the complete language-neutral topology boundary. Rendering
that value keeps visualization reusable by every authoring route and prevents
Python implementation maps from becoming accidental graph semantics. Direct
DOT assembly preserves a small deterministic source boundary; local Graphviz
keeps rendering inspectable and offline.

## Options Considered

- `Net.render()` was rejected because presentation is not a `Net` semantic.
- Accepting `BuiltNet` was rejected because handler and guard implementations
  are unnecessary; canonical declarations already contain the useful detail.
- A Python Graphviz package or network renderer was rejected because neither
  is needed for deterministic DOT plus a local process adapter.

## Consequences

Future overlays remain separate presentation inputs. Visual grouping must not
be read back as composition. Any interactive simulation, runtime History
overlay, enabledness highlighting, or generalized theme system requires its own
evidence and decision rather than expansion of this boundary.

## Review Trigger

Revisit only if a concrete editor or observation-plane consumer demonstrates
that deterministic DOT plus local Graphviz cannot carry its required
presentation.
