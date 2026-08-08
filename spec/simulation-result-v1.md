# Simulation result schema 1

This document and `observation/simulation-result-v1.json` define the
language-neutral result of one bounded Petrus simulation. The recommended
filename extension is `.petrus-simulation.json`; the media type is
`application/json`.

## Strict document

The top-level object has exactly seven fields: `format`, `version`, `profile`,
`scenario`, `outcome`, `snapshot`, and `history`. `format` is exactly
`petrus-simulation-result`, `version` is the integer `1` (not a boolean or
string), and `profile` is exactly `implementation-free-v1`. Unknown fields,
duplicate JSON members, non-finite numbers, unsupported versions, and numeric
coercion are refused.

`scenario` has exactly `start_instant`, `initial_marking`, and `max_actions`.
The start instant is integer zero. Initial marking is the protocol-v1 ordered
place/token JSON shape; token order within a place is significant.
`max_actions` is a non-boolean integer from 1 through 256. `outcome` has exactly
`actions_applied` and `reason`; actions is a non-negative integer no greater
than `scenario.max_actions`, and reason is `rest` or `action_limit`.

`snapshot` is one unchanged observation-protocol-v1 snapshot. Let
`F = snapshot.frontier`. `history` is one unchanged complete protocol-v1
History envelope with the same protocol and Instance identity,
`after = 0`, `next = frontier = F`, and exactly `F` records at dense positions
`[0, F)`. Position zero is the matching `InstanceCreated`. The snapshot and
History describe the same disposable Engine after `actions_applied` actions.
All instants are in Petrus's integer virtual-time domain and creation starts at
zero.

## Implementation-free-v1 profile and action law

The producer accepts an application-owned canonical build and Python marking;
it never decodes either from JSON and never accepts an existing Engine,
History Store, Dispatch, sensor, provider, Activity declaration, or source
delivery. Python construction is trusted, but admission requires empty handler
and guard implementation maps, absent transition handlers, and only absent or
inline-CEL guards, arc filters, and completion. Named and anonymous
declarations are rejected rather than substituted.
Every arc weight is exact non-boolean integer `1`; each transition has at most
one selecting input arc and that arc must consume, plus at most one output arc;
and every
`Delay`/`Until` value is an exact non-boolean non-negative integer. Every
nonempty marking place must belong to the Net. Every queue item is exactly a
Token whose color is `null` or a nonempty exact string and agrees with a typed
place. Token data is strict-JSON detached before one fresh marking is built;
that frozen marking supplies both execution and the scenario projection.
Canonical definition projection, strict serialization, and all admission
checks succeed before Engine creation.

The producer creates a fresh in-memory History, simulated clock at zero, and
current Petrus Engine with conservative/default candidate selection. Each
`advance()` returning `ready=true` is exactly one applied action. A return with
`ready=false, waiting=false` yields `rest`. Reaching the exact caller cap yields
`action_limit` without another probe. Waiting, in-flight work, or Dispatch use
is an impossible-profile refusal. Completion changes status but never halts
advancement itself. Therefore `rest` does not mean completed, and
`action_limit` neither claims another action exists nor proves eventual rest.

## Fixed bounds

Before Engine creation: at most 128 places, 128 transitions, 512 arcs, 512
initial tokens, and 1,000,000 UTF-8 bytes in the strict-JSON initial token
projection; each CEL expression is at most 4,096 UTF-8 bytes and the serialized
canonical definition is at most 1,000,000 bytes. Admission multiplies initial
token count by the maximum number of input arcs incident on any place and
refuses a reachable survey bound above 10,000. Before each `advance()`, the
producer also sums current queue length for every input arc—including inhibit
arcs—and refuses above 10,000 scans. This may over-count color/CEL-rejected
tokens and is an intentional profile restriction. Together with consuming
selection and one output, retained token count cannot grow and every internal
pre/post-action survey stays under the admitted bound without changing Engine
semantics.
During execution: at most 256 actions, 4,096 retained current
tokens, 4,194,304 encoded retained-token bytes, 50,000 History records, and
4,194,304 encoded History-record bytes; retained state and History are checked
before execution and after every action. The deterministic serialized result is
at most 4,194,304 bytes. Exceeding a bound refuses the result rather than
truncating it.

The canonical serialization is UTF-8, keys sorted lexicographically, two-space
indentation, strict JSON numbers, and exactly one terminal newline. JSON member
order and insignificant whitespace are not semantic for other conforming
serializers.

The Python `simulate(...)` API returns these final bytes directly; there is no
public arbitrary-document serializer. The fixed exporter completes simulation
and serialization, writes and file-fsyncs a temporary, then commits with one
`os.replace`. Any exception before or during replace preserves the previous
destination. Once replace returns export succeeds; this profile does not claim
crash-durable directory-entry persistence.

## No executable meaning

This artifact is evidence, not a deployment, resumable Instance, Net-definition
file, sandbox claim, all-path analysis, or eventual-termination proof. A reader
may display recorded facts and unchanged protocol projections. It must not
execute CEL, recompute enabledness or status, run handlers or Activities,
deliver input, mutate state, or infer omitted implementations. The artifact
contains no executable implementations and gives no authority over a live
Engine.
