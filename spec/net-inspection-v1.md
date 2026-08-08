# Canonical Net inspection document version 1

This document and `observation/canonical-net-inspection-v1.json` define the
language-neutral, non-executable artifact for inspecting one canonical Petrus
`Net` before an Instance exists. Petrus owns the artifact semantics and exact
fixture; Arx owns strict consumption and read-only presentation.

The strict-JSON document has exactly three top-level fields:

```json
{
  "format": "petrus-canonical-net-inspection",
  "version": 1,
  "definition": {}
}
```

`format` is the exact string `petrus-canonical-net-inspection`; `version` is the
integer `1`, not a boolean or string. `definition` is the unchanged exact
structural projection returned by `petrus.impetus.observation.definition()` and
used inside observation protocol 1. The inspection envelope is independently
versioned, while inspection version 1 is normatively bound to the observation
protocol-v1 definition shape. Changing that nested shape requires a new
inspection version and projector rather than silently changing version 1.
Inspection versioning remains independent from capture schema 1, canonical
History, and any future Net-definition file schema.

## Authority and one-way flow

The document records one immutable canonical build projection:

```text
authored Python source
    -> NetSpec.build()
    -> BuiltNet.net
    -> canonical inspection document
    -> read-only Arx presentation
```

There is no reverse arrow. Authored Python source remains the editable
authority. Rebuilding and exporting is the only way source changes produce a
new document. The document contains flattened canonical paths and declarations;
it does not retain Python source layout, helper structure, stamp origins,
destination overrides, comments, implementation maps, or repository
provenance. Presentation layout and selection are not Net semantics.

The producer operation accepts canonical `Net`; a DSL caller passes
`built.net`. The document may therefore describe a canonical Net produced by
any frontend without making the Python DSL part of its wire format.

## Exact projected content

The embedded definition preserves the established protocol-v1 projection:

- Net name and integer time domain;
- lexically path-sorted places and transitions;
- effective place/arc colors;
- named, CEL, anonymous, and absent declarations without implementations;
- declaration URIs where the canonical Net owns them;
- authored guard, timer, and arc order;
- arc position, endpoints, mode, weight, color, and filter, including parallel
  endpoint pairs; and
- the completion declaration.

The document contains no marking, tokens, Instance identity, current status,
History, enabledness, in-flight work, credentials, provider state, Python
callable, or implementation map.

## Consumer behavior

Consumers refuse malformed strict JSON, duplicate schema-owned member names,
unknown schema-owned fields, unsupported versions, predecessor documents,
observation captures, and Net-definition files rather than coercing or falling
back. Application-owned JSON value slots do not exist in schema 1.

Opening and navigating the document performs no producer request and executes
no handler, Activity, guard, filter, completion expression, CEL, or Python
module. A consumer must label the source as a read-only canonical build
inspection and must not present marking, History, enabledness, simulated
outcomes, or runtime status without a separately identified authoritative
source.

Node movement, selection, annotations, and other presentation state cannot
change the Python source, canonical Net, inspection document, or a live
Instance. Schema 1 supplies no save-as-executable, apply, deploy, simulation,
or source-patch operation.

The recommended filename extension is `.petrus-net-inspection.json`; the media
type remains `application/json`. Property order and insignificant JSON
whitespace are not semantic, and a final newline is optional. Schema 1 adds no
source provenance, digest, signature, executable-version identity, or
round-trip claim.
