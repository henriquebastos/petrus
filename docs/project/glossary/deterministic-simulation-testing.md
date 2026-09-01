# Deterministic Simulation Testing

Petrus's evidence program, abbreviated DST: a bounded, serializable
interpreter drives the production doors (Engine, Instance,
HistoryStore, Dispatch) under a controlled schedule, scripted
collaborator outcomes, and faults placed only at named durability boundaries,
with independent checkers judging observable production facts. One
World serves two drivers: scripted scenarios prove known cases;
campaigns hunt unknown ones.

- Do not use for: a proof of correctness or a second engine — DST is
  bounded evidence over production code.
- Related: [World](world.md), [Scripted scenario](scripted-scenario.md),
  [Campaign](campaign.md)
- Detail: [deterministic-simulation-testing.md](../../process/deterministic-simulation-testing.md)
