---
code: ES-062
title: Consolidation and coherence baseline
status: Active
status_reason: >-
  WS3 reader-facing documentation consolidation is complete. Earlier survey
  evidence and WS2 terminology rulings remain below. Runtime-format
  consolidation and unresolved design workstreams retain their own scope.
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

The Navigator requested a full reader-facing coherence pass over the README,
local Ariad guidance, and historical content. This continues WS3 through
ordinary commits. Existing Git history, decisions, and experiment evidence
remain intact. The installed Ariad package is preserved as a verified snapshot.

WS1 is complete with the corrections recorded below. WS2 has accepted glossary
rulings and still has pending vocabulary and code-name work. WS3 now covers
reader navigation, stale overview repair, and separation of current guidance
from review history. Runtime-format retirement, experiment pruning, and the
WS4–WS6 design work are not part of this documentation pass.

The survey below describes 2026-08-31. Its file counts, API names, and initial
claims are historical; the later dispositions correct findings that did not
survive verification. In particular, the bytecode files were untracked, the
compatibility module was used, and the flagged roadmap date was a template.
Use the current [briefing](../../briefing.md) and
[documentation guide](../../../README.md) for orientation.

## Inquiry

After two intense months (ES-050 through ES-061, CV8–CV19 closed, CV20
active), does the repository still cohere? Specifically: is the code aligned
with the founding vision, is the declared domain language current, does the
documentation still tell the truth, and does everything fit the DST driver
that emerged mid-project? This story is the consolidation surface: it holds
the evidence and dispositions each workstream one at a time, protecting the
Navigator's cognitive load.

## Method

Five independent read-only surveys ran in parallel on 2026-08-31 against the
working tree at `b7265ff`: package architecture, vision provenance and
alignment, declared-vs-actual domain language, DST centrality, and
documentation inventory. Findings below cite exact paths; nothing here is
speculative.

## Findings

### F1 — Vision: aligned, but the founding documents live in another repo

