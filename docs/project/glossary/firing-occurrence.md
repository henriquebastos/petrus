# Firing occurrence

One durable semantic begin→terminal lifecycle for a firing Binding —
the correlation identity pairing its records in interleaved History,
spelled `FiringOccurrence` and correlated by the `occurrence` field.
It is not an operational retry: one impure occurrence produces one
stable Activity invocation, which Dispatch may try through several
operational Attempts.

- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
