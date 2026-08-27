# CV20.DS3.TS2 Plan — Direct-marking execution lineage

## Plan checkpoint

- **Roadmap level:** Technical Story under active CV20.DS3.
- **Version intent:** keep only pre-release `petrus-net-document/version 1`;
  definition/view-only documents remain valid.
- **Refinement:** this plan supersedes the earlier source-anchor and replay
  design. The Navigator chose repeated complete markings and one common entry
  shape to keep Petrus Arx navigation simple.

## Wire shape

```json
{
  "lineage": {
    "head": 2,
    "entries": [
      {
        "id": 0,
        "parent": null,
        "provenance": "observed",
        "marking": [],
        "metadata": {"history_record": {}}
      },
      {
        "id": 1,
        "parent": 0,
        "provenance": "manual",
        "marking": [],
        "metadata": {"note": "What if?"}
      },
      {
        "id": 2,
        "parent": 1,
        "provenance": "simulated",
        "marking": [],
        "metadata": {"history_record": {}}
      }
    ]
  }
}
```

Entries are append-ordered. Explicit integer ids equal their indexes. Parents
alone express ancestry, so entries may share a parent. `head` persists the
selected branch position and need not name the final array entry.

Every entry directly contains its complete sparse marking. `metadata` is a
required strict-JSON object but is not state authority. Producers may retain a
canonical History record, current observation, scenario, outcome, Instance id,
or note there. A consumer never replays metadata to navigate.

Provenance describes how that entry's marking was obtained:

- `observed` is projected from a real Petrus History state;
- `manual` is a complete marking authored directly by a person; and
- `simulated` is a successor computed by Petrus.

A manual entry may parent a simulated entry. For example, a person may replace
the Hamsterdan readiness marking to express a hypothetical approval and then
ask Petrus to fire `ready.fold_human`. The replacement is manual; the successor
that Petrus computes is simulated. Ancestry retains the hypothesis boundary.
Choosing the transition does not change that classification.

## Producer boundaries

1. A live Engine projects one `observed` entry per canonical History record,
   with the marking after that record and final current observation metadata.
2. Hosted implementation-free simulation projects one `simulated` entry per
   canonical History record, with scenario and outcome context on its root.
3. A consumer appends a `manual` child to edit from any selected point. It does
   not mutate the parent or relabel the hypothesis as observed.
4. A consumer appends simulated entries only from a Petrus response. The
   current detached profile is bounded and implementation-free; a future
   application-bound service will own V5 enabledness, handlers, and
   hypothetical external results.

Runtime snapshot and History HTTP routes remain useful live transports.
`GET /v1/document` and hosted simulation materialize those runtime facts into
the one portable file format.

## Validation route

1. Replace the source/fact/checkpoint models with one strict entry model.
2. Pin dense ids, parent/head laws, complete sparse markings, strict metadata,
   and deterministic serialization in Petrus owner tests and fixtures.
3. Materialize observed and simulated documents with the same shape.
4. Remove unreleased inspection, capture, and simulation-result portable
   formats and all migration logic.
5. Verify the owner fixtures across Petrus and Arx, then exercise a real
   Hamsterdan V5 definition document on the Arx shared canvas.
