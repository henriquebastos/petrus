# Local Development Guide

This is the project-specific operating contract for agentic development.

Ariad is the canonical method. This file is the local instance of that method for this repository. It explains how the Driver and Navigator should work here, which commands matter, what validation means, and which project-specific rules override generic guidance.

Keep this file practical. It should help a future agent work correctly in this project without asking the Navigator to repeat the same context every session.

## Relationship to Ariad

This project uses Ariad as its human-agent development method.

When Ariad and this local guide differ, follow this local guide for project-specific work and surface the difference during the coherence check.

## Driver and Navigator

The agent is the **Driver**. The human is the **Navigator**.

The Driver reads context, proposes plans, changes files, runs checks, prepares validation routes, updates documentation, and renders checkpoints.

The Navigator holds intent, trade-offs, product judgment, and acceptance.

For choices inside an accepted direction, the Driver proceeds autonomously
when at least 90% confident that the choice preserves intent, scope, and the
project contract. Below that threshold, or at an explicit stop condition, the
Driver asks one focused question. At or above the threshold, checkpoints are
visible auto-release surfaces: record the evidence and continue without waiting.
This delegation never waives approval for destructive or shared actions and
never permits inventing a Navigator ruling that was not made.

## Project Commands

Python ≥3.14, managed with `uv`. Python source lives in `src/petrus/`; tests mirror ownership under `tests/`.

- Install/sync: `uv sync`
- Focused behavior test: `uv run pytest -q PATH::NODE`
- Fast static feedback: `scripts/check quick [PATH ...]`
- Checkpoint confidence: `scripts/check full`
- Release qualification: `scripts/check release`
- Periodic semantic mutation diagnostic: `scripts/check mutation`

The full profile and release qualification's cumulative full pass run the
complete hermetic pytest suite on four bounded xdist workers, report the 20
slowest durations above 0.5 seconds, and use a short harness-owned temporary
root so Unix-domain transport tests remain below the platform socket-path
limit. Selected routine tests are forbidden from skipping: an unexpected skip
fails the gate. Explicitly marked provider, Gondolin, and exact
installation qualification tests remain separate acceptance routes and are run
by exact node under their recorded authority and environment. They are
deselected—not reported as green-suite skips—by `full` and `release`. Release
qualification then retains one serial hermetic run under its additional fixed
seed so that pass still exercises one exact global order.

The mutation profile is deliberately separate from `quick`, `full`, and
`release`. It runs mutmut over an explicit allowlist of fast pure semantic
targets and has no score threshold. Review `uv run mutmut results` and inspect a
survivor with `uv run mutmut show MUTANT_NAME`; classify `no tests` separately
instead of treating it as a survivor. In these curated targets, mutmut 3.6
skips the `@dataclass`-decorated Selection classes and `TokenQueue` properties;
supported decorators such as `@classmethod` are still mutated. This profile
therefore never represents whole-module mutation coverage. Add a target only
after a bounded probe establishes useful method coverage, direct focused
tests, and acceptable runtime.

Run `uv` frozen so routine commands never rewrite `uv.lock`: `UV_FROZEN=1` is exported in the shell profile (equivalently, pass `uv run --frozen`). A lockfile change must be a deliberate `uv add`/`uv lock`, never incidental churn from a test or lint run.

Structural code conventions are declarative ast-grep rules under `rules/*.yml` (discovered via `sgconfig.yml`). To enforce a new convention — a code-style pattern we want to forbid or require — add a rule file under `rules/`; no Python change is needed. This is the growing home for engineering conventions distilled from review.

## TDD Feedback Discipline

Use the smallest feedback loop that can disprove the change, then widen confidence deliberately:

1. **Red:** write one behavioral test and run its exact node, for example
   `uv run pytest -q tests/petrus/impetus/instance/test_feature.py::test_behavior`. Confirm that it
   fails for the intended missing behavior, not because of an import, syntax,
   fixture, or infrastructure failure.
2. **Green:** make the smallest implementation change and rerun that exact
   node. Green means the behavior that was red now passes; it does not require
   a full repository suite after every edit.
