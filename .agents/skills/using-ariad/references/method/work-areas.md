# Work Areas

Ariad distinguishes three kinds of agentic software work: **Exploratory Work**,
**Delivery Work**, and **Refinement Work**.

This distinction is part of the method, not a runtime state model. Runtimes may
implement work areas as modes, lanes, or surfaces, but Ariad defines the
methodological fields of work.

## Exploration

**Exploration** preserves and thickens signals before commitment.

Exploration begins when something might matter before it is clear enough for
delivery or refinement. A new idea appears and needs to be worked through. A
promising direction reveals itself in the product. A bug is noticed but not
understood. A repeated tension appears across sessions. A product discomfort
keeps returning. A methodological gap is felt before there is a proposal. The
work is real, but it does not yet have enough form to become a commitment.

Exploration is centered on the **Exploratory Story**.

An Exploratory Story is for sensemaking. It gathers signals, facts, tensions,
hypotheses, experiments, contradictions, and interpretations until the material
gains enough form to become a candidate for Delivery, a requested change for
Refinement, or loses relevance and moves to archive.

Progress in Exploration is not completion of a target. It is condensation of
meaning.

## Delivery

**Delivery** turns formed intent into verified change.

Delivery begins when the work has enough form to become a bounded roadmap
commitment. A Delivery Story names the delivery arc. It is expanded into User
Stories and Technical Stories that can be planned, implemented, validated,
documented, reviewed, checked for coherence, and recorded in history. The work
may come from a direct request, roadmap item, known bug, or candidate promoted
from Exploration.

Delivery is centered on the **Delivery Story** as an arc of delivery.

User Stories and Technical Stories give the Driver and Navigator recognizable
units of implementation with intent, scope, validation, documentation, review,
and closure.

Progress in Delivery is not activity. It is coherent collapse: the point where
the change becomes intelligible, validated, documented, coherent, and ready to
enter project history.

## Refinement

**Refinement** cares for existing capability.

Refinement begins when the Navigator can name a requested adjustment to
something that already exists. A lifecycle surface feels confusing. A command
has a local bug. Documentation has drifted. A test gap is visible. A small
refactoring would make the current behavior safer. The work is concrete enough
to change, but it should not be inflated into roadmap delivery unless it grows
into a new promise, public contract, or broad architecture arc.

Refinement is centered on the **Workbench**.

The Workbench holds **Change Requests** and **Refinement Stories** outside the
roadmap. A Change Request says what should change. A Refinement Story tells the
story of a refinement arc and is the unit that flows through Refinement Work.

Progress in Refinement is not novelty. It is improved habitability: the existing
capability becomes clearer, safer, smoother, better tested, or easier to use.

## Passage between work areas

Exploration, Delivery, and Refinement are connected, but they should not collapse
into each other. All three work areas use the [expand/collapse](expand-collapse.md)
rhythm differently.

Exploration protects discovery from premature commitment. Delivery protects
commitment from vague motion. Refinement protects care from invisibility and
roadmap inflation.

A candidate crosses from Exploration into Delivery only when the Navigator
accepts that it has enough form to become roadmap work. Until then, the material
can remain exploratory without becoming roadmap noise. Once accepted into
Delivery, the work receives a place in the
[roadmap taxonomy](../delivery/roadmap-taxonomy.md): usually Delivery Story
first, then User Stories and Technical Stories. Direct promotion to one User
Story is the exception for candidates that are already one behavior-sized unit.

```text
signal -> Exploratory Story -> candidate -> Delivery Story -> User/Technical Stories -> verified change
```

A candidate crosses from Exploration into Refinement when it becomes a requested
change to existing capability rather than a new delivery promise.

```text
signal -> Exploratory Story -> Change Request -> Refinement Story -> validated refinement
```

Some Refinement begins directly from a clear Navigator request. In that case the
runtime may create a Refinement Story with one Change Request and pull it
immediately.

```text
direct request -> Change Request -> Refinement Story -> validated refinement
```

The passage is not mandatory. Some exploratory material pauses or archives. Some
delivery work begins directly from a clear Navigator request. Some refinement
work begins as a quick adjustment. The method only requires that the Driver
preserve the boundary: do not turn uncertainty into commitment silently, do not
let delivery dissolve back into open-ended exploration, and do not inflate local
care into roadmap structure without Navigator intent.

## Memory across work areas

[Memory Closure](memory-closure.md) applies across all three work areas. It runs
when work or a session reaches a closure, pause, compaction, or handoff boundary.
It promotes only durable meaning into the smallest project-owned surface, records
history according to local policy, and lets the remaining conversational context
disappear. Memory Closure does not change an item's lifecycle state or make
unfinished work complete.

## Runtime language

Ariad should prefer the method language:

```text
Exploration
Exploratory Work
Delivery
Delivery Work
Refinement
Refinement Work
Workbench
```

Runtime-specific docs may use mode or lane language when describing execution
inside a runtime:

```text
Exploratory Mode
Builder Mode
Delivery lane
Refinement lane
Builder Home
```

Mode implies an executing system following a path. Work area names the
methodological field. Lane names how a runtime routes a selected work unit
through a specific flow. This is why Ariad's canonical docs use Exploration,
Delivery, and Refinement, while Maestro or Mirror docs may describe modes,
lanes, or home surfaces.
