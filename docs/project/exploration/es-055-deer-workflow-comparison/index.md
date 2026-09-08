---
code: ES-055
status: Completed
opened: 2026-08-13
related:
  - docs/product/principles.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
  - docs/project/decisions/records/2026-08-03T2130Z-flat-json-is-the-canonical-net-definition-interchange.md
  - docs/project/decisions/records/2026-08-05T0923Z-net-owned-pi-loop-mirrors-a-bounded-public-seam.md
source_repository: https://github.com/deerwork-ai/deer-workflow
source_revision: b20823012eeec15d41f4969f09964401e00f56e0
---

# 1 Deer Workflow comparison

## 1a Conclusion and baseline

Deer offers a short author/run/observe path around complete coding-agent
subprocesses. Petrus can learn from that experience while retaining explicit
Net semantics, durable History, and Activity custody. The comparison completed
without an implementation candidate.

The source review inspected [Deer Workflow at `b208230`](https://github.com/deerwork-ai/deer-workflow/tree/b20823012eeec15d41f4969f09964401e00f56e0)
on 2026-08-13. It covered documentation, code, tests, examples, metadata, and
history. `[D]` below means inspected source, `[E]` executed Petrus evidence,
and `[I]` an inference for Petrus. Findings refer to that revision.

## 1b Mechanisms worth comparing

| Concern | Inspected Deer behavior | Petrus lesson |
| --- | --- | --- |
| Authoring | [`workflow.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/flow/workflow.ts) runs ordinary TypeScript control flow with process-local context. `[D]` | A small frontend can improve first motion; canonical topology and recoverable state must still come from Net and History. `[I]` |
| Concurrency | [`parallel.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/flow/parallel.ts) and [`pipeline.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/flow/pipeline.ts) start unbounded Promise work and convert exceptions, including cancellation, to `null`. `[D]` | Preserve explicit joins, bounded admission, and typed failure/cancellation. |
| Presentation | [Typed events](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/events/types.ts) feed JSONL, print mode, and TUI. Synchronous listeners can slow or break execution; one mutable phase races across branches. `[D]` | Share a read-only consumer protocol and keep observer failure off the execution path. Grouping is presentation, not another state owner. |
| Agent calls | [Agent interface](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/agents/types.ts) wraps a complete CLI loop. Adapters use stdin prompts, argument arrays, cleanup, and installation errors. `[D]` | Profile-specific convenience can remain small after authority, Hands, and Continuation are resolved. Avoid a falsely universal agent object. |
| Generated source | `skills/workflow-creator/` teaches one source-file route without automatically running it. `[D]` | Keep generation, inspection, validation, and execution separate. Examples and generator guidance should consume one API contract. |

Deer's JSONL output has no reader, replay, checkpoint, migration, or durable
state reconstruction contract. The inspected runtime has no explicit graph,
workflow scheduler, durable retry, human-wait, workflow deadline, or workflow
cancellation protocol. Per-agent cancellation does not establish sibling or
process-tree containment. `[D]`

Sandbox names map to different provider capabilities. The Pi adapter adds raw
flag and path/symlink checks, while arbitrary workflow code remains trusted
local TypeScript. Subprocess environment inheritance and a static cast of
structured output do not establish authority isolation or runtime result
validation. The `agent()` convenience was Codex-specific despite other adapter
options. `[D]`

## 1c Meaning retained for Petrus

1. Present one worked path through create, advance, wait, resume, inspection,
   and final result. The earlier review found this missing. The current
   [README](../../../../README.md) now supplies a small runnable token flow;
   [CV20](../../roadmap/cv20-approachable-petrus/index.md) owns the broader journey.
2. If a CLI or live view is commissioned, specify result/progress channels,
   JSONL schemas, provenance, and observer failure behavior. Reuse current
   [runtime](../../../runtime-guide.md) and observation contracts rather than
   adding a second semantic event log.
3. Higher-level sequence, fan-out, pipeline, and join notation must compile to
   explicit Net semantics. A view or helper cannot make a call stack canonical.
4. Keep provider schema hints separate from validation of actual results;
   preserve structured failure and provider-specific authority/cleanup limits.
5. Keep clients, credentials, host supervision, and deployment outside the
   flow. A generated frontend must not auto-execute or infer hidden topology
   from matching Python types.

The accepted [progressive-disclosure direction](../../decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md)
now owns that general product constraint. This comparison remains evidence for
adoption and presentation choices, not a duplicate delivery plan.

## 1d Historical verification and revisit

The August 13 review ran `scripts/check quick`; Ruff lint/format, production
typing, and structural checks passed. It inspected Deer tests but did not
establish a deployed durability guarantee. Source/test size comparisons and
missing README behavior described that earlier revision.

Revisit the comparison when a concrete first-run, authoring-assistance,
presentation, or provider-composition task needs it. Do not copy unbounded
fan-out, failure-as-null, shared mutable phases, synchronous semantic observers,
or private upstream loops. Substantial source reuse requires preserving Deer's
MIT notice and updating Petrus's third-party boundaries; these design lessons
require no code copy.
