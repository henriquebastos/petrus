# Memory Closure

Memory Closure is Ariad's cross-work-area protocol for releasing short-term agent context without making the project forget.

An agent session accumulates plans, observations, command output, rejected alternatives, partial explanations, and temporary reminders. Most of that material should not survive. The part that changes project truth must move into its smallest durable owner before the context disappears.

Memory Closure does not preserve a conversation. It **promotes durable meaning, records coherent history, points to what remains active, and discards the rest**.

## Relationship to Work Closure

Memory Closure and work closure are related but different.

- A User Story, Technical Story, Refinement Story, Change Request, or Exploration handoff closes according to its own lifecycle.
- Promote durable meaning during normal lifecycle closure. Run the complete Memory Closure protocol when short-term context must be released, including when release coincides with a lifecycle boundary.
- Memory Closure does not declare unfinished work done, authorize a commit, or bypass a Navigator checkpoint.
- A session may close while its work remains active, blocked, dirty, or awaiting validation. The durable project state must say so truthfully.

This protocol applies across Exploration, Delivery, and Refinement. Runtimes may automate or render it, but it does not require Mirror, Maestro, or any other runtime.

## Triggers

Run Memory Closure when any of these occurs:

- a lifecycle closure coincides with context release or leaves durable meaning that its normal closure did not absorb;
- the Driver is about to end, pause, compact, or hand off a session;
- the context window is becoming crowded enough to threaten relevant reasoning;
- work moves to another agent, thread, runtime, or human;
- an investigation produces durable findings even when no code changes;
- interruption would otherwise leave accepted direction, evidence, or risk only in conversation.

Do not wait for context exhaustion. Close memory at the last coherent boundary where the Driver can still distinguish durable meaning from conversational residue.

Do not create a second closure ceremony. When a work-closure surface already contains the required repository state, durable-memory pointers, verification, unresolved concerns, next movement, and history state, fold Memory Closure into that surface instead of emitting another receipt.

## Promotion Test

For each piece of short-term context, ask:

1. **Will a future Driver act incorrectly or repeat meaningful work if this disappears?**
2. **Does an authoritative project record or committed Git history already preserve it?**
3. **What is the smallest authoritative owner?**

If the first answer is no, discard it. If the second answer is yes, point to the owner rather than copying it. If it must survive and has no owner, promote it once.

If no authorized durable owner exists, do not invent one. Mark context release **not safe** until the project or Navigator establishes an owner.

| Short-term material | Durable owner |
| --- | --- |
| Current project, product, architecture, environment, or process truth | The focused current document that owns that truth |
| Consequential accepted choice and rationale | Decision record |
| Planned, active, blocked, deferred, or completed work state | Owning roadmap, Workbench, Change Request, Refinement Story, or issue record |
| Meaningful completed operational milestone | Worklog entry |
| Structural cost that must outlive the current work | Debt item with carrying reason and revisit trigger |
| Unformed but valuable signal, tension, hypothesis, or discovery | Exploration |
| Public behavior, usage, or operational contract | Product specification, README, operator documentation, or other owning surface |
| Verification that future work must be able to inspect | Owning work record, worklog milestone, release evidence, or another project-defined evidence surface |
| Ordinary implementation evolution | Authorized Git commit and diff history |
| Consequential explanation for an ordinary code change | Commit message; use a decision only when the rationale must be independently discoverable |
| Rejected scratch work, superseded narration, raw command output, and conversational repetition | Discard |

Git is durable history, but it is not the owner of every kind of meaning. Keep current truth readable in current documents, and use decision records when future contributors should discover rationale without reconstructing it from diffs.

The working tree and index are inspectable operational state, not durable Git history. Staged, unstaged, and untracked changes may disappear when a worktree, machine, orb, or runtime is released.

## Protocol

### 1. Establish Repository Reality

Inspect the state that the next Driver will inherit:

- repository, branch, and HEAD;
- staged, unstaged, and untracked changes;
- whether the receiving Driver is guaranteed to inherit this exact worktree;
- active work item and lifecycle state, when one exists;
- accepted Navigator direction not yet represented durably;
- completed and incomplete validation;
- blockers, debt, follow-up, and recovery concerns.

Do not describe unfinished or uncommitted work as recorded history.

### 2. Inventory Transient Meaning

Review the session for material that might need promotion:

- changed facts or contracts;
- accepted decisions and constraints;
- work-state transitions;
- findings that alter the next action;
- validation and failure evidence;
- debt or risk that must survive;
- valuable signals outside the current scope.

This is a semantic inventory, not a transcript summary.

### 3. Promote into Existing Owners

Update only the smallest surfaces needed to make project memory true. Prefer an existing work item, focused current document, decision, debt item, exploration record, specification, or worklog entry over creating a new category.