3. **Refactor:** keep the focused test green, then widen to its related test
   file(s). Run `scripts/check quick` over the touched Python paths for lint and
   formatting feedback; its type check deliberately still covers all of
   `src/petrus` so production typing remains coherent.
4. **Checkpoint:** run `scripts/check full`. This is the complete deterministic
   repository suite plus every quick check and is the required automated
   evidence before a validation checkpoint.
5. **Release:** run `scripts/check release`. It repeats the full suite under an
   additional fixed order to qualify a release artifact.

`pytest -k EXPRESSION` and `pytest --lf` are useful iteration shortcuts, but
they can omit relevant tests and therefore are not final evidence. Final
focused evidence names explicit files or node IDs before `scripts/check full`.

## Correctness-Sensitive Work

When work changes durable, concurrent, stateful, or externally effectful
behavior, follow the correctness-sketch, replay-before-fix, and regression
promotion guidance in
[`deterministic-simulation-testing.md`](deterministic-simulation-testing.md).
This is a conditional planning and evidence route inside the existing Ariad
lifecycle, not a second lifecycle or a mandatory artifact for ordinary work.

Production correctness must not depend on Python `assert`: use explicit
validation, refusal, or failure behavior because optimized Python may remove
assertions. Tests, including Hypothesis invariants, may use `assert`.

Each pytest worker that needs PostgreSQL owns one session-scoped ephemeral
container on a Docker-assigned loopback port. This isolates mutable schemas
across parallel workers while retaining the pinned image, tmpfs storage, and
fail-loud provisioning contract. Serialize a focused PostgreSQL test with the
same machine-global lock used by the full profile so focused and complete
sessions cannot remove one another's labeled harness containers:

```bash
flock --nonblock /tmp/petrus-check-full.lock \
  uv run pytest -q tests/petrus/engine/test_postgres_engine.py::TestPostgresEngineProvider::test_create_load_and_idempotent_close_own_the_joined_connection
```

If the lock is already held, wait for the owning test run to finish; do not run
a competing PostgreSQL harness session.

## Verification

For Ariad artifacts, retained records are self-contained and internally
consistent (links resolve and statuses are accurate).

Evidence-bearing artifacts (fit maps, probe reports, comparison matrices, research groundings) grade each claim by provenance, per claim, not per document — house style ratified 2026-07-13 (ES-012 D6):

- `[E]` — executable evidence: a probe/test in this repo ran it.
- `[D]` — docs-verified: checked against the authoritative source (repo, LICENSE, official docs), with date.
- `[R]` — reported: asserted by a source nobody verified; hearsay until upgraded.
- `[X]` — refuted: checked and found false (keep the entry — refutations are evidence too).

A claim's grade travels with it when quoted into other artifacts. Mixed cells spell both (`[E/R]`).

For kernel code, `scripts/check full` is the automated verification gate. It
requires the complete pytest suite—including the golden-trace replay tests in
`tests/`—to pass under the deterministic seed, Ruff lint and format checks to
be clean, `ty` to accept all production source, and ast-grep structural
conventions to pass. A conforming kernel replays a golden fixture with no
access to the Petrus engine.

Documentation parity is deliberately layered. Normative runtime behavior
belongs in executable tests and conformance fixtures. The language-neutral
`spec/` is supported by golden replay plus Impetus-native behavior tests, with
known unsupported or deferred coverage stated in the trace documentation. A
normative behavior without executable evidence is a visible coverage gap, not
verified behavior. `CONTEXT.md` is an orientation and ubiquitous-language
surface maintained through review and the coherence check; no standing gate
claims to prove its prose mechanically against implementation. The project
does not substitute a generic prose-to-code checker for behavioral evidence.

For a User Story, the Driver owns end-to-end QA and submits an **Experience Report** at the Behavior Checkpoint. The report is the routine acceptance surface and must make approval low-effort:

