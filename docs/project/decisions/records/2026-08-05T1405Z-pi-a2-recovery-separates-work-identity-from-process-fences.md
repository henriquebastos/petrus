---
status: Decided
raised: 2026-08-05
decided: 2026-08-05
deciders:
  - Driver recommendation, accepted under project checkpoint policy
supersedes:
related:
  - docs/project/roadmap/cv16-agenticus-composable-agent-infrastructure/index.md
  - docs/project/decisions/records/2026-08-05T0923Z-net-owned-pi-loop-mirrors-a-bounded-public-seam.md
---

# Pi A2 recovery separates stable work identity from process fences

## Question

How can a crash-restarted host reuse Pi native A2 without blindly repeating an
ambiguous paid provider operation, while still allowing a settled operation to
replay after its prior Attachment, grant, and Connection-state coordinates have
ceased to exist?

## Decision

Petrus places a durable lookup-first boundary around `PiRuntimeAdapter`.
`PiRecoveredRuntime` writes one process-fenced SQLite operation row before the
adapter may start. The row contains only a versioned hash of stable logical
work identity, secret-free Episode and Turn identities, terminal lifecycle
facts, opaque output and Continuation references, cleanup evidence, and host
acknowledgement state.

Any `executing` row found by a new owner is settled `indeterminate` before new
dispatch. It is never redispatched and never repaired by mining orphan output
or native-session storage. A terminal row with the same stable identity replays
without touching the new process's adapter, Connection custody, Attachment,
grant, gateway, or provider. Changed stable input conflicts.

Stable work identity includes the Episode, Turn, prompt digest, installation
Connection identity and account fingerprint, selected provider/model/topology,
and outer Continuation identity and reference digest. It deliberately excludes
Connection state/authority epochs and Attachment/grant epochs. Those are
process-scoped fences: a future host composition must persist them for cleanup
and reconstruction, but requiring them to match a dead process would make safe
terminal replay impossible.

The wrapper durably settles a result before `wait()` returns. A secret-free
local adapter receipt also lets `close()` freeze a naturally completed result
when the host closes before observing it. If cancellation closes without any
receipt, the operation settles `close-indeterminate`. Lost SQLite
acknowledgements are retried against immutable facts.

Host acknowledgement advances a contiguous settlement watermark. The
watermark permits eviction only of closed process-local adapter handles;
durable rows remain so a late redelivery cannot repeat provider work.

This contract is at-most-once per operation identity, not exactly-once external
provider execution.

## Rationale

The adapter's single-flight map prevents duplicate work only while one process
lives. A crash after an operation starts and before terminal History still
leaves provider outcome ambiguous. Persisting intent before dispatch and
refusing ambiguous restart is the smallest truthful safety improvement.

Using the same fingerprint for logical work and ephemeral execution fences
would reject every legitimate post-crash replay. Conversely, ignoring stable
Connection, model, prompt, or Continuation identity would alias different work.
The two-level identity keeps those responsibilities distinct.

## Options Considered

- **Blindly call Pi again after restart.** Rejected because the first provider
  turn or tool effects may already have happened.
- **Promote orphan output or session blobs during recovery.** Rejected because
  they may be an unadmitted Episode delta without a complete terminal fact.
- **Include prior Attachment, grant, and Connection epochs in duplicate
  identity.** Rejected because those coordinates cannot remain current in a
  reconstructed host and are not required to replay a frozen result.
- **Use `AgentNetRunner` recovery.** Rejected because it is the distinct
  Agent-as-a-Net A5 Program/Hands/Continuation topology, not Pi native A2.
- **Persist stable intent, freeze terminal refs, and classify ambiguity —
  chosen.** This advances host safety without inventing provider reconciliation.

## Consequences

- A supported Pi A2 host factory must consult durable operation state before
  creating fresh authority, territory, Attachment, grant, or gateway state.
- The host factory still has to own durable process-fence coordinates,
  output/Continuation body custody, partial-construction rollback, and verified
  DS2/Attachment/Motus teardown.
- A crash before terminal settlement can sacrifice a completed provider result
  to `indeterminate`; safety takes precedence over speculative recovery.
- The SQLite ledger is one process-fenced writer with owned private paths. It
  retains terminal rows even after process-local receipt eviction.

## Review Trigger

Revisit when a provider offers an authenticated operation-result lookup, when
durable row retention needs compaction, or when the A2 host factory can atomically
freeze body and Continuation custody with the terminal operation fact.
