---
code: ES-062
title: Consolidation and coherence baseline
status: Active
status_reason: >-
  WS3 reader guidance, DST documentation consolidation, and exploration Memory
  Closure are complete. WS2 vocabulary/code renames and WS4-WS6 design reviews
  remain open. Runtime formats and experiment evidence remain supported/retained.
opened: 2026-08-31
updated: 2026-09-08
related:
  - CV20
  - CV19
  - docs/project/glossary/index.md
  - spec/OVERVIEW.md
  - docs/ariad/index.md
  - docs/process/deterministic-simulation-testing.md
  - docs/process/engineering-conventions.md
source_context:
  - impetus/docs/references/2026-07-09-matt-hb-vision-call-transcript.md
  - impetus/docs/references/2026-07-09-vision-themes.md
---

# 1 Consolidation and coherence baseline

## 1a Current position, 2026-09-08

The reader-facing documentation and Memory Closure pass is complete. Readers
can start at the [README](../../../../README.md), follow the
[documentation guide](../../../README.md), and reach one
[World reference](../../../process/dst-world.md) for DST authoring and replay.
Exploration indexes state their conclusion or pause and link to current owners.
The [worklog guide](../../../process/worklog/index.md) preserves dated evidence
and limits future entries to meaningful milestones.

ES-062 remains Active because terminology and design reviews below remain open.
Runtime code, tests, fixtures,
experiment artifacts, decision records, and the installed Ariad package were
preserved during the WS3 pass. The subsequent WS2 pass below reconciles current
specification prose and a dated decision note with already accepted meaning.
Neither pass accepted a new runtime contract, format retirement, exploration
promotion, or product support claim.

## 1b Workstreams and next movement

| Workstream | State and next movement |
| --- | --- |
| WS1: factual repairs | Done. Corrected overview and Ariad claims after checking the survey. The flagged bytecode was untracked; the compatibility module is used; the roadmap date was a template. |
| WS2: domain language | Glossary adopted and the rulings below accepted. Remaining Engine/overloaded-word decisions and code renames need their own bounded work. |
| WS3: documentation | Reader guidance, DST contract consolidation, and exploration closure complete. Format retirement or pruning executed experiments requires separate evidence and compatibility decisions. |
| WS4: DST coverage and contribution rules | Review Agenticus/Fabric/processes coverage, CV20's relevant correctness obligations, and the supported test-kit package boundary. No implementation accepted here. |
| WS5: architecture | Review the compatibility facade, private Fabric imports, and ownership of root simulation modules against current callers. No deletion inferred from a survey. |
| WS6: Python review | Review against the Navigator's Python conventions when commissioned. No broad refactor is part of this pass. |

The next direction decision is which unresolved workstream to take. Paused
ES-052 still needs reactivation before Experiment 1; ES-060 still needs the
Navigator's benchmark feature-net. Their closure did not release those gates.

## 1c Survey provenance and corrections

Five read-only surveys on 2026-08-31 inspected architecture, vision provenance,
domain language, DST coverage, and documentation at `b7265ff`. The original
reports remain in Git history. Their findings were leads to verify, not a
license to remove code or rewrite contracts.

The founding Matt Scott conversation and vision decomposition were retained in
`impetus/docs/references/`, outside this repository. Petrus's own
[principles](../../../product/principles.md), [briefing](../../briefing.md), and
specification carry the product direction needed by contributors.

WS1 corrected false claims about an implemented `unpack` handler and empty
Ariad/worklog records. Three initial findings were wrong: `.pyc` files had
never been tracked; `motus/_execution/model.py` is imported by compatibility
tests; and `updated: YYYY-MM-DD` was inside a template. The then-current
`tests/project` run passed 29 tests.

The initial DST pruning suggestion also overstated redundancy. The September
review counted 1 World v1, 2 World v2, 45 World v3, 3 World v4, and 1 internal
Scenario v1 fixture. `Budget` still authors v3. The consolidation therefore
preserved all formats and fixture bytes and replaced chronological contract
reading with one current reference plus compatibility notes.

## 1d WS2 glossary adoption and accepted rulings

The project adopted the glossary directory on 2026-08-31 and removed
`CONTEXT.md` under the
[owning decision](../../decisions/records/2026-08-31T1922Z-glossary-directory-replaces-context-md.md).
The migration created 127 term files, checked coverage, and moved remaining
contract details into their specifications before deleting the monolith.
Those details covered token-queue removal, Sensor re-offer, Engine driving,
inhibitor handling, and the open token-type ledger question.

