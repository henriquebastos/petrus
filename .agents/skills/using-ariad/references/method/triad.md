# Process, Project, Product

Ariad keeps three dimensions visible: **Process**, **Project**, and **Product**.

Most agentic failures are not caused by bad code generation. They are caused by separation. The implementation moves, but the process that governs it does not. The project records one state while the product behaves differently. The product direction changes, but the roadmap and decisions stay frozen. The repository keeps files, but loses coherence.

The triad is the method's basic map for preventing that split.

## Process

**Process** is how the work is done.

It includes roles, lifecycle, checkpoints, validation habits, documentation rules, versioning, release discipline, and the collaboration contract between Driver and Navigator.

Process answers questions such as: should the Driver stop before implementation? What counts as validation? When should documentation change? What must happen before a commit? How does the agent know whether it is allowed to continue?

## Project

**Project** is the current construction context.

It includes architecture, roadmap, decisions, constraints, tasks, worklog, repository state, known risks, and the history needed for the next session to resume without starting from zero.

Project answers questions such as: what are we building now? Why did we choose this direction? What is already done? What is intentionally postponed? What should not be re-litigated in every session?

## Product

**Product** is the thing being made and the experience it creates.

It includes behavior, users, principles, promises, interface contracts, quality expectations, and the difference between a technically correct change and a change that actually belongs.

Product answers questions such as: who is this for? What should it feel like? Which trade-offs preserve the promise? What would make this implementation coherent or incoherent from the user's point of view?

## Coherence

The Driver uses the triad as a coherence check throughout the work.

A code change may require a roadmap update. A new operating rule may require an `AGENTS.md` update. A product behavior change may require documentation, tests, and a decision record. A failing validation may reveal that the implementation is correct in the repository but wrong for the product.

The triad does not add ceremony. It prevents amnesia. A project stays whole when process, project, and product remain connected while they change.
