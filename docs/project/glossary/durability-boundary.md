# Durability boundary

The edge of one atomic durable step — a named production boundary where a
DST schedule may stop, fault, crash, or resume, each carrying a required
durable fact and a recovery obligation. Faults land only on boundaries,
never inside a step, because any real crash instant inside an atomic step is
observationally equal to a boundary outcome after reload.

- Avoid: durable cut, semantic cut (former names; "cut" remains the shipped
  artifact and code spelling).
- Related: [Fault](fault.md)
- Detail: [deterministic-simulation-testing.md](../../process/deterministic-simulation-testing.md)
