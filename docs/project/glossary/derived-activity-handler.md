# Derived Activity handler

The public Petri-aware `ActivityHandler` implementation that derives
ordinary `prepare` and `project` behavior from a typed Activity
definition and one transition's arc inscriptions, refusing missing,
ambiguous, reused, weighted, or unmatched typed shapes at composition.
Explicit Activity handlers remain the escape hatch for semantics the
net shape cannot derive.
