---
code: ES-056
title: Progressive-disclosure developer experience
status: Completed
status_reason: >-
  The Navigator promoted the one end-to-end Approachable Petrus Value as CV20
  on 2026-08-27. Its original evidence gates remain explicit Delivery work;
  roadmap promotion does not claim that AX27–AX29 or the application acceptance
  cases have already passed.
opened: 2026-08-13
updated: 2026-09-08
related:
  - ES-055
  - ES-061
  - CV20
  - CV8
  - CV10
  - CV16
  - CV19
  - docs/product/principles.md
  - docs/project/decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
  - docs/project/decisions/records/2026-08-03T2130Z-flat-json-is-the-canonical-net-definition-interchange.md
evidence_repository: https://github.com/henriquebastos/hamsterdan
evidence_revision: ea7784bb8a1237f223e9ffcb27598d5e39ee9e17
promoted_to:
  - CV20
promoted_at: 2026-08-27
---

# 1 Progressive disclosure and CV20 promotion

## 1a Accepted direction and owner

The Navigator promoted one end-to-end Value, [CV20: Approachable Petrus](../../roadmap/cv20-approachable-petrus/index.md),
on 2026-08-27. CV20 owns delivery scope and current status. This exploration
preserves the application evidence, promotion rationale, and gates that had not
passed at promotion.

The product promise is one readable flow file through authoring, validation,
execution, observation, resume, and extension. It preserves the full runtime
and explicit low-level descent. The
[progressive-disclosure decision](../../decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md)
and [product principles](../../../product/principles.md) own that constraint.

One file may import domain types, Activities, clients, and configuration.
Credentials, live providers, History, deployment, and generated artifacts keep
their own owners. First motion includes inspection of canonical topology,
creating or resuming a named Instance, representative ingress, advancement, and
an explanation of the result. Generating a file never authorizes running it.

The original candidate used the provisional name CV19. That identifier later
went to deterministic simulation testing; promotion assigned this Value CV20.

## 1b Historical application evidence

The comparison used Hamsterdan as a concrete application case. At revision `ea7784b` it has 11 Activities, 11 GitHub
webhook event types, 12 human intent kinds, one Engine per pull request, agent
work, durable publication, timers, lifecycle replacement, recovery, and two
world-mutation gate classes.

Its four explorations separate several questions that Petrus must not conflate:

1. ES-001: runtime/application ownership. Moving operational retry and
   exact generation cleanup to Motus and lifecycle scopes removed large amounts
   of retirement topology while keeping current authority, desired state, and
   business acceptance in the application. Runtime capability can simplify the
   authored Net without weakening it.
2. ES-002: imperative sugar alone. Fourteen mostly domain-specific
   fragment families added about 540 lines of machinery to reduce roughly 510
   hand-wired declaration lines to about 440. The economics were negative.
   Hiding fluent arc syntax is not the product answer.
3. ES-003: structured authoring. Twenty-seven experiments found a layered
   candidate: a generic net kernel floor, function-shaped typed Blocks, a small
   composition algebra, optional sugar, and an advisory static facade. Every
   experiment compiled to the frozen runtime; zero Petrus changes were needed.
   Deterministic composition errors remain authoritative, and source mapping,
   canonical rendering, History, and replay survive lowering.
4. ES-004: application essence. The production net measured 46 places, 69
   transitions, 309 arcs, including 94 read arcs; experiments classified 73%
   of those reads as displaced by executed alternatives. Every product rule
   survived a candidate model centered on three control states, per-concern
   folds, pure decisions, typed subnet exits, and two effect gates. The full
   merged model and production migration remain unproven and unapproved.

The topology counts are diagnostics, not a score. Hamsterdan previously chose
more places and arcs to expose independent business owners, a clarity gain.
Conversely, the ES-004 fragments reached about 1.1 arcs per node by eliminating
ambient reads. A good authoring surface minimizes accidental coordination while
keeping genuine ownership visible; it does not optimize blindly for the
smallest graph or fewest source lines.

