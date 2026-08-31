# Activity attempt

One operational try by a Worker to execute an Activity invocation,
with identity, lease epoch, deadline, renewal, expiry, and
reassignment owned by Dispatch. Attempts remain outside canonical
History; exhausting the frozen execution policy produces the canonical
`ActivityFailed` terminal fact.