Ariad was upgraded as complete verified packages, first to 0.2.2 and then 0.3.0.
Project-specific guidance stays outside that installed snapshot. The
[glossary](../../glossary/index.md) owns current definitions; the list below
preserves accepted rulings and unresolved follow-up.

Ruling backlog, one per session, Navigator-paced:

1. ~~History vs event history~~:  ruled 2026-08-31: capitalized History
   is canonical; "event history" stays as an acceptable descriptive long
   form. Recorded in the glossary and as a review outcome on the 2026-07-06
   record.
2. ~~Candidate Selection~~:  ruled 2026-08-31: the Navigator renamed the
   pair to Transition Selection (policy level; implementation:
   Transition Selector) and Token Selection (arc level, formerly bare
   "Selection"). Glossary terms added with mirror boundaries, spec prose
   swept, review outcome recorded on the 2026-07-22 record. Follow-up:
   code identifiers (`Scheduler`, the `petrus.impetus.selection`
   `SelectionPolicy` family) are pending rename.
3. ~~DST vocabulary~~:  ruled 2026-08-31, definitions Navigator-accepted:
   eleven terms (Deterministic Simulation
   Testing, World, Workload, Checker, Fault, Durability boundary, Choice
   streams, Budget, Campaign, Scripted scenario, Process Runner). Navigator
   review reshaped the batch: Workload replaces "Scenario profile" (the
   FoundationDB/TigerBeetle term; `ScenarioProfile` class pending rename),
   Durability boundary replaces "Durable cut" ("cut" remains the shipped
   artifact/code spelling), and the two drivers over one World are named
   apart:  Scripted scenario (author-chosen schedule: prove known cases,
   debug, pin found bugs) vs Campaign (seed-driven exploration: hunt
   unknown cases). The boundary-faults-only rationale (mid-step crash
   instants collapse observationally into boundary outcomes) is now recorded
   in the owner doc §Durable and irreversible cuts. Timeline, JournalEntry,
   Observation, Disposition, and ScenarioRegistry stay out as implementation
   vocabulary.
4. ~~Net document family~~:  ruled 2026-08-31, Navigator-accepted after a
   naming session: Net document (envelope; "Net Schema" rejected as
   overloading the schema sense), Layout (was portable view; "viewport"
   rejected as meaning the visible window), Net identity (was definition
   identity), Timeline (was execution lineage; forks into parallel
   timelines; boundaries versus History and spawn/Thread lineage). Pending
   renames now include `PortableViewV1`, `ExecutionLineage`/`LineageEntry`,
   and the DST `Timeline` authoring facade. The specification prose sweep
   completed on 2026-09-08; the serialized fields and Python names remain intact.
5. Engine surface verbs:  Action, Snapshot, DriveOutcome, AcceptDelivery…;
   the old CONTEXT.md entry has been retired. Review the current Engine
   glossary and specification for the remaining post-split action vocabulary.
6. Overloaded words needing Avoid/qualification rulings: delivery,
   execution, lineage, view, snapshot, profile, attempt, command.
   ~~territory~~:  ruled 2026-09-03, Navigator-accepted: Execution
   territory glossary entry anchored in the Motus execution contract
   (`src/petrus/motus/execution/__init__.py`) and the
   episode-owns-independent-execution-territory decision; bare
   "territory" blessed as the short form in Motus context.
7. ~~Undefined coined names~~:  ruled 2026-08-31: Gondolin and
   Absurd got glossary entries; orb and pi/A2 were deliberately
   excluded as incidental substrate vocabulary and vendor runtime lane
   names (same rule as claude/codex/amp). "A2" has no recorded expansion
   anywhere in the repo; capture it if it means something. Gondolin's
   entry uses "execution territory", defined by ruling 6 on 2026-09-03.
8. "Library, not framework":  already owned by the host-lifecycle principle
   in `docs/product/principles.md`; no additional definition is needed.

## 1e WS3 reader pass and Memory Closure

The first reader pass produced a runnable README, one runtime guide, current
briefing/roadmap pointers, a short engineering guide linked to all 89 preserved
review cases, and an Ariad router using the installed Memory Closure protocol.
Its [worklog evidence](../../../process/worklog/entries/2026-09-08T1508Z-codex-reader-coherence.md)
records the examples and checks executed then.

The Navigator then authorized DST consolidation and exploration closure, with
a critic for each task. The resulting ownership is:

