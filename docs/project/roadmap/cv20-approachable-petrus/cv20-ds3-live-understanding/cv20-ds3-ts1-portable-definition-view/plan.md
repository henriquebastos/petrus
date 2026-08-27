# CV20.DS3.TS1 Plan — Portable definition and view document foundation

## Plan checkpoint

- **Roadmap level:** Technical Story under active CV20.DS3.
- **Version intent:** additive pre-release protocol capability in Petrus 0.0.0;
  no canonical Net v3 or runtime History version changes.
- **Confidence:** 93%. The Plan auto-released under the project rule after the
  Navigator asked to continue from accepted ES-061 and CV20 promotion.

## Scope and design

Add `petrus.impetus.net_document` beside the canonical definition owner. It
will own strict Pydantic models, parser, deterministic serializer, definition
identity, and projection from one runtime Net.

The first production shape is:

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
    "nodes": [{"node": "review.ready", "x": 20.5, "y": 40}]
  }
}
```

`definition` is required. `view` is absent or one strict object, never null.
View v1 contains node positions only. Paths are direct canonical Net paths,
unique and Unicode-scalar ordered. Partial layout is valid so a consumer may
place missing nodes without moving authored ones.

Coordinates are finite JSON numbers, including fractional values. They are
presentation values rather than canonical Net identity, runtime time, counts,
or History positions; applying the v3 safe-integer rule would lose real ELK and
drag coordinates without improving semantic authority. Non-finite constants or
overflowed numeric values are refused.

Definition identity is lowercase SHA-256 over
`serialize_net_definition(document.definition)`. The outer document and view
never enter that digest. The serializer emits UTF-8, `ensure_ascii=False`,
two-space indentation, strict finite JSON, and one trailing newline while
omitting absent optional components.

## Alternatives rejected

1. **Put layout inside Net definition v3.** Rejected because it changes
   canonical semantic identity and breaks v3's explicit layout deferral.
2. **Use predecessor `viewState`.** Rejected because it belongs to a closed
   v2 schema and carries unrelated waypoints/annotations/ref state.
3. **Restrict coordinates to safe integers.** Rejected for this slice because
   actual layout and dragging produce useful finite fractions; positions are
   not integer semantic facts.
4. **Implement lineage before static arrangement.** Deferred, not rejected.
   ES-061 already proves the lineage semantics, but the Navigator's immediate
   feedback loop is V5 arrangement. Optionality lets the static tracer land
   without weakening the eventual one-envelope model.

## Validation route

1. Start with failing protocol/model tests for definition-only, arranged,
   partial, fractional, identity-preserving, and malformed inputs.
2. Implement the minimum production models and functions.
3. Generate schema/fixtures from production and test byte/semantic fixed points.
4. Run focused Net-definition/document tests, project checks, and the broad
   gate appropriate for a new public Impetus protocol module.
5. Supply the exact accepted fixture and commit to Arx; Arx independently
   verifies its strict consumer against the owner bytes.

## Documentation and coherence

Add the protocol spec and link it from the spec index and DS3. At Behavior and
Review checkpoints, decide whether the accepted contract warrants a new
Petrus decision record and whether any implementation debt survives. Do not
change product principles: existing progressive-disclosure and canonical-Net
authority principles already own this direction.
