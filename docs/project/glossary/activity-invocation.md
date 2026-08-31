# Activity invocation

The immutable logical instruction prepared by a server-side handler
for one firing occurrence: activity binding reference, typed input,
resolved execution policy, correlation identity, and provider
idempotency identity. `ActivityRequested` records it before dispatch
and acts as the authoritative outbox.