- concise approval-oriented summary and overall pass/fail;
- each acceptance behavior with its expectation, observed result, pass/fail status, and evidence references;
- screenshots for visual behavior and video where motion or interaction matters;
- automated checks and other relevant artifacts;
- known issues, risks, important omissions, and confidence limits;
- a Driver recommendation to accept, rework, or accept with reservations;
- the focused product, UX, taste, trade-off, or acceptance judgment requested from the Navigator;
- optional notes from manual inspection, when the Driver performed it.

Driver QA must pass before the report reaches approval. The Navigator may approve or request changes by reading the report. Navigator hands-on inspection remains available for UX exploration, product insight, taste, or additional confidence, but is not routine QA and is not a prerequisite for approval. When an inspectable route would be useful, include it as an optional route rather than assigning validation work back to the Navigator. If the Driver is technically unable to execute a required check, the report states exactly what could not be checked, why, the resulting confidence limit, and the smallest specific Navigator exception needed.

For a kernel slice, the Driver's evidence includes `uv run pytest` with all tests green and the slice's target golden fixture(s) replaying step-for-step; a failure is any assertion mismatch on consumed/produced tokens, marking, enabled set, or derived status.

## Documentation Rules

Describe when documentation must be updated.

Common documentation surfaces:

- `README.md`
- `docs/project/briefing.md`
- `docs/project/decisions/index.md` and `docs/project/decisions/records/`
- `docs/project/roadmap/index.md` and roadmap item folders
- `docs/project/debt/index.md` and `docs/project/debt/items/`
- `docs/process/engineering-conventions.md`
- `docs/process/worklog/index.md` (template; historical entries are not included)
- `docs/product/principles.md`

## Agent Memory Mirrors Repo Docs

An agent's private/persistent memory (any harness's `MEMORY.md`, notes, or recall
store) is a **convenience pointer, never a source of truth**. Anything durable enough
to keep in agent memory must also exist in repo documentation, because the project
does not assume any single agent harness — a different agent, or a human, must be able
to recover the same knowledge from the repo alone. Navigator rule, 2026-07-09.

## Conflict-Resistant Project Memory

Use one file per durable artifact when the surface may be edited by multiple people or agents.

- Worklog milestones live in `docs/process/worklog/entries/`.
- Decision records live in `docs/project/decisions/records/` and use `status` for open or decided lifecycle state.
- Debt items in the Technical Debt Ledger live in `docs/project/debt/items/`.
- Roadmap items own their current `status` in frontmatter or in their own file, not in a central table.
- Exploratory Stories own state in `docs/project/exploration/es-<code>-<slug>/`.
  Their `ES-<N>` codes use the monotonic allocation contract in the
  [Exploration index](../project/exploration/index.md): previously allocated codes through
  `ES-049` remain reserved, codes are never reused, and the index's one
  `next_code` coordination field advances in the same commit as a new story.

Index files explain structure, naming, and templates. They should not maintain complete lists of every artifact unless this project explicitly accepts that coordination cost.

The Exploration `next_code` field is an explicit exception to the default
against central mutable state. It is one mechanically checked allocation
coordinate, not a status registry or complete story list; story directories
remain authoritative. This small coordination cost prevents a pruned or
partially retained history from silently restarting the namespace.

Prefer status metadata over directory moves for lifecycle state. Directory moves are acceptable for archival or deliberate reorganization, but state should remain explicit in the artifact so links and history stay understandable.

## Roadmap Taxonomy

Use Ariad's default taxonomy unless this project explicitly adapts it:

- Value / CV: major delivery stage with clear impact.
- Delivery Story: coherent delivery arc inside a Value / CV.
- User Story: atomic user-observable delivery that can be verified end to end through observable behavior or capability. For non-UI work, the validation route may be a dry-run, diagnostic, operation report, generated artifact, documented policy, runtime state, or other inspectable output.
- Technical Story: internal capability needed by a Delivery Story, still verified but not necessarily Navigator-visible by itself.
- Task: concrete work inside a User Story or Technical Story.
- Maintenance: legitimate work that may sit outside roadmap structure.

Do not inflate maintenance into the roadmap just to make it visible.

Use Ariad's default new-work codes unless this project explicitly adapts them:
`CV<N>` for Values, `DS<N>` for Delivery Stories, `US<N>` for User Stories,
and `TS<N>` for Technical Stories.

