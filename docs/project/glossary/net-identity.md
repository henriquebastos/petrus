# Net identity

The SHA-256 digest of the canonical Net-definition v3 bytes embedded
in a Net document; two documents describe the same Net exactly when
their Net identities are equal. Layout and Timeline changes never
alter it.

- Do not use for: a Petrinet Instance's durable identity — an
  Instance is one running execution, not the authored Net.
- Avoid: definition identity (former name).
- Related: [Net definition](net-definition.md),
  [Net document](net-document.md)
- Detail: [spec/net-document-v1.md](../../../spec/net-document-v1.md)
