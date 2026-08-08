---
status: Decided
raised: 2026-08-04
decided: 2026-08-04
deciders:
  - HB (Navigator)
  - Driver recommendation, accepted under project checkpoint policy
related:
  - CV18.DS2
  - docs/project/decisions/records/2026-07-23T1614Z-impetus-owns-versioned-net-definition-protocol.md
  - spec/net-definition-v3.md
---

# V3 interoperability hardening is a one-time pre-release corrigendum

## Question

Should Petrus narrow schema v3 after its first bounded Arx round trip exposed
that Python's arbitrary integers and JavaScript's UTF-16 ordering did not yet
support a universal language-neutral interchange claim, or introduce v4
immediately?

## Decision

Apply one coordinated pre-release corrigendum to v3. Every JSON number token is
an integer in the inclusive RFC 8259 interoperable range
`[-9007199254740991, 9007199254740991]`. Canonical place and transition order is
lexicographic Unicode scalar-value order over complete unescaped dotted paths,
with no normalization or locale collation. Petrus and Arx change together and
retain identical positive and negative conformance fixtures.

This is a one-time exception, not a new versioning policy. No unbounded-integer
v3 document was a supported cross-system artifact; the only accepted owner
fixture remains byte-identical. After this corrigendum, any change to the set of
admitted v3 documents requires a successor protocol version.

## Rationale

The Navigator chose to strengthen the interchange foundation before broadening
Arx authoring. Safe integers are represented exactly by Python and ordinary
JavaScript JSON values, while arbitrary-precision JSON numbers would require a
different token/value custody model throughout browser tooling. Unicode scalar
ordering matches Python's code-point semantics and can be implemented
explicitly in TypeScript; native JavaScript UTF-16 order cannot be canonical
across languages.

The alternative v4 is mechanically purer because the integer bound narrows
what Petrus's first v3 parser admitted. It would, however, preserve an
interoperability defect in the only canonical version before any supported
document exercised that latitude. Recording the exception, changing both
consumers atomically, retaining the original bytes, and pinning exact vectors
makes the correction explicit without creating parallel pre-release formats.

## Options Considered

- **Introduce v4.** Rejected for this one pre-release correction because there
  is no supported unbounded-integer v3 exchange to preserve and both current
  owners can align atomically.
- **Use arbitrary-precision or string integers.** Rejected because this would
  expand the protocol and browser custody model beyond demonstrated Net needs.
- **Keep native language ordering.** Rejected because Python code-point and
  JavaScript UTF-16 order disagree for discriminating non-BMP paths.
- **Apply and record one v3 corrigendum — chosen.** It makes the existing
  language-neutral claim true before authoring expands.

## Consequences

- Parser admission, Pydantic fields, runtime projection, generated schema, and
  shared fixtures enforce the same integer range.
- Collection validation and projection use explicit scalar-value ordering.
- Existing `net-definition-v3.json` bytes and semantics do not change.
- Decimal/exponent JSON number spellings remain outside v3 even when integral.
- Future v3 admission changes require a successor version.

## Review Trigger

Return before adding a numeric domain that cannot fit the interoperable range,
normalizing Unicode, changing path comparison, or changing v3 admission.
