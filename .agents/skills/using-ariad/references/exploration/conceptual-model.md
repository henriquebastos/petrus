# Exploration Conceptual Model

This document names the conceptual elements of Ariad Exploration.

It does not explain the practical flow. The step-by-step sequence, examples, story thickening, and visual feedback live in [Exploratory Flow](flow.md).

For the method-level distinction between Exploration, Delivery, and Refinement, see [Work Areas](../method/work-areas.md).

## Progress semantics

Exploration treats progress as transformation of form. A signal is not merely advanced through steps. It changes nature as it is held, related, questioned, experimented, and shaped.

Progress in exploration is not completion of a target. It is condensation of meaning.

Meaning condenses when thin signals become thicker narratives. A captured signal is only a perceived phenomenon. As it gathers context, connects to other signals, clusters, resonates, attracts interpretation, meets hypotheses, and survives experiments, it gains relation, direction, and interpretive weight.

## Concepts

### Signal

A signal is a thin narrative that deserves not to be lost.

It may come from a conversation, a runtime failure, repeated friction, product discomfort, architectural suspicion, user feedback, operational incident, methodological gap, or unresolved question.

A signal does not need a solution. It does not need a planned action. It only needs enough relevance to be preserved.

### Exploratory Story

An Exploratory Story is a narrative thread opened by one or more signals.

It thickens as facts, tensions, hypotheses, experiments, and interpretations accumulate. It ends by becoming a candidate for Delivery, a requested change for Refinement, or by being archived.

An Exploratory Story does not have to move linearly. It can branch, loop, absorb contradictions, weaken hypotheses, form clusters, generate experiments, or end without delivery or refinement.

Signals and Exploratory Stories belong to different surfaces:

- Signal Radar holds possible, captured, kept-for-later, and reactivated signals.
- Narrative Field holds Exploratory Stories and the relations around them.

A Narrative Field Snapshot may show nearby kept signals as a Signal Radar excerpt, but those signals do not live in the Narrative Field unless they open or thicken an Exploratory Story.

### Assemblage

Assemblage is the process by which an Exploratory Story gains body by absorbing heterogeneous material from its environment.

Logs, conversations, analytics, decisions, feelings, failures, constraints, terminology, visual sketches, and experiments can all become part of the assemblage.

### Cluster

A cluster is a meaningful grouping of related signals.

The constellation metaphor is useful: separate points become readable as a figure when relation gives them shape. A cluster does not claim that the figure is final or objective. It says that several signals can currently be read together as a pattern.

### Resonance

Resonance is the felt or observed amplification of a signal, cluster, inquiry, or Exploratory Story.

A signal resonates when it returns, echoes across sources, attracts attention, or keeps explaining more than its initial scope. Resonance is a quality of the field, not only a state of one item.

### Attractor

An attractor is a cluster or Exploratory Story with enough gravity to pull interpretation, attention, or action.

Attractors are not delivery inputs by themselves. Their main use is to reveal the center of gravity around which the Exploratory Story can thicken.

The attractor is a methodological instrument, not the durable value of the exploration. The durable value is the thickened story, inquiry, candidate, decision, or archive that results from working with the attractor.

Attractors can be useful, too narrow, too broad, or misleading. A useful attractor helps the team see a real pattern. A narrow attractor may later be absorbed into a wider attractor. A misleading attractor over-explains events and can distort the field.

### Inquiry

An inquiry is an exploratory question formed around one or more signals, clusters, or attractors.

An inquiry is not a demand. It is not yet a story. It gives the exploration a center without forcing delivery.

### Hypothesis

A hypothesis is a possible interpretation, direction, or solution inside an inquiry.

Hypotheses are allowed to compete. They are working shapes, not decisions.

### Experiment

An experiment is a safe-to-learn intervention that introduces new material into the field and observes how the Exploratory Story changes.

Experiments are not delivery work by default. They are learning moves inside exploration. They may involve a prototype, a document sketch, a visual mockup, a code spike, a manual check, instrumentation, transcript classification, or a comparison between alternatives.

The Driver may propose an experiment when the story reaches a practical uncertainty that conversation alone cannot resolve. The proposal should remain optional and Navigator-confirmed.

### Exploration Documentation

Exploration Documentation is a durable narrative record of an Exploratory Story.

It preserves the useful shape of the exploration: initial signal, thickened story, attractors and refinements, experiments, findings, Carry Forward Notes, decisions, kept-for-later signals, and current state. It may be generated when a story is promoted, paused, archived, or simply reaches a meaningful documentation boundary.

When a candidate is promoted, the full Exploration Documentation should remain in the Exploration area. The future Delivery Story may receive a shorter exploration summary with a link back to the full document.

