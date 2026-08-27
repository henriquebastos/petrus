# CV20.DS3.TS1 Experience Report

## Recommendation

**Pass — accept.** Petrus now owns one strict portable Net document foundation
with required canonical definition v3 and optional identity-neutral node
positions. The exact owner fixtures crossed into Arx, where the real
Hamsterdan V5 arrangement survived Save As and fresh reopen with unchanged
definition identity. Confidence is 95%; the Behavior and Review checkpoints
auto-released.

## Acceptance evidence

| Contract | Evidence | Result |
| --- | --- | --- |
| Definition-only and arranged files | Projection, parse, serialize, and parse/serialize fixed points pass for absent, partial, fractional, and complete views | Pass |
| Definition authority | Every admitted embedded v3 definition compiles through the existing canonical boundary | Pass |
| Identity | Lowercase SHA-256 uses only `serialize_net_definition(document.definition)`; absent, added, and moved views retain the same digest | Pass |
| Strict view | Coordinates are finite JSON numbers; paths are canonical, unique, definition-owned, and Unicode-scalar ordered; partial and empty views are valid | Pass |
| Strict envelope | Duplicate members, malformed UTF-8, surrogates, non-finite and overflowed values, null/unknown fields, wrong discriminators, coercible types, malformed definitions, and foreign paths refuse | Pass |
| Owner artifacts | The protocol spec, generated Pydantic schema surface, positive fixture, and negative foreign-node fixture are present and exercised by production-model tests | Pass |
| Consumer proof | Arx copied both fixtures byte-for-byte and its TypeScript consumer passed; the browser-saved 198,551-byte V5 document byte-fixed through Petrus with identity `70e3778ec802435a8e57456cc7e4edce04be30b91a6a65e53afa0d122f47e1e2` | Pass |

The positive fixture is SHA-256
`cb09cfe6bec3cfddf39a63c14aa404c03ee37e8740727c26ec8dee4526318154`;
the negative fixture is
`aa72d1f80f4dadd48b92e2b562d2439a20e017bcbb3de8c72ac19decc2a28fb3`.

## Automated evidence

- `UV_FROZEN=1 uv run pytest -q tests/petrus/impetus/test_net_document.py tests/petrus/impetus/test_net_definition.py` — 61 passed.
- `scripts/check quick src/petrus/impetus/net_document.py tests/petrus/impetus/test_net_document.py` — passed.
- Arx's final cross-story `pnpm check` passed 1,144 tests, 49/49
  conformance checks, typechecks, lint/stylelint, dependency rules, and the
  production build.
- Petrus's final `scripts/check full` passed all static, structural, Graphviz,
  PostgreSQL, and test gates with 2,456 tests passed.

## Review and debt

The implementation sits beside canonical Net definition ownership and calls
its parser/compiler/serializer rather than duplicating v3 semantics. One frozen
Pydantic model family owns strict wire shape; parser and writer add the JSON
laws that schema alone cannot express. View data remains outside Net identity
and runtime authority.

No new debt item is warranted. Camera, selection, waypoints, markings,
execution, and Arx file custody remain outside this Petrus Technical Story.
The later TS2 adds optional lineage without changing this definition/view
foundation.

## Next movement

Keep CV20.DS3 Active for its application-bound V5 simulation and live
understanding follow-up. The portable definition/view and Arx arrangement
acceptance are complete.
