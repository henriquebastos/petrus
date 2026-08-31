# Activity

The Motus unit of Petri-agnostic imperative work executed by a Worker
for an impure handler: ordinary typed input in, external side effects
allowed, a typed result or terminal execution failure out. It never
receives a live `Instance`, marking, History, topology, or output-arc
contract.

Related: [Activity invocation](activity-invocation.md),
[Handler](handler.md), [Dispatch](dispatch.md)