Exploration candidates usually promote to a Delivery Story, because exploratory material often contains more than one behavior validation boundary. Direct promotion to a single User Story is the exception: use it only when the candidate is already one behavior-sized unit, has one observable validation route, and does not hide later user-facing behavior behind a technical prerequisite.

### Carry Forward Notes

Carry Forward Notes preserve implementation-relevant findings that emerged during Exploration before a candidate is promoted.

They may include constraints, thresholds, examples, validation ideas, technical observations, non-goals, risks, or field-specific rules. Capturing them does not create Delivery commitment. It only prevents useful learning from being buried in the conversation when a later Delivery handoff is created.

The Driver should ask the Navigator before preserving Carry Forward Notes, especially when the notes may shape implementation scope.

### Candidate

A candidate is a thickened Exploratory Story, inquiry, hypothesis, or experiment result mature enough to be considered for Delivery.

Promotion is a Navigator decision. The Driver may suggest promotion, but it should not silently convert exploration into delivery.

Promotion is not only naming an idea. A promoted candidate should produce a Delivery handoff: suggested roadmap placement, Delivery Story seed, candidate User Stories and Technical Stories, validation seeds, and pull state. The candidate enters the Delivery field under the roadmap taxonomy — usually as a Delivery Story inside a Value / CV, then expanded into child stories — even if the Navigator has not pulled the first User Story or Technical Story for implementation yet.

Direct-to-User-Story promotion is allowed, but rare. The Driver should explicitly justify it by showing that the candidate has exactly one behavior/capability boundary and can be validated end to end as one User Story.

### Archive

Archive is the non-active resting place for exploratory material.

Archived material is not necessarily wrong or useless. It may be resolved, duplicated, incorporated elsewhere, intentionally deferred, no longer alive in the current field, or identified as a misleading attractor.

## Events

Exploration can be understood through events. Events are moments where the method recognizes that something changed in the exploratory field.

Events are not visual components. They may produce visual feedback, conversation feedback, stored records, or later automation, depending on the runtime.

```text
signal_detected
  the Driver notices a possible signal but does not persist it yet

signal_captured
  a signal is preserved in the journey's Signal Radar

signal_reactivated
  a kept signal is brought back into attention and routed to open a new Exploratory Story, thicken an existing story, join a cluster, or archive

exploratory_story_opened
  engagement around a signal opens an Exploratory Story in the Narrative Field

exploratory_story_thickened
  an Exploratory Story gains new material that changes its meaning, weight, or direction

cluster_formed
  related signals can be read together as a pattern

resonance_detected
  a signal, cluster, inquiry, or Exploratory Story begins echoing across sources or returning with force

attractor_detected
  a cluster or Exploratory Story starts pulling interpretation, attention, or action

attractor_refined
  a confirmed attractor changes scope, name, or center while preserving continuity with the previous reading

attractor_superseded
  a previous attractor is replaced because a different center now explains the story better

attractor_rejected
  the Navigator rejects a proposed attractor and the story returns to the last valid state

inquiry_opened
  one or more signals gain a guiding question

experiment_suggested
  the Driver or Navigator notices that a practical uncertainty may need a learning move before the story can continue safely

experiment_started
  exploration deliberately leaves the conversational flow to learn something specific

experiment_completed
  an experiment produces an observation, artifact, or result that changes the exploratory field

carry_forward_notes_captured
  the Navigator accepts preserving implementation-relevant exploration findings for a possible Delivery handoff

exploration_documented
  a durable Exploration document is generated or updated for an Exploratory Story, regardless of whether it promotes to Delivery

promotion_brief_generated
  a promoted candidate receives a full Exploration brief plus a concise Delivery Story summary/link

candidate_formed
  material has enough form to be considered for Delivery

candidate_promoted
  the Navigator accepts a candidate into Delivery; the handoff normally includes Delivery Story placement, candidate User Stories and Technical Stories, validation seeds, and pull state

signal_archived
  exploratory material leaves the active field without being erased
```

## Exploratory surfaces

Maestro's exploratory mode currently uses four surface names:

```text
Signal Radar
  What is being picked up?
  Surface for possible signals, captured signals, and signals kept for later.

Narrative Field
  What is thickening?
  Bird's-eye view of active Exploratory Stories in a journey.

Exploratory Story View
  What is happening inside this story?
  Focused view of one Exploratory Story and its current thickening.

Candidate Gate
  What is ready to cross?
  Surface for promotable Exploratory Stories or candidates ready for Navigator decision.
```

Radar is not the method and not a separate extension. In this model, Signal Radar is a Maestro exploratory surface.

## Relationship with visual grammar

Visual design can help discover the method, but it does not define it.

The conceptual model must survive multiple renderings. A signal can appear as a triangle, card, row, voice prompt, or API object. An Exploratory Story can appear as a timeline, assemblage map, cluster field, narrative card, or another future surface.
