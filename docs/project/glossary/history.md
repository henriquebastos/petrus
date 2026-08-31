# History

One Instance's canonical semantic timeline: append-only and
uncompacted, like a tracing log, with every transition firing
contributing. Projections, indexes, snapshots, and summaries may be
derived from it but never replace it.

- Avoid: journal, firing journal, storage/provider names as synonyms
- Related: [History record](history-record.md), [History Store](history-store.md)
- Detail: [spec/event-history.md](../../../spec/event-history.md)
