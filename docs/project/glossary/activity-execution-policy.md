# Activity execution policy

The immutable policy frozen into one Activity invocation: one Attempt
by default, with opt-in bounded deterministic backoff, renewable
heartbeat timeout, per-Attempt start-to-close, and aggregate
schedule-to-close. A provider must refuse deadline fields it cannot
enforce soundly.

- Detail: [spec/handler-contract.md](../../../spec/handler-contract.md)
