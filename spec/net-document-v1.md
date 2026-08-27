# Petrus Net document version 1

This specification and the `net-document-v1-*.json` fixtures define the only
portable Petrus file format. A document always carries one Net definition. It
may also carry authored layout and a marking lineage, so the same shape covers
a static design, a production observation, a simulation, and a manually
forked hypothesis.

`petrus.impetus.net_document` owns strict parsing, deterministic serialization,
projection from a runtime `Net`, and definition identity.

## Envelope

```json
{
  "format": "petrus-net-document",
  "version": 1,
  "definition": {
    "format": "petrus-net-definition",
    "version": 3,
    "definition": {}
  },
  "view": {
    "version": 1,
    "nodes": [
      {"node": "review.ready", "x": 20.5, "y": 40}
    ]
  }
}
```

`format`, `version`, and `definition` are required. `view` and `lineage` are
optional and must be omitted, not set to `null`, when absent. A
definition-only document is therefore a complete valid file. Layout and
execution facts are components of that same file, not alternate file formats.

The embedded definition is exactly one canonical Net-definition v3 envelope.
It remains the semantic authority for places, transitions, arcs, colors, and
completion. It contains no implementation bindings, provider credentials, or
runtime authority.

## Definition identity

The lowercase SHA-256 definition identity is computed from:

```text
serialize_net_definition(document.definition)
```

View and lineage data do not enter that digest. Arranging nodes, selecting a
different lineage head, or adding a hypothesis therefore leaves the Net's
structural identity unchanged.

## View

View version 1 contains authored node positions only:

- `node` is the canonical dotted `NetPath` of a place or transition in the
  embedded definition;
- `x` and `y` are finite JSON numbers and may be fractional; and
- `nodes` contains unique paths sorted by Unicode scalar value.

A view may be partial or empty. A consumer may place missing nodes without
moving the authored positions. Camera state, current selection, panels,
waypoints, and other editor-local state are not portable view facts.

## Marking lineage

Lineage is one uniform navigation sequence. Every entry has the same required
shape, whether its state was observed in production, produced by simulation,
or entered manually:

```json
{
  "head": 3,
  "entries": [
    {
      "id": 0,
      "parent": null,
      "provenance": "observed",
      "marking": [
        {
          "place": "pending",
          "tokens": [
            {"color": "Work", "data": {"result": "failed"}}
          ]
        }
      ],
      "metadata": {"instance": "production-42"}
    },
    {
      "id": 1,
      "parent": 0,
      "provenance": "observed",
      "marking": [
        {
          "place": "done",
          "tokens": [
            {"color": "Work", "data": {"result": "failed"}}
          ]
        }
      ],
      "metadata": {"history_record": {"record": "FiringCompleted"}}
    },
    {
      "id": 2,
      "parent": 0,
      "provenance": "manual",
      "marking": [
        {
          "place": "pending",
          "tokens": [
            {"color": "Work", "data": {"result": "succeeded"}}
          ]
        }
      ],
      "metadata": {"note": "What if the input had succeeded?"}
    },
    {
      "id": 3,
      "parent": 2,
      "provenance": "simulated",
      "marking": [
        {
          "place": "done",
          "tokens": [
            {"color": "Work", "data": {"result": "succeeded"}}
          ]
        }
      ],
      "metadata": {"outcome": {"reason": "rest"}}
    }
  ]
}
```

`entries` is a nonempty append-ordered array. Each `id` is a non-negative JSON
safe integer equal to its array index. Entry zero is the sole root and has
`parent: null`; every later entry names a smaller id. Two entries may name the
same parent, which creates branches without a separate branch structure.
`head` names any existing entry and persists the currently selected branch
position; it need not name the last entry.

`provenance` is exactly `observed`, `simulated`, or `manual`. It states how the
entry was obtained, not how a consumer must render it:

- `observed` means Petrus projected the marking from a real runtime History
  state;
- `manual` means a person directly authored the complete marking, whether or
  not a Net transition can reach it; and
- `simulated` means Petrus computed the successor under Net and implementation
  semantics.

Provenance belongs to each entry rather than to a whole branch. A simulated
entry may therefore have a manual parent. The ancestry records that the
experiment began from a hypothesis, while the child remains simulated because
Petrus computed it. A person's choice of enabled transition does not make the
successor manual. Likewise, a hypothetical external result may be retained in
metadata while the successor remains simulated when Petrus computes its
marking.

A consumer can protect observed entries from in-place editing and append a
manual child instead. That child preserves the observed parent and turns the
changed path into a hypothesis.

`marking` is always present and is the complete state at that entry. Navigation
selects this field directly. It never replays History to discover state, and
observed, simulated, and manual entries need no separate navigation logic.
Repeated complete markings are an intentional simplicity trade-off.

The marking uses sparse form:

- the empty array is the empty marking;
- absent places contain no tokens;
- present places are definition-owned, unique, sorted by Unicode scalar value,
  and contain a nonempty token array;
- token `color` is a nonempty string or `null` and matches any color declared
  by the place; and
- token `data` is any strict JSON value with finite numbers and Unicode scalar
  strings. Integral numbers in token data and metadata stay within
  `[-9007199254740991, 9007199254740991]` so every conforming consumer retains
  their exact value.

`metadata` is always present and is a strict JSON object. It can retain useful
context such as an Instance id, a canonical `history_record`, a group of
`history_records`, simulation scenario and outcome, an observation snapshot,
or a manual note. Petrus does not interpret metadata to compute lineage
markings or ancestry. History in metadata is supporting debug evidence, not a
second state authority.

## Runtime materialization

The live observation and hosted simulation HTTP protocols remain runtime
transports rather than additional portable file formats. A live Engine
materializes its current definition and canonical History prefix as one Net
document whose entries have `observed` provenance and complete markings. A
hosted simulation returns the same document format with `simulated` entries.
Consumers may add or move view positions and append manual branches. They may
append simulated branches only from markings returned by Petrus, without
translating to another file shape.

## Canonical laws

Let `P` project a runtime Net and optional positions, `S` serialize, and `R`
parse. For every projectable Net `N`, admitted position map `V`, and admitted
document `D`:

```text
R(S(P(N, V))) == P(N, V)
R(S(D)) == D
S(R(S(D))) == S(D)
identity(P(N, absent)) == identity(P(N, V))
```

The reference writer emits deterministic UTF-8 with native Unicode,
two-space indentation, strict finite JSON numbers, and one final newline. It
omits absent `view` and `lineage` components.

Parsing refuses malformed UTF-8, duplicate members at any depth, non-finite
numbers, Unicode surrogate values, unknown fields, coercible wrong types,
unsupported discriminators, null optional components, malformed or
noncanonical definitions, foreign view or marking paths, invalid colors,
unsorted or duplicate paths, empty sparse place entries, empty lineage,
non-dense ids, invalid parents, and an unknown head.

`NetDocumentV1.model_json_schema()` describes structural shape. JSON Schema
alone cannot express duplicate-member refusal, Unicode-scalar ordering,
definition-owned paths, exact v3 compilation, or every numeric bound; the
Petrus parser and compiler remain authoritative.

Version 1 has no alternate capture, inspection, or simulation-result portable
envelopes, no source artifacts, hashes, base64 custody, checkpoints, replay
facts, attachment references, or migration paths.
