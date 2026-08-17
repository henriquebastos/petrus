# DST scenario version 1

**Status:** Internal test contract. This is not a public Petrus package or
hosted-simulation API.

This document specifies the strict, portable replay artifact for the
`engine-coordinator-v1` deterministic simulation testing profile defined by
the [DST correctness owner](deterministic-simulation-testing.md). The Python
contract and the first narrow replay application live in
[`tests/dst/replay.py`](../../tests/dst/replay.py).

## Identity and evolution

An artifact is a strict JSON object with these pins:

- `format`: exactly `petrus-dst-scenario`;
- `version`: exact integer `1`, never a boolean;
- `profile`: exactly `engine-coordinator-v1`; and
- `scenario_id`: a non-empty fixture or generated-scenario identity.

Version 1 rejects duplicate keys, non-finite numbers, unknown fields, missing
fields, implicit type coercion, unknown event/fault/property values, non-dense
schedule positions, invalid fault/cut pairs, and values outside their declared
or profile ceilings. A new field, event kind, fault kind, changed
interpretation, or widened profile ceiling requires an explicit compatibility
decision and a version or profile change. A new application profile may be
registered under the same scenario profile when it preserves this envelope.

DS2's proposed generic cross-project World/profile protocol does not preserve
this envelope: it adds normalized application commands, opaque runtime
generations, scheduled follow-up proposals, checker manifests, and explicit
abrupt-drop semantics. It therefore cannot be represented as another version 1
application profile. The current `engine-coordinator-v1` proof remains
replayable unchanged; any generic artifact has a new explicit format or version
and separately pinned test-kit API compatibility.

The artifact is data only. JSON values may contain null, booleans, strict
numbers, strings, arrays, and string-keyed objects. It cannot contain a Python
callable, closure, Engine, HistoryStore, Dispatch, provider client, credential,
file handle, or another live object. `application.profile` locates fresh
repository-owned construction code and `application.definition_digest`
prevents that code from silently changing beneath a retained fixture.

## Authoring is executable; replay is data

This artifact is the expanded replay and failure-retention format, not the
primary human authoring language. DS2 scenarios are ordinary pytest programs
over a test-owned `World` composition root and an imperative `Timeline`
facade. Authors may use Python control flow, helpers, local values, and pytest
assertions to tell a complex story. Every operation that can change simulated
execution must still cross the Timeline, which records its normalized event,
fault activation, logical ordering, bound consumption, disposition, and
observation into this strict-data shape.

The Timeline may provide debugger-like, bounded `run_until` checkpoints. The
authoring predicate or callback is never serialized: the journal expands the
individual drive/events that actually occurred and records the named
checkpoint observation. Replay consumes those expanded choices directly and
does not execute the originating pytest scenario, callback, or PRNG.

The World owns deterministic time, identities, ordering, scripted external
truth, and construction of the real production runtime. A simulated process
crash discards every runtime-generation object and rebuilds through production
load/reconcile doors; only strict initial configuration, modeled external
facts, and the normalized journal may survive or reconstruct the test world.
Application projects may wrap the generic Timeline in domain verbs, but those
verbs must lower to Petrus-owned normalized events rather than importing
application policy into Petrus.

## Top-level shape

| Field | Exact shape and meaning |
| --- | --- |
| `origin` | Seed, 40-hex Petrus commit, runtime identity, unique dependency identities, originating property id, and shrink lineage. These are provenance, not an instruction to install or checkout automatically. |
| `application` | Non-empty registered profile plus `sha256:<64 lowercase hex>` definition digest. No implementation object is serialized. |
| `limits` | Every profile resource ceiling, spelled explicitly in the artifact. Values may narrow but never widen the profile ceilings. |
| `initial` | Supplied Instance identity, initial logical instant, and strict marking entries. Each place appears at most once. |
| `schedule` | One to 512 dense zero-based steps. Every step contains exactly `position`, `event`, `faults`, and `expect`. |
| `expected` | Final disposition, exact History record-type sequence, canonical snapshot, profile observations, and unique passing property checks including `origin.property`. |

### Origin

`origin` has exactly:

```json
{
  "seed": 1729,
  "petrus_commit": "<40 lowercase hex>",
  "runtime": {"implementation": "CPython", "version": "3.14.7"},
  "dependencies": [{"name": "petrus", "version": "0.0.0"}],
  "property": "S4-terminal-before-projection",
  "shrink": {"parent_scenario_id": null, "steps": 0}
}
```

Property ids are the closed `S1`–`S8` and `L1` vocabulary in the correctness
owner. `parent_scenario_id` is null for an unshrunk/root scenario; a minimized
derivative names its immediate parent and increments `steps`. The expanded
schedule remains authoritative even if a future generator cannot reproduce it
from the retained seed.

### Limits

The object always names these exact non-boolean integers:

