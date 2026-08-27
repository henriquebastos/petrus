# AX2 portable-document spine

This bounded prototype compares three ES-061 document compositions. It is
evidence, not a public Petrus parser, schema, migration promise, or production
API.

## Compared shapes

### 1. Uniform entries without evidence anchors

`lineage.entries` is one dense append-ordered list. A History entry carries one
canonical record, source-local position, parent, and provenance. A manual entry
carries one explicit complete marking replacement. Observed and simulated
records have exactly the same fact shape.

This shape gives consumers one navigation loop, but it cannot prove that an
entry came from an imported capture or simulation result. The executable
comparison admits a canonically valid mutation after its source table is
removed. It therefore fails observed-custody authority.

### 2. Uniform entries plus immutable evidence anchors — leading shape

The top-level strict JSON object exercised by `uniform_spine.py` is:

```text
petrus-net-document/v1
├── definition: complete petrus-net-definition/v3 envelope
├── view?: strict v1 portable-view component
└── lineage?:
    ├── sources: dense immutable custody-anchor table
    ├── head: entry id
    └── entries: dense append-ordered navigation list
```

Each source anchor retains exact observation-capture or simulation-result bytes
as `{sha256, base64}`. Its `after` field says which source History position is
the first projected entry. A later observed capture can therefore prove an
exact shared prefix while adding only its new suffix to the document list.
SHA-256 detects changed retained bytes; it is not a signature, producer proof,
or authenticity claim.

Every entry has `id`, `parent`, `provenance`, and one strict fact:

- `history-record` carries `{source, position, record}` for both observed and
  simulated canonical records; or
- `manual-replace-marking` carries an explicit intervention result.

An optional `checkpoint` is a replay-derived marking assertion for faster
navigation. It is not a source, event container, or second timeline. The
parser normalizes every entry to the same `NavigationEntry` fields: `id`,
`parent`, `provenance`, `event`, and resolved `marking`. Source-specific
capture/result parsing occurs once at admission to prove custody. Navigation
does not open those artifacts.

The mixed producer-backed fixture contains 15 entries in one list:

1. two records from an observed root capture;
2. one manual marking replacement;
3. all seven records from a disposable simulation descended from that manual
   state; and
4. five new records from a later observed capture as a sibling branch.

The later capture's two-record prefix remains in its immutable source bytes but
is not duplicated in navigation. One source-independent loop sees the observed
event sequence, intervention, simulated sequence, and observed sibling.

This list is a derived portable lineage, not canonical runtime History. Each
retained source keeps its own dense, linear per-Instance History. A simulation
source begins with its own `InstanceCreated` and `TokensInitialized`; position
zero resets source-local replay, and its declared initial marking must equal
the document parent state. An observed extension must preserve Instance
identity and exactly match its parent prefix. Observed entries cannot descend
from manual or simulated hypotheses.

### 3. Whole-artifact checkpoint containers — control

`document_spine.py` retains the first AX2 shape as the control. Its mixed fork
has four outer checkpoints but 16 records hidden in three nested source
Histories. Consumers must open capture/result-specific payloads to navigate
events, and the later observed checkpoint repeats the complete two-record
prefix. Passing its original 45 tests establishes strict custody and checkpoint
composition, not one-list navigation.

## View boundary

View remains outside definition identity and execution lineage. The uniform
probe uses direct globally unique canonical Net paths and accepts finite JSON
numbers, including fractional coordinates, because Arx revision `1e81a8d`
currently uses finite JavaScript-number geometry. AX2 deliberately does not
choose safe integers, binary64, waypoints, annotations, or the final portable
view subset; those remain AX3 acceptance questions.

## Executable evidence

`examples.py` constructs definition-only, definition-plus-view, observed,
manual, simulated, and mixed-fork fixtures through Petrus's real `Net`,
`Engine`, observation, History, Net-definition, and `simulate(...)` producers.
The uniform suite verifies:

- strict UTF-8 JSON and exact envelope/source discrimination;
- explicit non-boolean integer ids, `id == index`, one root, smaller parents,
  valid head, dense source ids, and source-position coverage;
- canonical v3 compilation and definition equality in every retained source;
- exact canonical History records and byte-equality to each source position;
- observed same-Instance exact-prefix extension without duplicated navigation
  entries;
- simulation initial-state relation and source-local canonical replay;
- manual intervention in the same list and optional checkpoint agreement;
- provenance-confusion and malformed-source refusal;
- one generic navigation loop over the complete mixed fork; and
- the demonstrated custody failure of entries without anchors.

Run it from the repository root:

```bash
UV_FROZEN=1 uv run pytest -q \
  docs/project/exploration/es-061-portable-net-document-and-forkable-execution-lineage/experiments/portable-document-spine/test_document_spine.py \
  docs/project/exploration/es-061-portable-net-document-and-forkable-execution-lineage/experiments/portable-document-spine/test_uniform_spine.py

scripts/check quick \
  docs/project/exploration/es-061-portable-net-document-and-forkable-execution-lineage/experiments/portable-document-spine
```

## Limits

- The parsers remain exploration-local. They do not choose the public error
  model, extension, media type, size bounds, source-table encoding, or API.
- SHA-256 plus retained bytes proves internal custody only, not who produced an
  artifact or whether it came from production.
- `manual-replace-marking` is the smallest intervention proven here. Patch
  operations or a wider manual-operation vocabulary are not implied.
- Every point is inspectable, but none is automatically resumable. The document
  carries no History Store writer authority, implementation bindings, provider
  state, or live host.
- Arx layout/save/reopen and Hamsterdan V5 application-bound simulation were
  not run. Current `implementation-free-v1` cannot execute V5: its 137
  transitions and 570 arcs exceed limits of 128 and 512, and its handlers are
  forbidden by that profile.
