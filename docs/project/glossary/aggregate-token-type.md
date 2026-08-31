# Aggregate token type

A token color whose data structurally contains other typed fields —
one single type, not a bag of several. Filters and guards read an
aggregate's nested fields directly, with no runtime type inspection.

- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