`events`, `faults`, `crash_restart_pairs`, `actions_per_drive`,
`total_actions`, `logical_instant`, `history_records`,
`history_payload_bytes`, `retained_tokens`, `retained_token_bytes`,
`pending_outcomes`, `in_flight_activities`, `artifact_bytes`, and
`watchdog_seconds`.

Their maxima are those in the
[profile bounds](deterministic-simulation-testing.md#profile-bounds). The
loader validates static admission constraints. A replay profile enforces the
dynamic limits it can reach; DS2's general harness must enforce every limit at
every event and report `bounded_exhaustion` or `harness_failure` exactly as the
correctness owner specifies.

### Portable tokens and markings

A token is exactly `{"color": string-or-null, "data": JSON-value}`. A
marking entry is exactly `{"place": non-empty-string, "tokens":
non-empty-token-array}`. Markings are arrays so artifact order stays visible;
the loader refuses duplicate places instead of allowing last-write-wins
collapse.

## Closed event vocabulary

Each `event` is one discriminated strict object:

| `kind` | Additional exact fields |
| --- | --- |
| `deliver` | `source`, non-empty `tokens`, and string-or-null `identity` |
| `drive` | positive `max_actions`, at most 256 and the artifact's `actions_per_drive` |
| `advance_time` | non-negative `instant`, within the artifact's logical-time ceiling |
| `dispatch_terminal` | positive `occurrence`, `outcome` (`completed` or `failed`), and strict JSON `value` |
| `close_scope` | `scope`: exact non-empty `name` and positive integer `generation` |
| `reset_scope` | `scope`: exact non-empty `name` and positive integer `generation` |
| `crash` | one named durable `cut` |
| `restart` | no additional fields |
| `begin_fair` | no additional fields |

The general vocabulary maps to the production doors named by the correctness
owner. The DS1 `projection-recovery-v1` runner deliberately implements only
`drive`, `dispatch_terminal`, `crash`, and `restart`; it refuses other valid
events rather than pretending to be the DS2 scheduler.

## Fault entries and cuts

Each fault has exactly `kind`, `cut`, positive bounded `count`, and
string-or-null `error`. The closed kinds are:

- `history_refuse`, `history_commit_refuse`;
- `dispatch_refuse`, `dispatch_delay`, `dispatch_duplicate`,
  `dispatch_conflict`;
- `ack_refuse`, `process_crash`, `history_unreadable`; and
- `projection_raise`, the application-profile fault which raises from
  deterministic projection after `activity_terminal_frozen`.

Only `projection_raise` carries a non-null `error`. Every other fault requires
null. The allowed kind/cut combinations are exactly those in
[`ScenarioFault.allowed_cut`](../../tests/dst/replay.py); the source and
correctness table change together. Counts across a schedule may not exceed
`limits.faults`. Crash and restart events pair and alternate from a live
initial runtime.

`projection_raise` is not a generic fault adapter or a claim that application
code is simulated. It selects a registered, deterministic test-application
projection that raises the recorded message at the production handler door.

## Step and final expectations

`expect` has exactly:

- `disposition`: `applied`, `idempotent`, `refused_expected`,
  `quarantined`, `bounded_exhaustion`, or `harness_failure`;
- `history_frontier`: the exact non-negative durable record count after the
  step; and
- `error`: the exact expected error string or null.

History frontiers are monotone and the final frontier equals the length of
`expected.history_record_types`.

The final `expected.snapshot` has exact canonical `marking`, `status`,
`watermark`, and integer `in_flight` identities. `observations` is a list of
unique exact `name`/JSON-`value` pairs owned by the application profile.
`checks` contains unique exact property ids with outcome `pass`; the
originating property must be present. The final disposition is one of
`quiescent`, `terminal`, `quarantined`, `bounded_exhaustion`, or
`external_wait`.

## First retained replay

[`projection-crash-recovery-v1.json`](../../tests/dst/fixtures/projection-crash-recovery-v1.json)
encodes the existing regression where:

1. production Engine/Coordinator freezes one stable Activity invocation;
2. Dispatch reports a terminal result;
3. the production result-ingress door commits `ActivityCompleted` before the
   registered projection raises;
4. a crash discards the Engine, Coordinator, Instance, Dispatch, and handler;
5. restart constructs every collaborator fresh from the application profile
   and retained JSONL History; and
6. production reconciliation projects the frozen result without preparing or
   dispatching the Activity again.

Run it from the repository root:

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay \
  tests/dst/fixtures/projection-crash-recovery-v1.json
```

Success is one strict `petrus-dst-replay-result` JSON line with `outcome` equal
to `pass`, History frontier 9, final `done` marking, no in-flight or pending
Activity, and passing `S1-replay-agreement`, `S3-stable-invocation`, and
`S4-terminal-before-projection` checks. The command uses no wall-clock sleep,
network, provider authority, credentials, or object serialized in the fixture.

This command is the DS1 contract proof, not the finished DST harness. DS2 owns
general event execution, fault adapters, scheduler behavior, and all-profile
bound enforcement; DS3 owns generation, shrinking, and regression promotion.
