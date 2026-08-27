# Portable Net document version 1

This document, `net-document-v1.json`, and the negative interoperability
fixtures define Petrus's portable Net document. The Pydantic models in
`petrus.impetus.net_document` own strict parsing, serialization, JSON Schema
generation, definition identity, and projection from a runtime `Net`.

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
document. `view` is optional; when present, it is a non-null strict object.
The document is not an observation capture, simulation result, runtime
Instance, executable behavior binding, or History.

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
omits an absent `view`; explicit `null` is not an alternate spelling.

Parsing refuses malformed UTF-8, duplicate members at any depth, non-finite or
overflowed coordinates, Unicode surrogate values, unknown fields, coercible
wrong types, unsupported discriminators, null view, malformed or noncanonical
embedded definitions, noncanonical or duplicate view paths, and view paths
foreign to the definition.

`NetDocumentV1.model_json_schema()` describes structural shape. JSON Schema
alone cannot express duplicate-member refusal, Unicode-scalar ordering,
definition-owned view paths, exact v3 compilation, or finite integer overflow;
the Petrus parser and compiler remain authoritative.

## Evolution boundary

This foundation deliberately contains no marking, tokens, History, evidence,
simulation branch, source custody, or provenance. ES-061 accepted a later
optional flat lineage component in this same pre-release envelope. Until that
component is specified and implemented, it is an unknown field and is
strictly refused rather than guessed.
