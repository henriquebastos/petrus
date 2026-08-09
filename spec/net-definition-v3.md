# Net-definition file schema version 3

This document, `net-definition-v3.json`, and the positive and negative
`net-definition-v3-*` interoperability fixtures define Petrus's canonical
language-neutral cross-system Net definition. The Pydantic models in
`petrus.impetus.net_definition` own strict parsing, serialization, JSON Schema
generation, and compilation to the immutable runtime `Net`.

## Envelope

```json
{
  "format": "petrus-net-definition",
  "version": 3,
  "definition": {}
}
```

Both discriminators are required exactly. Schema v3 is not predecessor v2,
canonical inspection v1, observation protocol v1, an observation capture, a
simulation result, or History.

## Authority and phases

The v3 JSON document is canonical for cross-system definition exchange. The
Pydantic document is the typed in-memory form of those exact bytes. Compilation
constructs the existing immutable `Net`, whose constructor remains the one
semantic topology, inscription, source-transition, timer-anchor, and index
boundary.

```text
Python DSL or another frontend -> Net -> v3 document
v3 JSON <-> Pydantic NetDefinitionV3 -> Net
Arx or another editor <-> v3 JSON
```

A frontend need not serialize and parse its own in-process build. Equivalent
frontends converge on the same v3 projection. Executable behavior remains a
separate implementation binding supplied when an Instance is constructed.

## Flat definition

The document contains one complete flattened Net:

- optional descriptive name and exact integer time domain;
- unique lexically sorted places with full dotted `NetPath` and optional color;
- unique lexically sorted transitions with full path, handler declaration,
  ordered guards, and ordered timers;
- arcs in semantic definition order with exact dense zero-based positions,
  endpoints, consume/read/inhibit mode, positive weight, effective color, and
  optional filter; and
- one optional completion declaration.

Named and CEL declarations are implementation-free. Anonymous handlers and
guards retain their canonical owner/occurrence URI. Handler and guard URIs are
derived assertions: they must exactly match the canonical runtime `Net`.
Arc-filter declarations have canonical runtime URIs derived from endpoints,
endpoint-pair multiplicity, and dense semantic arc order; those URIs are not
serialized fields. Completion conditions have no independent URI in v3.

Typed-place colors are already compiled onto every incident arc. A document
with an inherited `null` arc color is noncanonical and refused rather than
normalized. Parallel arcs remain distinct through list order and position;
compilation deterministically assigns their pair-local `#$N` arc identities
and `#filter:$N` filter declaration identities without changing the document.

## Canonical laws

Let `P` project a runtime Net, `C` compile a document, `S` serialize, and `R`
parse. For every projectable Net `N` and every admitted document `D`:

```text
P(C(P(N))) == P(N)
P(C(D)) == D
R(S(D)) == D
S(R(S(D))) == S(D)
```

The reference writer emits deterministic UTF-8 from the Pydantic model's JSON
value with two-space indentation and one final newline. Property order and
insignificant whitespace are not semantic on input. Parsing refuses malformed UTF-8, duplicate members
at any depth, non-finite numbers, Unicode surrogate values, unknown fields,
coercible wrong types, unsupported discriminators, noncanonical collection
order/positions/derived fields, and every runtime `Net` semantic violation.

### Interoperable integers

Every JSON number token in a v3 document must use integer token spelling and
must be in this inclusive range:

```text
[-9007199254740991, 9007199254740991]
```

Decimal and exponent spellings are refused even when they denote an integer.
The bound applies before envelope, model, or semantic admission and is also
expressed by every variable integer field in the generated JSON Schema. Arc
positions retain the stronger lower bound zero; arc weights retain the stronger
lower bound one. Runtime projection refuses an integer outside this range
rather than emitting a document another conforming implementation cannot hold
exactly. This is the RFC 8259 interoperable integer range, not an
arbitrary-precision extension or a string-integer convention.

### Canonical path ordering

Place and transition paths are ordered by comparing their complete, unescaped
dotted strings lexicographically as sequences of Unicode scalar values by
unsigned scalar value. At the first difference, the smaller scalar sorts
first; if one sequence is a prefix of the other, the shorter sequence sorts
first. No locale collation or Unicode normalization occurs. Native UTF-16 code
unit ordering is not the protocol rule.

The positive interoperability fixture discriminates these rules with
`U+E000 < U+1F600` and both safe-integer bounds. The invalid fixtures pin
out-of-range integer and reversed UTF-16-style path order refusal. Petrus and
Arx retain these files byte-for-byte as a shared conformance seam.

The generated `NetDefinitionV3.model_json_schema()` describes structural
shape. JSON Schema alone cannot express duplicate-member refusal, canonical
ordering, derived URIs/effective colors, endpoint topology, or runtime semantic
rules; the Petrus parser/compiler remains authoritative.

## Flat templates, not executable nesting

Schema v3 has no refs, mounts, recursive files, or separately executable
subnets. Python reusable specifications and future editor templates may stamp,
copy, or merge authored material before projection. Their output is one flat
definition with complete paths.

An independently packaged Net plus Activities, handlers, credentials, and
deployment policy is not an authoring subnet. It is a separately bound
application/Instance. Independently encapsulated Instances communicate through
Fabric rather than sharing one executable definition.

## Delta from predecessor v2

Schema v3 deliberately changes predecessor v2 rather than claiming
compatibility:

- exact `format` and integer `version` replace unrestricted `fileVersion`;
- node maps and relative paths become canonical sorted lists and full paths;
- refs, ref origins, multi-file resolution, and editor `viewState` are absent;
- arc order and multiplicity are explicit through dense positions;
- current consume/read/inhibit, color, filter, guard, timer, completion, and
  canonical URI semantics replace predecessor fields; and
- strict canonical admission and the current `Net` constructor replace the
  predecessor's permissive projection gaps.

There is no implicit v2 migration or fallback.

## Pre-release v3 corrigendum

The integer range and scalar-order wording were pinned after the first bounded
Petrus/Arx round trip exposed that Python arbitrary integers and JavaScript
UTF-16 ordering could not support the original language-neutral claim
universally. The project accepted one coordinated pre-release v3 corrigendum:
Petrus and Arx changed together, retained the original fixture bytes, and
published exact shared conformance vectors. No unbounded-integer v3 exchange
was supported. Future changes to v3 admission require a successor protocol
version; this correction is not a general exception to versioning.

## Explicit deferrals

Schema v3 does not contain layout, waypoints, annotations, comments, initial
marking, tokens, Instance state, History, enabledness, simulation scenarios,
implementation bindings, Python source, repository provenance, credentials,
provider state, deployment packaging, or file-custody operations.

Current `Place` does not yet implement the descriptive role vocabulary in
`net-schema.md`; v3 therefore cannot serialize it. Correlated inhibitor
semantics are separately decided but not yet implemented by runtime `Arc`; v3
does not invent an inert field. Adding either semantic to the canonical file
requires an explicit successor version and matching runtime delivery.