Use Ariad's default roadmap states unless this project explicitly adapts them: `Planned`, `Active`, `Blocked`, `Validated`, `Done`, `Deferred`, and `Dropped`. Store state in the roadmap item's own metadata or status section. When work cannot proceed, prefer `Blocked` with a reason over runtime warning labels such as `Attention`.

## Expand and Collapse

Use expand when work is blocked by ambiguity: separate concerns, name options, clarify scope, or expand a Delivery Story into User Stories.

Use collapse when work is lost in fragments: relate parts, update status, name emergent value, close a User Story or Technical Story, close a Delivery Story, or prepare a release boundary.

## User and Technical Story Lifecycle

For non-trivial work, follow the Ariad lifecycle:

- plan,
- name User Story acceptance behavior, preferably as Given / When / Then / And,
- implement,
- test and validate,
- document,
- review and coherence check,
- record project history according to the configured commit policy.

User Stories and Technical Stories have distinct evidence gates:

- a Technical Story may close on complete internal technical evidence;
- a User Story reaches the Behavior Checkpoint only after Driver-owned QA produces a passing Experience Report; Navigator approval or rework is based on that report, with manual Navigator inspection optional.

A Behavior Checkpoint parks only its affected story passage. Other parents and unrelated work continue subject to their own local WIP limits.

## Technical Debt Tracking

Use the Technical Debt Ledger at `docs/project/debt/`, with debt items in `docs/project/debt/items/`, when debt should outlive one story's review notes.

During Review, name:

- debt paid;
- new debt introduced;
- debt carried forward;
- revisit trigger;
- whether a debt item should be created or updated in the Technical Debt Ledger.

Small local debt can be captured as follow-up. Debt that may affect future delivery, safety, maintainability, validation, operation, or product coherence should enter the ledger.

## Checkpoints

Render these checkpoint surfaces:

- after the Plan Checkpoint surface is shown; creating `plan.md` does not replace the visible checkpoint,
- at the Behavior Checkpoint, after Driver-owned QA, with a concise Experience Report containing enough behavioral and artifact evidence for report-based approval or rework; an optional inspection route may be included when useful,
- after review and refactoring assessment,
- before recording project history unless the local commit policy says otherwise.

At 90% or higher confidence, record the Driver recommendation and automatically
continue through the next phase. Below 90%, at an explicit stop, or when a
destructive/shared action needs approval, stop for Navigator confirmation. A
later Navigator message may veto or redirect work already auto-released.

## Navigator Preferences

Ariad ships with opinionated defaults. Override them here when this project or Navigator has a better local answer.

- **Commit policy:** default is to commit after a coherent story or meaningful change is validated and accepted.
- **Push policy:** default is to ask before pushing to a shared remote.
- **Checkpoint progression:** render full checkpoints for non-trivial work and auto-release them at 90% or higher confidence; compress only trivial low-risk changes.
- **Documentation detail:** default is the smallest documentation update that keeps the project coherent.
- **Worklog policy:** default is to record meaningful milestones as one file per entry, not every edit.
- **Branch/PR habits:** work directly on the default branch for now; revisit when there is code and/or collaborators. *(Ariad default pending Navigator confirmation.)*
- **Driver-executed validation:** the Driver runs both automated QA and the concrete operation/behavior route, then reports observations and a pass/fail verdict. Do not assign routine validation back to the Navigator. Hands-on Navigator inspection is optional only when the Navigator requests it.

## Commit and Release Rules

Commit on the default branch after each validated, coherent change. Ask before pushing to a remote. No versioning or release scheme exists yet — define it when the first runnable artifact appears.

## Local Exceptions

- **Everything is tracked, including pre-code work.** The Navigator requires that organization, exploration, spikes, experiments, and discussions all produce Ariad artifacts (Exploratory Stories, experiments, decision records, worklog entries) and get committed. "It was just a spike" is not a reason to leave work untracked. See decision record `docs/project/decisions/records/2026-07-06T1336Z-track-everything-via-ariad.md`. Revisit if artifact volume becomes ceremony that slows exploration.
