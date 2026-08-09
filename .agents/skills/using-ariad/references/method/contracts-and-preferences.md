# Contracts and Preferences

Ariad is opinionated, but not every opinion has the same authority.

This distinction is connected to Ariad's [methodological roots](methodological-roots.md): XP contributes small verified change and feedback discipline; Kanban contributes visible work, explicit policies, and limits against uncontrolled scope expansion.

The method ships with a recommended way to work because a method that begins completely neutral asks the Navigator to design a process before experiencing one. New users should be able to start with Ariad's defaults and get coherent behavior immediately.

At the same time, Ariad should not confuse every recommended habit with an invariant of the method. Different Navigators, teams, and repositories may have different commit rhythms, push rules, branching habits, documentation detail levels, or checkpoint compression preferences.

The distinction matters because Ariad is meant to preserve coherence, not to turn one person's habits into universal law.

## Method Contract

The **method contract** is the part of Ariad that makes Ariad itself.

These are invariants:

- the agent is the Driver;
- the human is the Navigator;
- the Driver reads before acting;
- non-trivial work is planned before implementation;
- the Driver protects scope and does not silently absorb new work;
- validation is part of delivery;
- user-visible or product-visible work needs a concrete validation route;
- documentation is updated when project truth changes;
- coherence is checked across Process, Project, and Product;
- the Navigator retains judgment, trade-offs, and acceptance;
- project history should record intention, not just file changes.

Changing these does not merely customize Ariad. It changes the method.

## Navigator Preference Defaults

**Navigator preference defaults** are Ariad's recommended starting posture for how the method is practiced.

They are opinionated defaults, not universal truths. They exist so a new user can begin without designing a process from scratch.

Recommended defaults:

- use the full checkpoint cycle for non-trivial work;
- compress checkpoints for trivial work only when the change is low-risk and easy to inspect;
- commit after a coherent story or meaningful change has been validated and accepted;
- ask before pushing to a shared remote;
- keep commits small enough to review and meaningful enough to explain;
- write commit messages that explain why the change exists;
- update the smallest documentation surface that keeps the project coherent;
- record worklog entries for meaningful milestones, not every edit;
- capture follow-up work instead of expanding the current story silently.

These defaults are part of Ariad's out-of-the-box experience. A project or Navigator can override them when there is a better local answer.

## Navigator Preferences

**Navigator preferences** are deliberate local choices about how the Navigator wants work conducted.

Examples:

- commit after every codebase change;
- commit only at the end of a story;
- push after every accepted story;
- push only at a Delivery Story boundary;
- never push without explicit confirmation;
- use compressed checkpoints for documentation-only work;
- require full checkpoints for every code change;
- keep worklog entries terse;
- maintain detailed worklogs for audit-heavy projects.

Preferences should be explicit when they affect agent behavior. If they are not written down, the Driver should use Ariad defaults and surface uncertainty when it matters.

## Project Contract

The **project contract** is the public operating agreement of a repository or team.

It belongs in project files such as `AGENTS.md`, `CLAUDE.md`, the focused current-policy documents under `docs/process/development-guide/`, contribution docs, CI rules, release instructions, or team agreements.

Project contract examples:

- required commands before a story is done;
- branch naming rules;
- pull request policy;
- release process;
- mandatory CI checks;
- documentation surfaces that must be updated;
- privacy or security constraints;
- whether the repository publicly adopts Ariad.

A Navigator preference can become part of the project contract, but only when the project chooses to make it public and durable.

## Workspace Overlay

A **workspace overlay** is a local runtime configuration that guides work without changing the repository contract.

Use a workspace overlay when a Navigator wants Ariad to govern local Builder Mode sessions without imposing Ariad on every contributor to the repository.

A useful rule:

> Ariad may govern local conduct. Project docs should record truths about the project. Repository contract files should change only when repository adoption is explicitly desired.

## How the Driver Should Resolve Conflicts

When instructions differ, use this order:

1. hard safety constraints and explicit Navigator instructions for the current session;
2. project contract;
3. configured Navigator preferences;
4. Ariad preference defaults;
5. general Ariad guidance.

If following one layer would violate a higher layer, stop and surface the conflict.

## Why This Separation Exists

Ariad needs a spine and a skin.

The spine is the method contract: the small set of invariants that protects coherence.

The skin is configurable: the local habits, policies, rhythms, and preferences that make the method livable in a real project.

A method without a spine becomes vibes. A method without skin becomes bureaucracy.
