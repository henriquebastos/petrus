---
status: Decided
raised: 2026-08-05
decided: 2026-08-05
deciders:
  - Driver recommendation, accepted under project checkpoint policy
supersedes:
related:
  - CV16.DS10
---

# The Net-owned Pi loop mirrors a bounded public model-phase seam

## Question

How can CV16.DS10 replace Pi 0.83.0's core loop with Impetus structure without
copying private upstream implementation, changing the qualified model/Hands
body, or making either Agenticus Thread or Impetus History falsely authoritative
for the other's state?

## Decision

The binding `agent-as-net.a5.local` profile invokes one model phase through
Pi's public provider/message APIs, stops before tool execution, and lets an
explicit Impetus Net own repetition and ordered tool dispatch. The untouched
public `runAgentLoop` remains the behavioral oracle; no private Pi function or
source block is copied.

The version-1 mirror is deliberately bounded to the public behavior exercised
by the qualified profile:

1. build each provider phase from the system prompt, public `convertToLlm`
   result, ordered messages, and exact Hands tool schemas;
2. retain the final assistant message returned by the provider stream;
3. classify `error` and `aborted` before inspecting tool calls;
4. discover tool proposals from assistant `toolCall` content blocks rather
   than inferring them from the stop reason;
5. reject every proposed call after a `length` stop without executing one, and
   feed ordered error results back to the next model phase;
6. project each settled Hands result into Pi's public `ToolResultMessage`
   shape, with deterministic tests normalizing timestamps;
7. execute tool batches sequentially in assistant-source order and stop after
   the current settled call when cancellation becomes visible;
8. render unknown, blocked, or failed tools as ordinary model-facing error
   results rather than escaping the loop; and
9. treat provider failure as the terminal assistant fact, without implicit
   retry, compaction, or a second synthetic provider message.

The static Program declares `ProgramOwnership.NET` and does not claim steering
or evaluation seams. Steering queues, follow-up queues, parallel batches, and
mid-Episode grant changes are excluded from version 1 because the binding
profile and its oracle do not exercise them.

Impetus History is canonical for loop progression. Its JSON-safe tokens may
carry Episode/Turn identities, phase ordinals, opaque output/Continuation
references, assistant digests, bounded tool proposals, model-facing result
projections, grant epochs, and terminal codes. It never carries credentials,
transcript bytes, or raw provider state. Agenticus custody owns transcript
bytes and Continuation payloads; Agenticus Thread owns Episode, Turn, and
Continuation lineage. A runner initializes the Net once from Thread and then
projects committed Net facts back into Thread idempotently; it never consults
Thread as Engine scheduling authority.

One model phase and each Hands call are separate Activities. Pure Net handlers
classify and route their settled values. Host/Attachment policy opens the exact
grant before execution, and Hands remains the enforcing authority.

## Rationale

Pi's public package exports provider streaming, model/message/tool types, and
conversion/validation boundaries, but its exact one-phase bookkeeping and tool
execution functions are private. Reusing `runAgentLoop` would leave the old
heart in control; copying its private loop would create a fork. Reconstructing
the bounded public behavior as Net structure changes only loop ownership while
keeping the accepted provider/model and Agenticus Hands body.

Separate model and Hands Activities make the canonical process facts visible
and make ambiguity local to one recorded effect. The split custody boundary
keeps append-only History useful for replay without turning it into a transcript
or credential store.

## Options Considered

- **Wrap one complete `runAgentLoop` call in a Net Activity.** Rejected because
  Pi would still own the model/tool loop and the Net would only decorate it.
- **Copy Pi's private `runLoop`.** Rejected because that creates an upstream
  fork and obscures which behavior is controlled.
- **Add a Pi fork exposing private phase helpers.** Rejected for the binding
  profile because existing public provider/message APIs are sufficient.
- **Use public one-phase APIs plus explicit Net structure — chosen.** This is
  the smallest implementation that actually transfers loop ownership.

## Consequences

- The untouched full loop and one-turn helper provide deterministic golden
  oracles; intentional differences must be recorded rather than normalized
  away.
- Engine normally redispatches a recorded in-flight Activity on resume. The
  Net-owned runner must inspect in-flight model/Hands work before its first
  `advance()` and settle it `indeterminate` with zero redispatch.
- Quiescent markings are resumable; version 1 makes no provider-side
  reconciliation claim for ambiguous effects.
- The Pi application-owned A5 recovery debt's early trigger is reached. DS10
  must record the classification slice it pays while leaving broader provider
  reconciliation for DS11.

## Review Trigger

Revisit when a supported profile needs steering, follow-up queues, parallel
tools, dynamic grants, or provider-side reconciliation, or when upstream Pi
publishes a stable one-phase loop primitive whose behavior can replace the
bounded mirror.
