# CV20.DS3.TS2 Experience Report

## Recommendation

**Pass — accept.** Petrus now owns the optional strict lineage in the same
portable Net document v1. One 15-entry producer-backed fixture navigates an
observed prefix, a manual marking replacement, a simulated descendant, and a
later observed sibling through the same `id`/`parent`/`provenance`/event/marking
projection. Confidence is 96%; the Behavior and Review checkpoints
auto-released under the local confidence rule.

## Acceptance evidence

| Contract | Evidence | Result |
| --- | --- | --- |
| Static compatibility | Existing definition-only and arranged fixture bytes remain exact; absent lineage is omitted and explicit null refuses | Pass |
| Dense flat lineage | Source and entry ids equal indexes, entry zero is the sole root, later parents are smaller, and head names an entry | Pass |
| One evolution fact | Observed and simulated entries share `HistoryRecordFact`; manual replacement is one explicit fact in the same list | Pass |
| Exact evidence custody | Canonical padded base64, SHA-256, source envelope, exact definition, complete History, snapshot/replay agreement, and source-position equality are enforced | Pass |
| Branch semantics | Later observed evidence preserves same-Instance exact prefix; simulation initial marking equals its document parent; manual hypotheses cannot become observed descendants | Pass |
| Uniform navigation | `resolve_lineage` returns all 15 mixed-fork entries with resolved markings; optional checkpoints are replay assertions and false checkpoints refuse | Pass |
| Owner artifacts | Language-neutral spec, producer-backed positive fixture, and source-custody negative fixture are exercised by production-model tests | Pass |

The positive fixture is SHA-256
`63173b9a70e729c42f898eae5b06afeb1e4e3cb0ae643fc303ea50ca8d92fea0`;
the negative fixture is
`2d1d051e78a5ab4ddb481405c7ec943aa626b7095498148a74f21e079a6cd6d1`.
The retained source payloads are exact outputs from Petrus Engine capture and
the implementation-free simulation producer, not hand-authored histories.

## Automated evidence

- `UV_FROZEN=1 uv run pytest -q tests/petrus/impetus/test_net_document.py tests/petrus/impetus/test_net_document_lineage.py tests/petrus/impetus/test_net_definition.py tests/petrus/impetus/history/test_history.py tests/petrus/engine/test_observation.py tests/petrus/engine/test_simulation.py` — 146 passed.
- `scripts/check quick src/petrus/impetus/net_document.py src/petrus/impetus/_net_document_evidence.py tests/petrus/impetus/test_net_document.py tests/petrus/impetus/test_net_document_lineage.py` — lint, formatting, production typing, and structural checks passed.
- `UV_FROZEN=1 uv run pytest -q tests/project` — 29 passed.
- Changed Markdown local-link check — all links resolved.
- `scripts/check full` — 2,192 passed. It could not complete green in this
  orb: seven failures and 256 setup errors require unavailable Docker-backed
  providers or Graphviz. Every failure/error is in those established
  infrastructure routes; none implicates the document owner code.

## Review and debt

The public wire models and navigation API remain in
`petrus.impetus.net_document`; exact source-protocol admission is isolated in
one private helper. The implementation calls current History codecs and replay,
canonical Net-definition compilation, and existing observation projections
rather than creating a second event or marking model. Runtime History stays
linear and unchanged.

No new debt item is warranted. Inline base64 can increase document size, but
external attachments and a size policy remain deliberately deferred until a
measured artifact requires them. SHA-256 is described only as byte custody,
never authenticity. Arx lineage navigation, Save As protection, manual editing,
and capable Hamsterdan V5 simulation remain explicitly outside this Petrus
Technical Story.

## Next movement

Pin the owner commit and exact fixture hashes for Petrus Arx. The next consumer
slice should open the new lineage directly, render one branch-aware timeline,
protect observed entries, and require Save As before a manual or simulated
hypothesis is persisted.
