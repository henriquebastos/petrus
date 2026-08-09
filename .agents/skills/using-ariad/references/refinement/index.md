# Refinement

Refinement is the Ariad work area for caring for existing capability.

Exploration asks what a signal is becoming. Delivery asks what the project is
committing to change. Refinement asks what an existing capability needs in order
to become clearer, safer, smoother, or more habitable.

Refinement Work begins when the Navigator wants to adjust what already exists
without turning that care into roadmap delivery. It may come from real use,
local bugs, product friction, copy or surface polish, test gaps, documentation
inconsistency, small refactoring requests, or repeated operational discomfort.

Refinement is centered on the **Workbench**. The Workbench holds **Change
Requests** and **Refinement Stories** outside the roadmap.

## What Refinement protects

Refinement protects care from inflation.

A coding agent can turn every small bug, copy adjustment, and friction into a
roadmap item. That makes the roadmap noisy and makes delivery feel heavier than
it needs to be. Refinement gives small and emergent improvements a disciplined
place to live without pretending they are new product promises.

Refinement also protects velocity from improvisation. A quick fix should not
require a full Delivery Story, but it still needs a named request, scoped work,
validation, and closure.

## Current artifacts

- [Refinement Conceptual Model](conceptual-model.md) names Workbench, Change
  Request, Refinement Story, and Refinement Work.
- [Refinement Flow](flow.md) demonstrates quick and composed refinement through
  Change Request cycles.

## Boundary with Delivery

Delivery belongs to the roadmap. It changes or completes a product, project, or
process capability through Delivery Stories, User Stories, and Technical Stories.

Refinement belongs to the Workbench. It cares for an existing capability through
Refinement Stories composed of Change Requests.

If a Change Request grows into a new promise, public contract, broad
architecture change, or roadmap-level arc, it should be promoted to Delivery
rather than absorbed silently into Refinement.

## Boundary with Exploration

Exploration preserves uncertainty before commitment. A weak signal, open
question, or unclear possibility should remain exploratory until it has enough
form to become either Delivery or Refinement.

Refinement begins after the Navigator can name a requested change to an existing
capability. It does not require knowing the implementation, but it does require a
clear enough request to enter the Workbench.

## Working principle

The roadmap carries delivery commitment. The Workbench carries refinement care.
The Driver may recommend where work belongs, but the Navigator chooses the field
before the work begins.

Ariad defines the semantic obligations of Refinement, not a particular runtime
storage model or surface layout. Implementations may choose their own status
names and rendering style if the work field, CR phase, mutation boundary,
outcome evidence, and RS closure conditions remain visible.
