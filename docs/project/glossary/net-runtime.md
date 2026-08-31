# Net runtime

The kernel runtime responsible for validating and instantiating net
definitions, maintaining markings, computing enabled firing
candidates, performing begin/end firing semantics, deriving timer
maturations, and integrating handler-projected effects. Policy timing,
wakeups, and activity dispatch belong to the driving runtime above it.