The first dream description is the Matt Scott call transcript at
`impetus/docs/references/2026-07-09-matt-hb-vision-call-transcript.md`
(sibling repo), with the Navigator's decomposition in
`2026-07-09-vision-themes.md` ("agents are wrongly built as imperative loops;
model coordination as a pure Petri net; the harness is the net"). Petrus
carries no copy; its only pointer is `spec/README.md:53`. The repo's own
vision (briefing, principles, roadmap) is consistent with that dream, and
CV20 Approachable Petrus is the natural next step of it. Verdict: direction
aligned; provenance not portable with this repo.

### F2 — Architecture: layered and mostly clean, with bounded drift

Layering is acyclic at package level: `impetus → engine → agenticus`, with
`motus.activity` as a shared leaf. Sizes: agenticus 46 files (~15k LOC,
largest), impetus 25 (~9k, `instance/__init__.py` alone is 2,376 lines),
tests/dst ~23.5k LOC. Concrete drift:

- `src/petrus/motus/_execution/model.py` is a self-declared compatibility
  module no code imports — dead.
- `src/petrus/processes/{postgres,spawn,call}.py` import private names
  (`_text`, `_json_object`, `_freeze_json`) from `petrus.fabric.model`.
- `tests/project/test_package_boundaries.py` carries
  `TEMPORARY_COORDINATION_EXPORTS` and `REMOVED_ROOT_EXPORTS` — an in-flight
  facade removal never finished.
- Root modules `simulation.py`/`simulation_http.py` sit above impetus+engine
  but outside any package.
- One upward edge: `agenticus/runtime/agent_net_runner.py:38` imports
  `Engine`.

### F3 — Domain language: 108 declared terms, zero for the newest domains

`CONTEXT.md` (783 lines) defines 108 terms but none for DST (World, Scenario,
Checker, ChoiceStreams, Fault, Budget, ProcessRunner…), none for the Net
document family (Net document, PortableView, ExecutionLineage, fork), and
none for the new Engine surface verbs (`AcceptDelivery`, `Snapshot`,
`DriveOutcome`…). The `Engine` entry still describes `Engine.deliver()`
although `b7265ff` split delivery into phases. Coined names lacking any
definition: Gondolin (docstring only), orb (one CONTEXT.md use), pi/A2
(code + ADRs only); Absurd has an ADR but no glossary entry. Overloaded
words needing rulings: delivery, execution, lineage, instance, process,
profile, view, snapshot, selection, attempt; plus History vs event history
(the ADR ratified "event history", CONTEXT.md says bare "History").

### F4 — DST: code aligned, process driver drifting

`src/petrus/testing/dst.py` (2,656 lines) plus `tests/dst/` (53 fixtures,
real Postgres/Absurd/ZeroMQ worlds) is real and load-bearing — HEAD's engine
change re-expanded 8 fixtures. But DST covers only the Impetus/Engine/Motus
spine: agenticus (~20k lines, the largest package), fabric, and processes
have zero simulation coverage, and CV20 plans contain no DST reference
despite DST being the declared design driver. The cross-project test-kit
promise (2026-08-17 decision) is packaged but unguarded —
`test_package_boundaries.py` never mentions `petrus.testing`. Doc lineage:
v4 is current but is a delta; v3 (905 lines) holds the substantive spec body
and is not prunable; v1/v2 are kept alive only by 5 legacy fixtures;
`dst-scenario-v1.md` is a parallel superseded format kept by one fixture —
the strongest pruning candidate.

### F5 — Documentation: large, mostly closed history, with false claims

286 markdown files. 129 decisions (117 Decided, 12 Superseded, 0 Open), 70
worklog entries, 12 explorations (10 Completed, ES-052 and ES-060 Paused),
36 roadmap files of which only CV20 is live. Bulk: ES-059 alone is 2.9M of
the 3.4M exploration tree, including 52 committed `.pyc` files.
`engineering-conventions.md` (1,214 lines) restates ~90 conventions, several
now enforced mechanically by `rules/` + `sgconfig.yml`. Statements that are
now false: `spec/OVERVIEW.md` says "65 decision records" (129) and asserts a
stdlib `unpack` handler exists (only `passthrough` does —
`src/petrus/impetus/binding/__init__.py:364`); `docs/ariad/index.md:12` says
the worklog "currently has no entries" (70) and that reference captures are
absent (ES-059's experiment tree exists). `roadmap/index.md` frontmatter is
an unfilled template (`updated: YYYY-MM-DD`).

## Candidate workstreams

Each is sized to be dispositioned in one focused session. Order is the
Navigator's call; suggested sequence reflects risk and leverage.

1. **WS1 Truth repairs + mechanical cleanup** (no design decisions): fix the
   false claims in `spec/OVERVIEW.md` and `docs/ariad/index.md`; delete
   committed `.pyc` under ES-059; remove the dead
   `motus/_execution/model.py`; fill `roadmap/index.md` frontmatter.
2. **WS2 Glossary and domain-language ruling**: adopt the glossary-capable
   Ariad (`feat/domain-modeling-integration`, unmerged on GitHub as of
   2026-08-31); migrate CONTEXT.md terms; add the missing DST/Net-document/
   Engine vocabulary; rule on the overloaded words (F3).
3. **WS3 Documentation shrink**: archive concluded explorations' bulk,
   consolidate dst-world v1–v3 into v4 after re-expanding 5 legacy fixtures,
   retire `dst-scenario-v1`, condense `engineering-conventions.md` to what
   the mechanical gate does not already enforce.
4. **WS4 DST driver alignment**: decide whether agenticus/fabric/processes
   come under DST worlds and make CV20 stories carry DST obligations; guard
   the test-kit boundary.
5. **WS5 Architecture debt**: finish the facade removal, fix the fabric
   private-name leakage, place the root simulation modules.
6. **WS6 Python style review**: audit the codebase against the Navigator's
   python-* style skills (call sites, composition, naming, typed data,
   errors, comments, testing).

## Disposition

Open. Dispositions are appended per workstream as each is decided.

### WS1 — Truth repairs (done 2026-08-31)

Applied after re-verifying each survey claim against the working tree:

- `spec/OVERVIEW.md` no longer states a decision-record count (was "65",
  actual 129 and growing) and now says `unpack` is Decided but not yet
  implemented, matching `spec/handler-contract.md:48` and the code (only
  `passthrough` exists).
- `docs/ariad/index.md` now points at the real exploration and worklog
  surfaces instead of claiming the worklog has no entries.
- Untracked `__pycache__` noise under `docs/project/exploration/` deleted
  from disk; nothing was ever committed, so F5's "52 committed `.pyc`"
  claim was wrong — the repository history is clean.

Two survey findings did not survive verification and were re-dispositioned:

- `motus/_execution/model.py` is not dead —
  `tests/petrus/motus/test_execution_contract.py:64` imports it as a pinned
  compatibility surface. Retiring it is a decision, moved to WS5.
- `roadmap/index.md` has no unfilled frontmatter; the flagged
  `updated: YYYY-MM-DD` is the item template inside a code block. No change.

`tests/project` (29 tests, includes the conventions gate) passes.

### WS2 — Glossary (in progress, opened 2026-08-31)

Ariad updated by whole-package replacement: `using-ariad` 0.2.1 → 0.2.2 from
`https://github.com/henriquebastos/ariad`; manifest hashes verified.
`docs/project/glossary/` created from
the packaged template (one term per kebab-case file, one-or-two-sentence
definitions, optional `Avoid`/`Related`; behavior and invariants stay in
their focused owners). The Petrus router now lists the glossary surface.

Bulk migration done 2026-08-31: 127 term files created from CONTEXT.md's
accepted language, definitions distilled to the glossary format.
Compatibility-era names became `Avoid` lines instead of files (Impetus
Kernel, Petri-net core → petrinet-kernel; net instance → petrinet-instance;
schema reference → net-uri).

CONTEXT.md deleted 2026-08-31 (decision
`2026-08-31T1922Z-glossary-directory-replaces-context-md`). A coverage audit
confirmed all but six pieces of its surplus contract detail were already in
`spec/` or decision records; the six were re-homed first: token-queue
front-most-equal-occurrence removal and Sensor retain-and-re-offer →
`spec/net-schema.md`; Engine `DriveOutcome` host posture and the
`DrivingPolicy` re-ask contract → `spec/firing-semantics.md` §Scheduling;
derived-handler inhibitor exemption → `spec/handler-contract.md`; token type
ledger boundary → `**OPEN:**` marker in `spec/net-schema.md`. Spec citation
tags `[CONTEXT.md]` renamed to `[glossary]`; live references in README,
briefing, development guide, engineering conventions, the Ariad router, and
`engine/_coordination.py` retargeted. Historical mentions in older decision
records and worklog entries left as written.

Aligned to Ariad main 0.3.0 on 2026-08-31 after running its read-only
`upgrading-ariad` audit (clean: no destructive or ambiguous classes beyond
the deliberate package replacement). `using-ariad` replaced wholesale
0.2.2 → 0.3.0, manifest verified; `docs/project/glossary/index.md` updated
to the 0.3.0 template; all 127 term files converted to the 0.3.0 entry form
(`Avoid`/`Related` as bullets) with `Detail:` links to each term's owning
spec file per the dissolve coverage audit. Boundary bullets (`Use when` /
`Do not use for` / `Example`) are added opportunistically as terms are
touched, not fabricated in bulk. The audit also flagged the legacy
monolithic `briefing.md` / `development-guide.md` / `principles.md` as an
optional modular-docs migration — deferred to WS3.

Ruling backlog, one per session, Navigator-paced:

1. ~~History vs event history~~ — ruled 2026-08-31: capitalized **History**
   is canonical; "event history" stays as an acceptable descriptive long
   form. Recorded in the glossary and as a review outcome on the 2026-07-06
   record.
2. ~~Candidate Selection~~ — ruled 2026-08-31: the Navigator renamed the
   pair to **Transition Selection** (policy level; implementation:
   Transition Selector) and **Token Selection** (arc level, formerly bare
   "Selection"). Glossary terms added with mirror boundaries, spec prose
   swept, review outcome recorded on the 2026-07-22 record. Follow-up:
   code identifiers (`Scheduler`, the `petrus.impetus.selection`
   `SelectionPolicy` family) are pending rename.
3. ~~DST vocabulary~~ — ruled 2026-08-31, definitions Navigator-accepted:
   eleven terms (Deterministic Simulation
   Testing, World, Workload, Checker, Fault, Durability boundary, Choice
   streams, Budget, Campaign, Scripted scenario, Process Runner). Navigator
   review reshaped the batch: **Workload** replaces "Scenario profile" (the
   FoundationDB/TigerBeetle term; `ScenarioProfile` class pending rename),
   **Durability boundary** replaces "Durable cut" ("cut" remains the shipped
   artifact/code spelling), and the two drivers over one World are named
   apart — **Scripted scenario** (author-chosen schedule: prove known cases,
   debug, pin found bugs) vs **Campaign** (seed-driven exploration: hunt
   unknown cases). The boundary-faults-only rationale (mid-step crash
   instants collapse observationally into boundary outcomes) is now recorded
   in the owner doc §Durable and irreversible cuts. Timeline, JournalEntry,
   Observation, Disposition, and ScenarioRegistry stay out as implementation
   vocabulary.
4. ~~Net document family~~ — ruled 2026-08-31, Navigator-accepted after a
   naming session: **Net document** (envelope; "Net Schema" rejected as
   overloading the schema sense), **Layout** (was portable view; "viewport"
   rejected as meaning the visible window), **Net identity** (was definition
   identity), **Timeline** (was execution lineage; forks into parallel
   timelines; boundaries versus History and spawn/Thread lineage). Pending
   renames now include `PortableViewV1`, `ExecutionLineage`/`LineageEntry`,
   the DST `Timeline` authoring facade, and the spec/net-document-v1.md
   prose sweep.
5. Engine surface verbs — Action, Snapshot, DriveOutcome, AcceptDelivery…;
   the old CONTEXT.md entry has been retired. Review the current Engine
   glossary and specification for the remaining post-split action vocabulary.
6. Overloaded words needing Avoid/qualification rulings: delivery,
   execution, lineage, view, snapshot, profile, attempt, command.
   ~~territory~~ — ruled 2026-09-03, Navigator-accepted: **Execution
   territory** glossary entry anchored in the Motus execution contract
   (`src/petrus/motus/execution/__init__.py`) and the
   episode-owns-independent-execution-territory decision; bare
   "territory" blessed as the short form in Motus context.
7. ~~Undefined coined names~~ — ruled 2026-08-31: **Gondolin** and
   **Absurd** got glossary entries; **orb** and **pi/A2** were deliberately
   excluded as incidental substrate vocabulary and vendor runtime lane
   names (same rule as claude/codex/amp). "A2" has no recorded expansion
   anywhere in the repo; capture it if it means something. Gondolin's
   entry uses "execution territory", defined by ruling 6 on 2026-09-03.
8. "Library, not framework" — already owned by the host-lifecycle principle
   in `docs/product/principles.md`; no additional definition is needed.


## 1b WS3 reader-facing coherence pass, 2026-09-08

The documentation pass is complete. The README has a runnable first example;
the documentation guide separates usage, contribution, and historical evidence.
Advanced examples and Agenticus support limits now have one runtime guide.
The briefing and roadmap point to the completed direct-marking timeline story
and its actual remaining application-bound work.

The engineering guide is a short entry point into all 89 preserved review
cases. Their text and provisional status are unchanged. The local Ariad router
uses the installed package and its Memory Closure protocol. AGENTS.md now
correctly describes the installed method and retained experiments. The method
package, decision corpus, runtime contracts, code, tests, and experiment
artifacts are unchanged. Prose was edited for contributors who do not know the
project's session history; headings and links provide the reading path.

[Verification and review](../../../process/worklog/entries/2026-09-08T1508Z-codex-reader-coherence.md)
records executed examples, automated checks, preservation checks, and limits.

WS3's possible DST-format retirement and experiment pruning are deferred.
They require compatibility and evidence-retention decisions, not a prose
cleanup. WS2's remaining terminology rulings and code renames, plus WS4–WS6,
remain open under this exploration. The current reader pass does not mark
those workstreams complete or accept tentative domain language.
