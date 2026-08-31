# Clock watermark

The per-Instance virtual clock: the driver-assigned, monotonically
non-decreasing instant of the latest appended History record. "Now"
for enablement — live and during replay — is the clock watermark; the
net runtime never reads a wall clock.

- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
