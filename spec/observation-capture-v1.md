# Observation capture schema 1

This document and `observation/engine-capture-v1.json` define the
language-neutral portable artifact for one deliberately completed observation
of a current Petrus Instance. Petrus owns the artifact semantics and exact
fixture. A trusted consumer such as Arx assembles and keeps the artifact; no
producer archive or new Engine operation is implied.

The capture is strict JSON with exactly four top-level fields:

```json
{
  "format": "petrus-observation-capture",
  "version": 1,
  "snapshot": {},
  "history": {}
}
```

`format` is the exact string `petrus-observation-capture`. `version` is the
integer `1`, not a boolean or string. Capture schema versioning is independent
of observation protocol 1, canonical History record schemas, and any
Net-definition file schema. Canonical records without lifecycle or
queue-occurrence provenance use schema 4; lifecycle-scope and
provenance-bearing records use schema 5. The recommended filename extension is
`.petrus-observation.json`; the media type remains `application/json`. Property
order and insignificant whitespace are not semantic, and a final newline is
optional. Schema 1 adds no provenance timestamp, digest, signature, or
executable-version identity.

## Complete capture boundary

`snapshot` is one unchanged [observation protocol 1](observation-protocol-v1.md)
snapshot. Let `F = snapshot.frontier`. `history` is one normalized observation
protocol 1 History envelope with:

- the same `protocol` and `instance` as `snapshot`;
- `after: 0`;
- `next: F` and `frontier: F`; and
- exactly `F` unchanged positioned records with dense positions `[0, F)`.

`F` is a non-boolean integer of at least one. Position zero is exactly one
schema-4 `InstanceCreated` record whose `instance` equals `snapshot.instance`;
no later position may contain another `InstanceCreated`. Capture version,
observation protocol, positions, frontiers, and nested record schema versions
are exact integers rather than booleans, strings, or values accepted only by
numeric coercion.

The normalized envelope is a capture artifact, not a claim that one HTTP page
of arbitrary size was served. The consumer obtains bounded live pages, checks
them, and combines only records below `F`.

The snapshot establishes one atomic current-state/History boundary. Canonical
History is append-only, so positions below `F` cannot change while the consumer
downloads them. Assembly starts with `cursor = 0` and
`observed_frontier = F`. For each page the consumer requests
`limit = min(page_size, F - cursor)` (and at most 1,000 over the standard HTTP
profile), then requires:

- `page.after == cursor` and exact snapshot protocol/Instance identity;
- `page.frontier >= observed_frontier`;
- `page.next == min(cursor + limit, page.frontier)` and `page.next <= F`; and
- records with exactly the dense positions `[cursor, page.next)`.

It then advances `cursor = page.next` and
`observed_frontier = page.frontier`. Because every accepted page frontier is at
least `F` and the requested limit cannot pass `F`, each page in this loop ends
at `cursor + limit`. The producer may append after the snapshot and page
frontiers may rise above `F`; they may never fall between pages. The completed
capture still normalizes its embedded History frontier to exactly `F`.

Before publication, a consumer must require stable protocol and Instance
identity, exact dense positions, unchanged nested canonical History records,
and the complete prefix through `F`. Each nested record retains its canonical
schema independently: schema 4 without lifecycle or queue-occurrence
provenance and schema 5 for a lifecycle-scope or provenance-bearing record.
Interleaved schema-4/schema-5 records do not change capture version 1. Duplicate
JSON member names are refused at every schema-owned object level before
ordinary object decoding. Unknown fields in
capture, observation-protocol, and History-record structures are refused;
arbitrary application-owned JSON objects inside token data, Activity input,
results, and similar value slots retain all their keys. Unsupported versions,
malformed strict JSON, mismatches, gaps, duplicate positions, regressed
frontiers, partial downloads, and records outside the boundary are refused
rather than repaired, truncated, guessed, or interpreted as predecessor data.

## Meaning and limits

`snapshot.current` is the authoritative protocol-v1 current-state projection
**when captured at `F`**. It omits active lifecycle scopes; a scope-aware
consumer derives those only by folding the complete embedded History through
`F`. The snapshot is not live after the producer disappears. The embedded
`snapshot.definition` is the exact protocol-v1 structural inspection
projection. It is not Net-definition file schema v2/v3, contains no executable
implementations, and cannot restore a deployment.

At earlier positions a reader may fold only recorded History projections. It
must not execute handlers, Activities, guards, filters, completion declarations,
CEL, or obsolete packages, and must not present derived historical enabledness
or status as authoritative.

A completed capture remains inspectable without the host, network, Petrus
runtime, or implementation packages. An interrupted capture is not a partial
historical view and must not be published as complete. This schema does not
guarantee recovery of an Instance for which no capture completed before its
only hosted definition disappeared.

Storage, file publication, deletion, transfer, and presentation are consumer
custody. A browser consumer can validate and fully serialize before one save
commit, report success only after completion, leave its active source unchanged
on cancellation/failure, and refuse any partial bytes on later open. Browser
file APIs do not guarantee that a pre-existing selected destination survives
every write failure; schema 1 makes no stronger filesystem-atomicity claim.
Automatic backup, managed libraries, central archives, retention, discovery,
signing, encryption, long-History optimization, replay, fork, and migration are
outside schema 1.
