# Token Selection

The tokens one arc takes from one place for a firing binding — a
`(place, tokens)` pair, tokens in FIFO-scan order of admitted positions.

- Do not use for: choosing which enabled candidate begins — that is
  [Transition Selection](transition-selection.md).
- Avoid: Selection (bare), when the arc/policy level would be ambiguous.
- Related: [Head selection](head-selection.md), [Offer](offer.md)
- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