The Deer Workflow comparison adds the other half of the evidence. Deer reaches
one generated file and visible progress quickly because ordinary TypeScript
control flow is the workflow. It loses the compiled artifact, durable state,
replay, resume, and explicit join/failure semantics. Petrus should copy the
first-motion discipline, generated-authoring package shape, and presentation
clarity; not the execution model.


## 1c Why one Value

Authoring, host composition, and inspection had each been developed as separate
capabilities. The missing product behavior was a coherent journey through them.
One Value makes that journey the acceptance target while its Delivery Stories
retain independent implementation boundaries.

| Delivery owner | Question assigned at promotion |
| --- | --- |
| [DS1](../../roadmap/cv20-approachable-petrus/cv20-ds1-one-file-first-motion.md) | Which generic run composition and named local durability profile are actually missing? |
| [DS2](../../roadmap/cv20-approachable-petrus/cv20-ds2-expressive-flow-authoring.md) | Which typed block/composition notation preserves canonical lowering and deliberate descent? |
| [DS3](../../roadmap/cv20-approachable-petrus/cv20-ds3-live-understanding.md) | How should the user inspect Net documents and correlate semantic state with operational progress? |
| [DS4](../../roadmap/cv20-approachable-petrus/cv20-ds4-generated-authoring-and-examples.md) | How do generated source, examples, diagnostics, and repair use the same public contract? |
| [DS5](../../roadmap/cv20-approachable-petrus/cv20-ds5-approachable-effects-and-agents.md) | How do ordinary Activities and one supported Agenticus profile fit the same journey? |

Petrus owns generic runtime composition and canonical diagnostics. Arx owns
human interaction and presentation. Applications retain authority, clients,
policy, and domain work. A runner should return control to its host. The
recommended local durable SQLite profile still required evidence; this
exploration did not settle it as the default.

## 1d Promotion gates and order

The original evidence gates were not all executed at promotion. Their current
results belong to the Delivery Stories above:

AX27, AX28, and AX29 are retained executable probes in Hamsterdan ES-003 at
the evidence revision in frontmatter. CV20 inherited those probes as Delivery
evidence to execute, not as passing results.

1. AX28 runs first for generic runtime composition. It follows one file through
   compile, canonical inspection, a named local run, observation, and replay or
   resume. It must reveal missing assembly before a public facade is designed.
2. AX29 mixes higher-level blocks with low-level topology in one file without
   losing validation, stable lowering, or source attribution. It protects
   descent before an authoring API is promoted.
3. AX27 tests generated-authoring diagnostics. Its mechanism can run independently;
   productization follows the selected authoring and diagnostics contract.
4. The application benchmark starts with one pull request: CI failure, rerun,
   repair, branch movement, confirmed resume, readiness publication, human wait,
   and terminal state. Full authored-architecture coverage follows; neither
   successful experiment authorizes production migration.
5. Runner ownership, local profile, and presentation consumer each need a bounded
   decision or experiment. Zero-agent and supported Agenticus examples must
   share the journey while preserving different authority needs.

The ES-061 portable-document/static-arrangement work can proceed independently
of AX28. Live presentation needs a concrete runtime consumer. Agenticus
convenience follows a coherent zero-agent route. Promotion did not reopen
CV8 semantics, resolve CV10 blockers, broaden CV16 support, or make Arx own
application lifecycle.

## 1e Questions carried into Delivery

At promotion, default notation, local durability/profile progression, runner
lifetime, and live presentation correlation remained open. So did source maps,
definition evolution preflight, and selection of one Agenticus convenience
route. [CV20](../../roadmap/cv20-approachable-petrus/index.md) now owns those
questions; [ES-060](../es-060-expressive-authoring-notation-design/index.md)
retains the paused notation-design method.

Any fold/decide layer must consume canonical facts and emit identified work
through existing runtime operations. It cannot keep unreconstructible process
state in a host loop. Convenience must also preserve structured failure,
bounded fan-out, explicit wiring, and independent observation. Source-line and
graph-size reductions cannot substitute for visible business ownership.

## 1f Closure

This exploration is complete because its candidate was promoted. Delivery is
complete only where the owning story records executed evidence. The historical
application counts and comparisons above describe the pinned revision; this
Memory Closure reran neither those applications nor their experiments.
