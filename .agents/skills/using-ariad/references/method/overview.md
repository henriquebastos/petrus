# Overview

Ariad is a method for working with coding agents while preserving the integrity of the work.

The method begins with a distinction: a repository is not the same thing as a project. The repository contains files. The project contains intention, history, constraints, product judgment, unresolved questions, and the reasons behind the current shape of the code. Coding agents are very good at changing repositories. They need a method to participate in projects.

That method must protect continuity. Agentic work can produce a strange failure mode: the work accelerates, but the project becomes less intelligible. A change lands without its decision. A test passes without a validation route. Documentation is updated in one place and contradicted in another. The next session starts with impressive code and weak memory.

Ariad treats coherence as part of the work, not as polish after the work. The agent reads before acting, preserves signals before they vanish, plans before implementing, validates before closing, documents before forgetting, and stops where human judgment belongs. The human does not micromanage every edit; the human navigates direction, trade-offs, product sense, and acceptance.

The core operating model is small. The agent is the Driver. The human is the Navigator. The work is held across Process, Project, and Product. Documentation becomes the project's memory surface.

Ariad then distinguishes three kinds of work.

**Exploratory Work** happens when something matters before it is ready to become a delivery commitment. A signal appears, a friction repeats, an inquiry opens, an experiment teaches something, or a candidate begins to form. [Exploration](../exploration/index.md) keeps that material visible without forcing it into the roadmap too early.

**Delivery Work** happens when intent has enough form to become verified change. A story is bounded, planned, implemented, tested, validated, documented, reviewed, and recorded in history. [Delivery](../delivery/index.md) keeps that change small enough to finish and coherent enough to trust.

**Refinement Work** happens when existing capability needs care. A bug arrives, a surface feels confusing, a test gap appears, documentation drifts, or use reveals polish that should not become roadmap noise. [Refinement](../refinement/index.md) keeps requested changes visible and validated without inflating them into delivery promises.

The passage between the three matters. Exploration protects discovery from premature commitment. Delivery protects commitment from becoming vague motion. Refinement protects care from becoming either invisible improvisation or roadmap inflation. A candidate crosses from Exploration into Delivery only when the Navigator accepts that it has enough form. A requested change crosses into Refinement when the Navigator can name the existing capability being cared for.

Ariad is runtime-independent. Its portable distribution is the standard `using-ariad` Agent Skill; runtimes may discover or install that package in different locations. Mirror Mind and its Maestro extension are optional adapters, not prerequisites or alternate method authorities.

The result is not a heavier process. It is a way to let acceleration keep its memory.