| Task | Result |
| --- | --- |
| DST documentation | One complete World reference; compact version notes preserving old anchors; a v3 fixture index; separate runner and internal Scenario contracts. No fixture regeneration or compatibility change. |
| ES-059 and ES-061 | Experiment verdicts, costs, promotion rationale, and supersession retained. Current authoring and Net-document work points to ES-060, CV20.DS2, CV20.DS3, and the specification. |
| ES-052 and ES-060 | One paused-state entry and one ES-052 experiment plan. Source assumptions, all 16 first-experiment probes, falsifiers, later gates, and open questions retained. ES-060's benchmark decision remains pending. |
| ES-053 through ES-058 | Completed comparisons retain source provenance, useful findings, rejected approaches, and revisit conditions. ES-056 points to CV20 for delivery. Recommendations do not become accepted work through editing. |
| ES-050, ES-051, worklog, and ES-062 | Light closure makes earlier evidence and current owners explicit. Dated worklog entries remain intact; ES-062 keeps only verified outcomes and unresolved work. |

Humanizer and unslop guided the prose; small diagrams show the World inputs,
authoring/source-map relationship, and observed/manual/simulated branching.
The diagrams explain existing contracts or explicitly labeled experiments.

## 1f Verification, review, and limits

`scripts/check quick` passed lint, formatting, typing, and structural checks.
The focused command passed 99 tests with no skips:

```sh
uv run --frozen pytest -q tests/project tests/dst/test_world.py \
  tests/dst/test_replay.py tests/dst/test_process_runner.py --forbid-skips
```

Independent critic review accepted all five tasks after corrections to the
Scenario-v1 enforcement wording, inherited experiment/source pointers, dated
production observations, and prose. The final document scan checked 459
Markdown files and 666 local links with no broken targets or anchors; all 261
frontmatter documents parsed. Byte comparisons preserved 381 method,
specification, decision, worklog, and supporting exploration files, including
all 72 worklog entries. Only Markdown documentation changed.

The new reference's resource-recovery command returned `pass` / `converged`,
14 operations, and 39 journal entries. It exposed a stale digest duplicated in
the old v4 prose; exact digests now remain in the fixtures. `git diff --check` passed.

Historical research and experiment suites were not rerun; this pass changes
documentation only. The complete release gate was not rerun or represented as passing.

The documentation review reduced duplication without changing runtime behavior.
No new technical-debt item is needed for this pass; unresolved terminology,
compatibility retirement, architecture, and coverage reviews remain in the
workstreams above.

## 1g WS2 accepted-language coherence, 2026-09-08

The continuation applied the accepted Layout, Timeline, and Net identity names
to the Net document specification and its observation/simulation references.
A mapping table preserves the exact `view`/`lineage` keys and current Python
API names, and the old specification anchors still resolve.

The Timeline glossary and the August 27 decision still described the earlier
History-record/source-anchor candidate. The accepted CV20.DS3.TS2 plan and
Experience Report explicitly replace it with complete markings. The glossary
now reflects that accepted result, and a
[dated decision correction](../../decisions/records/2026-08-27T0206Z-portable-net-document-unifies-definition-view-and-lineage.md#1-coherence-correction-2026-09-08)
records supersession while preserving the original passage. This is a repair
of stale wording, not a new terminology ruling.

The World reference now distinguishes Workload from the shipped
`ScenarioProfile` name and its `Timeline` authoring class from a Net document
Timeline. Four DST glossary links now point to the complete World reference.
Public API renames remain pending and require a compatibility-aware change.

Verification passed 78 tests with no skips:

```sh
uv run --frozen pytest -q tests/project \
  tests/petrus/impetus/test_net_document.py \
  tests/petrus/impetus/test_net_document_lineage.py --forbid-skips
```

The critic accepted the terminology, authority chain, and preserved contract.
The specification's fenced examples are byte-for-byte unchanged. Code, fixture,
and installed-method files did not change. `scripts/check quick` passed, and
the scan of 459 Markdown files found all 677 local links and anchors valid.
The release gate and historical application experiments were not
rerun for this documentation correction.

Two DST glossary phrases remain for a separate definition review: World says
every run produces an artifact although construction and harness failures can
prevent one; Budget describes steps and faults while the actual deterministic
limits are more specific. Their current detailed rules remain in the World
reference. The remaining Engine vocabulary, API renames, and WS4-WS6 work
remain open.
