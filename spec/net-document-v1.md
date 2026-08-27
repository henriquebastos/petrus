# Portable Net document version 1

This document, `net-document-v1.json`, `net-document-v1-lineage.json`, and the
negative interoperability fixtures define Petrus's portable Net document. The
Pydantic models in
`petrus.impetus.net_document` own strict parsing, serialization, JSON Schema
generation, definition identity, projection from a runtime `Net`, and lineage
navigation with resolved markings.

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

`definition` is required and is exactly one canonical Net-definition v3
document. `view` and `lineage` are optional; when present, each is a non-null
strict object. A present lineage has at least one retained evidence source and
one entry. The document is not a runtime Instance, executable behavior binding,
resume authority, or replacement for canonical linear History.

## Definition authority and identity

The embedded definition retains all authority and canonical laws specified by
`net-definition-v3.md`. Parsing compiles it through the existing immutable
runtime `Net` semantic boundary. The document's definition identity is the
lowercase SHA-256 digest of:

```text
serialize_net_definition(document.definition)
```

View data never enters that digest. Moving a node therefore changes the
portable presentation while preserving exact Net identity.

## Portable view version 1

View v1 contains only authored node positions:

- `node` is the direct canonical dotted `NetPath` of a place or transition in
  the embedded definition;
- `x` and `y` are finite JSON numbers and may be fractional; and
- `nodes` contains unique paths sorted lexicographically by Unicode scalar
  value, using the same ordering rule as Net-definition v3.

A view may be partial or empty. Consumers place missing nodes without moving
the authored positions. Camera state, selection, panels, waypoints,
annotations, and editor-local state are not portable view facts.

## Execution lineage

The optional lineage retains evidence custody and projects observed,
simulated, and manual evolution into one flat entry list. The following is a
shape illustration; `net-document-v1-lineage.json` contains the exact
producer-backed conformance instance:

```json
{
  "sources": [
    {
      "id": 0,
      "kind": "observation-capture",
      "after": 0,
      "artifact": {
        "sha256": "64 lowercase hexadecimal characters",
        "base64": "canonical padded base64"
      }
    },
    {
      "id": 1,
      "kind": "simulation-result",
      "after": 0,
      "artifact": {
        "sha256": "64 lowercase hexadecimal characters",
        "base64": "canonical padded base64"
      }
    }
  ],
  "head": 2,
  "entries": [
    {
      "id": 0,
      "parent": null,
      "provenance": "observed",
      "fact": {
        "kind": "history-record",
        "source": 0,
        "position": 0,
        "record": {}
      }
    },
    {
      "id": 1,
      "parent": 0,
      "provenance": "manual",
      "fact": {
        "kind": "manual-replace-marking",
        "marking": []
      }
    },
    {
      "id": 2,
      "parent": 1,
      "provenance": "simulated",
      "fact": {
        "kind": "history-record",
        "source": 1,
        "position": 0,
        "record": {}
      },
      "checkpoint": []
    }
  ]
}
```

Source and entry ids are non-negative interoperable JSON integers, are dense,
and equal their array indexes. Entry zero is the sole root and has `parent:
null`; every later entry names a smaller parent id. Two entries may share a
parent. `head` names any existing entry and selects the current navigation
point without changing ancestry.

Observed and simulated entries use the same `history-record` fact. Its
`record` exactly equals the canonical History record at `position` in the
retained `source`. Provenance is explicit and must agree with source kind:
observation captures contribute `observed` entries and simulation results
contribute `simulated` entries. A `manual-replace-marking` fact has `manual`
provenance and replaces the complete marking at one hypothetical child; it
does not claim that a runtime History event occurred.

Sparse markings are arrays sorted by place path. Each place occurs at most
once and carries a nonempty `tokens` array; absent places have no tokens. Every
place is canonical and definition-owned. Token `color` is a nonempty string or
null and must equal a colored place's declared color. Token `data` is a strict,
finite, Unicode-scalar JSON value. The empty array is the empty marking.

## Evidence custody and replay

An embedded artifact retains exact bytes as canonical padded base64 and their
lowercase SHA-256 digest. The digest detects a changed retained payload; it is
not a signature, producer-authenticity proof, credential, or execution
authority.

An `observation-capture` source embeds exact
`petrus-observation-capture/version 1` bytes. A `simulation-result` source
embeds exact `petrus-simulation-result/version 1` bytes with profile
`implementation-free-v1`. Both artifacts must contain the document's exact
definition body, one complete dense History page beginning at zero, matching
Instance identity and frontier, canonical records, and a snapshot whose
marking, watermark, and armed registrations agree with replay. Simulation
scenario and outcome bounds are also admitted.

`after` is the first source position projected into entries. It may be greater
than zero only for an observation capture; a simulation source uses exactly
zero. Every source position from `after` through its frontier appears once and
in order in the entry list. The source's final projected entry resolves to its
snapshot marking.

A later observed source may project only a nonduplicated suffix. Its complete
retained capture must preserve the parent's Instance identity and exactly
extend the parent's canonical observed prefix. It can therefore create an
observed sibling of a hypothetical branch, but it can never descend from that
hypothesis. A simulation source may descend from any entry only when its
scenario initial marking equals that parent's resolved marking; its own
canonical History remains a disposable linear Instance.

An optional `checkpoint` repeats the complete resolved marking for its entry.
It is an assertion for faster or independent consumers, not a second state
authority, and must exactly equal replay. Omit an absent checkpoint; `null` is
not valid. Petrus's `resolve_lineage` projection gives every consumer one
source-independent sequence of `id`, `parent`, `provenance`, event name, and
resolved marking.

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
omits absent `view` and `lineage` components and absent entry checkpoints;
explicit `null` is not an alternate spelling for those optional components.

Parsing refuses malformed UTF-8, duplicate members at any depth, non-finite or
overflowed coordinates, Unicode surrogate values, unknown fields, coercible
wrong types, unsupported discriminators, null optional components, malformed
or noncanonical embedded definitions, noncanonical or duplicate view paths,
view paths foreign to the definition, malformed source artifacts, digest or
base64 contradictions, noncanonical History, invalid ids or parents,
provenance contradictions, incomplete source coverage, unrelated observed
suffixes, simulation-parent discontinuity, and false checkpoints.

`NetDocumentV1.model_json_schema()` describes structural shape. JSON Schema
alone cannot express duplicate-member refusal, Unicode-scalar ordering,
definition-owned view paths, exact v3 compilation, or finite integer overflow;
the Petrus parser and compiler remain authoritative.

## Evolution boundary

Version 1 deliberately carries no executable implementation bindings,
provider credentials, runtime leases, resume tokens, source signatures,
external attachment references, arbitrary manual patch language, or Arx-local
session state. Source artifacts remain existing Petrus protocols and canonical
History remains linear. A consumer may protect observed evidence, Save As, and
append a hypothetical branch without editing the retained capture or claiming
that manual/simulated facts occurred in production.
