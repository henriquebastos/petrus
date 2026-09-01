# Scripted scenario

A DST schedule chosen by an author — or retained from a minimized
campaign failure — and replayed exactly through the World: submit
chosen inputs, run to a durability boundary, inject a fault, inspect the
recovered state.

- Use when: proving a known case, debugging, or pinning a found bug
  as a regression.
- Do not use for: seed-driven exploration of unchosen schedules —
  that is a [Campaign](campaign.md).
- Related: [World](world.md), [Durability boundary](durability-boundary.md)
- Detail: [deterministic-simulation-testing.md](../../process/deterministic-simulation-testing.md)
