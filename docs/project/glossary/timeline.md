# 1 Timeline

The Net document's optional parent-linked sequence of steps, each carrying a
complete marking and observed, simulated, or manual provenance. Branches can
continue from an observed state or a manually authored hypothesis.

- Use when: navigating or branching states in a Net document.
- Do not use for: [History](history.md), the canonical linear record of one
  Instance, or process/Thread ancestry. History metadata in a Timeline is
  supporting evidence; navigation reads each entry's complete marking.
- Avoid: execution lineage, the former name. `ExecutionLineage` remains the
  Python class and `lineage` the serialized field. The separate DST `Timeline`
  class is an authoring facade, not a Net document Timeline.
- Related: [Net document](net-document.md), [History](history.md)
- Detail: [Net document specification](../../../spec/net-document-v1.md#1d-timeline)
