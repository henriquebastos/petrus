# Layout

The Net document's identity-neutral node arrangement: positions only,
addressing places and transitions of the embedded definition by path;
partial layouts are valid. Moving a node changes layout bytes, never
the Net identity.

- Do not use for: derived runtime views such as the Engine's
  `InFlightView`.
- Avoid: portable view (former name; the `PortableViewV1` class is
  pending rename), viewport.
- Related: [Net document](net-document.md),
  [Net identity](net-identity.md)
- Detail: [spec/net-document-v1.md](../../../spec/net-document-v1.md)
