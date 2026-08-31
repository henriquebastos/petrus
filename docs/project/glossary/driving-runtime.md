# Driving runtime

The coordination layer that drives an Instance from above through the
firing-occurrence seam: applying composable policy to safe whole
Actions, beginning selected occurrences, dispatching Activity
invocations, accepting results and deliveries, and advancing recorded
time. Mutation of one `Instance` is serialized; activities may run
concurrently outside that writer.

- Related: [Engine](engine.md)
- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
