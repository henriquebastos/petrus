# Engine

The live composition that creates or resumes and drives exactly one
Instance: one canonical History Store, Dispatch, writer fence, clock,
Candidate Selection, and advancement lane. It is not a fleet or
multi-Instance supervisor; Fabric connects Instances rather than
sharing their state.

- Related: [Petrinet Instance](petrinet-instance.md), [Driving runtime](driving-runtime.md), [Fabric](fabric.md)