Do not create a worklog entry for every session. Do not create a decision record for ordinary implementation. Do not copy the same conclusion into the briefing, roadmap, worklog, and a handoff file.

Do not publish planned, interrupted, or unvalidated behavior as established current truth. Keep it in the owning active-work surface until its lifecycle makes it current. A project should state where Refinement state lives—repository Workbench, issue tracker, or another project-owned surface—so active Change Requests remain recoverable.

### 4. Remove Duplication and Stale Current State

Check that promoted information has one authoritative owner and that indexes remain routing surfaces rather than mutable history ledgers. Replace stale current truth instead of appending versions to the same policy document. Let Git retain the old text.

When a durable record links to detail elsewhere, preserve the link and a concise conclusion rather than copying the full evidence.

### 5. Check Coherence and Retrieval

Verify that Process, Project, and Product agree with the resulting state. Check that:

- links and status metadata point to real owners;
- active or blocked work is discoverable;
- decisions, debt, and follow-up are not stranded in conversation;
- validation claims match executed evidence;
- a future Driver can find detail progressively from project indexes and Git.

### 6. Record History According to Project Policy

If this is a configured commit boundary, the work satisfies that boundary's lifecycle requirements, and commit authorization is present, record a commit whose message explains why the project changed. Add a worklog milestone only when the milestone itself deserves a durable operational narrative.

At that boundary, if commit authorization is required but absent, stop before committing and report the proposed history action. Treat push as a separate policy and checkpoint: absent push authorization never prevents an otherwise authorized local commit. If this is not a configured commit boundary, leave the work in its truthful lifecycle and working-tree state. Memory Closure does not create a commit or push boundary.

### 7. Emit a Compact Closure Receipt

End with a concise Navigator-facing receipt:

```text
Memory Closure
repository: <branch @ HEAD>
boundary: <session ended, paused, compacted, handed off, or work closure already performed>
work state: <lifecycle state and owning record>
working tree: <clean, or staged/unstaged/untracked path summary>
durable memory: <paths or commit that now own the meaning>
verification: <decisive result and evidence pointer, or explicitly incomplete checks>
unresolved: <owner pointer, or none>
next: <one coherent movement and its owner>
history: <commit, proposed commit, or why none>
context release: safe | not safe — <reason>
```

The receipt is a conversation or runtime surface by default, not another project file. Persist it only when the project has an explicit handoff surface or its content qualifies as a meaningful worklog milestone. Use pointers instead of repeating the durable records.

When Memory Closure coincides with an existing story, refinement, exploration, or release closure, add only missing receipt fields to that surface. Do not render both.

## Context-Release Condition

Short-term context is safe to release when:

- every consequential item was promoted to one durable owner, retained under the dirty-release rule below, or deliberately discarded;
- repository and lifecycle state are truthful;
- verification and unresolved risk are explicit;
- history policy was followed or the pending checkpoint is visible;
- the next coherent movement is named;
- the next Driver can recover detail through project indexes, linked records, Git, and any guaranteed dirty-state transfer without needing the transcript.

If any accepted decision, critical evidence, active blocker, or necessary next step still exists only in conversation, context release is not safe.

Dirty context release is safe only when all of these hold: the owning work surface records intent, lifecycle state, blockers, and next action; the receipt names staged, unstaged, and untracked paths; and either the receiving Driver is guaranteed to inherit the same worktree or an authorized durable checkpoint or project-defined handoff surface preserves every consequential uncommitted change. Inherited dirty state is short-term operational transfer, not durable Git history or transferable long-term memory. Otherwise, mark context release **not safe**.

## Progressive Resume

The next Driver should reconstruct working context rather than reload historical conversation:

1. Read the project instruction entrypoint and load Ariad.
2. Inspect branch, HEAD, working-tree state, and recent relevant commits.
3. Read concise current briefing and local process/product indexes.
4. Find active or blocked work through owning status metadata, including the project's configured Refinement owner.
5. Follow links only to decisions, debt, exploration, worklog, specifications, and evidence relevant to that work.
6. Confirm the next movement against current repository reality before acting.

Do not read every historical record by default. Progressive retrieval is part of memory protection: indexes orient, current records focus, and Git supplies detail on demand.

## Anti-Bloat Invariants

- Preserve durable meaning, not the transcript.
- Store a fact or rationale once and link to it elsewhere.
- Keep current truth current; let Git preserve superseded text.
- Use worklogs for meaningful milestones, not session exhaust.
- Use decisions for consequential rationale, not routine implementation.
- Keep raw command output transient unless it is required evidence.
- Never treat an uncommitted working tree as transferable long-term memory.
- Do not create version-suffixed current documents or generic session-summary files by default.
- Do not preload all durable memory into the next context; retrieve progressively.
- Closure quality is measured by recoverability with less context, not by the volume preserved.
