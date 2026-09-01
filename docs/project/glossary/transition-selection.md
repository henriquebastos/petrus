# Transition Selection

The Instance-scoped policy boundary, outside the Petrinet Kernel and composed
per Instance by its Engine, that admits, ranks, and chooses at most one
enabled firing candidate — a transition under one specific Binding — to begin
within the `BeginCandidate` action class. The composed implementation is a
**Transition Selector**; the base contract promises no universal fairness
grain.

- Do not use for: the tokens one arc takes from one place for a binding —
  that is [Token Selection](token-selection.md).
- Avoid: Candidate Selection (former name), Scheduler (retired temporary
  vocabulary).
- Related: [Enabled firing candidate](enabled-firing-candidate.md),
  [Selected firing occurrence](selected-firing-occurrence.md)
- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
