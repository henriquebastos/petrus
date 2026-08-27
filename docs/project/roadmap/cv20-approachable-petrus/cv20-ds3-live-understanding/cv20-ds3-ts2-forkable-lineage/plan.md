# CV20.DS3.TS2 Plan — Forkable execution lineage foundation

## Plan checkpoint

- **Roadmap level:** Technical Story under active CV20.DS3.
- **Version intent:** complete the optional lineage component of pre-release
  `petrus-net-document/version 1`; definition/view-only documents remain valid
  and unchanged.
- **Confidence:** 94%. ES-061 already proved the producer-backed mixed fork and
  the Navigator accepted its semantics. The Plan auto-released under the local
  process rule.

## Wire shape

The optional component is:

```json
{
  "lineage": {
    "sources": [
      {
        "id": 0,
        "kind": "observation-capture",
        "after": 0,
        "artifact": {"sha256": "…", "base64": "…"}
      }
    ],
    "head": 2,
    "entries": [
      {
        "id": 0,
        "parent": null,
        "provenance": "observed",
        "fact": {
          "kind": "history-record",
          "source": 0,
          "position": 0,
          "record": {}
        }
      },
      {
        "id": 1,
        "parent": 0,
        "provenance": "observed",
        "fact": {
          "kind": "history-record",
          "source": 0,
          "position": 1,
          "record": {}
        },
        "checkpoint": []
      },
      {
        "id": 2,
        "parent": 1,
        "provenance": "manual",
        "fact": {"kind": "manual-replace-marking", "marking": []}
      }
    ]
  }
}
```

`sources` and `entries` are dense append-ordered arrays. Explicit integer ids
remain on the wire and equal their indexes. Entry parents alone express
ancestry, so two later entries may share one parent. `head` selects one current
entry without changing branch structure.

An observation source may use `after > 0` only when it retains a complete
capture that exactly extends its observed parent. A simulation source always
projects from position zero of its own disposable Instance. Both produce the
same entry fact; provenance remains explicit and must agree with source kind.

## Source custody and navigation

Retain exact source bytes inline as canonical padded base64 plus lowercase
SHA-256. This settles the immediate one-file requirement and the proven AX2
shape without introducing attachment infrastructure. The digest proves that
the retained bytes were not changed inside the document; it is not a signature
or production-authenticity claim.

Petrus parses each source once during document admission. It verifies the
existing capture/result envelope, exact embedded definition, complete dense
canonical History, snapshot/replay agreement, and result scenario/outcome
facts. Every source position from `after` through frontier appears exactly once
in the shared entries list and each copied record equals the retained source.

The public navigation projection returns the same fields for every entry:
`id`, `parent`, `provenance`, event name, and resolved marking. Consumers never
need to open a hidden capture or simulation timeline.

## Alternatives rejected

1. **Entries without retained sources.** Rejected because a changed observed
   record remains structurally valid and cannot be related to imported
   evidence.
2. **Whole capture/result per entry.** Rejected because consumers regain
   separate nested timelines and later captures duplicate their full prefix.
3. **Branch canonical History.** Rejected because one Instance has one dense
   append-only History and manual intervention did not occur in that History.
4. **External attachments now.** Deferred because they would violate the
   immediate one-file goal and add storage/custody infrastructure before a
   measured artifact-size problem exists.
5. **Infer provenance from source completeness.** Rejected because redacted
   production evidence can be less complete than a realistic simulation.

## Validation route

1. Add failing public tests for all six accepted forms and the mixed 15-entry
   observed/manual/simulated fork.
2. Add frozen strict models and source-independent navigation records beside
   the existing Net document owner.
3. Promote the exploration's source/replay checks with current production
   codecs; remove exploration-only duplication where safe only after parity.
4. Generate one mixed positive fixture and focused negative fixtures from real
   Engine/capture/simulation producers; assert parse/serialize fixed points.
5. Run focused and broad Petrus verification and check all changed links,
   roadmap state, spec coherence, and retained fixture hashes.

## Documentation and handoff

Extend `spec/net-document-v1.md` rather than creating another top-level format.
At acceptance, pin exact fixtures for Arx. Arx may then open one lineage story
against the Petrus owner contract; it must preserve imported observed custody
and use Save As before a hypothesis can become a persisted branch document.
