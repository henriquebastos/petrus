# Lifecycle scope

The immutable durable identity `(name, generation)` that owns one
explicit generation of queued token occurrences and firing
occurrences. A scope opens canonically, closes with exact cleanup and
in-flight cancellation, or resets atomically by closing N and opening
N+1.
