---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - the concept-first migration's compatibility-window commitment for curated root exports; the accepted concept packages and dependency boundaries remain unchanged
  - DEC-040's recommendation to inventory external consumers and announce replacements before a versioned deprecation window
related:
  - docs/project/decisions/records/2026-07-21T0809Z-concept-first-ontology-boundaries.md
---

# Pre-release APIs carry no compatibility promise

## Question

Must Impetus preserve curated root exports and temporary names through a
versioned deprecation window, or may the pre-release project remove and rename
them while keeping every executable experiment and test working?

## Decision

Impetus is pre-release and makes no backward-compatibility promise for its
current Python API. Canonical concept packages are the maintained import
surface. Obsolete names, aliases, root re-exports, and module paths may be
removed or renamed without deprecation warnings, compatibility shims,
migration guides, elapsed support windows, or a release-count gate.

Every such change must update production code, tests, scripts, and all
executable experiments in the same delivery unit. The full behavioral suite
must remain green. Experiments freeze behavioral evidence, not old import
syntax. Historical reports, transcripts, and prior decision evidence remain
historical and are not rewritten merely to normalize old vocabulary.

The curated root facade is not canonical ontology and carries no independent
support promise. Maintained code should import concepts from their owning
packages. Root exports whose canonical homes already exist may be removed in a
bounded repository-wide cleanup; this includes the `NetInstance` identity
alias in favor of `impetus.instance.Instance`.

A temporary name with no implemented replacement may remain only because the
replacement story has not yet delivered, not to preserve compatibility. Thus
`Scheduler` may remain until Candidate Selection replaces it,
`ExecutionRuntime` until the Dispatch API settles its replacement, and the
root-only whole-action coordination names until the Engine work supplies an
honest production surface. Once a replacement lands, repository consumers
move atomically and the superseded name may be deleted immediately. Private
`impetus._coordination` does not become a public replacement import merely to
remove its current root doorway.

No obsolete flat deep-module shims are reintroduced. Structural rules continue
to prohibit canonical implementation packages from importing through the root
facade even while any temporary root exports still exist.

## Rationale

No Impetus release or deployed consumer creates a migration obligation. The
project version is `0.0.0`, and the executable consumers found by DEC-040 are
repository experiments, tests, and scripts under project control. Preserving
their behavior is valuable; preserving their old imports is not.

Deprecation machinery would turn pre-release design iteration into an
unearned public promise and would keep superseded vocabulary visible after the
architecture has learned a better name. Updating the whole executable corpus
instead gives stronger evidence: the accepted semantics continue to work
through the canonical package graph.

## Options Considered

- **Retain all compatibility through 0.x or 1.0.** Rejected: there is no
  release contract or external migration burden that justifies carrying the
  surface.
- **Deprecate export by export after consumer inventory and a warning
  release.** Rejected: replacement readiness still matters, but a support
  window does not. Repository consumers can be updated atomically.
- **Remove names immediately even when no replacement exists.** Rejected:
  deletion must not manufacture an API or make private coordination public.
  Temporary implementation vocabulary may survive until its owning story.
- **Remove obsolete compatibility atomically with complete repository consumer
  updates — chosen.** This preserves behavior without treating pre-release
  spelling as a contract.

## Consequences

- Planned maintenance removes root exports that already have canonical package
  homes, removes `NetInstance`, updates all executable consumers, and verifies
  the full suite. It follows the normal Plan Checkpoint; this recording change
  does not perform the refactor.
- Canonical package documentation and examples must not teach the root facade
  as the supported architecture.
- Candidate Selection, Dispatch Attempt, and Engine stories may delete their
  superseded temporary names when they deliver replacements, without a second
  compatibility-timing ruling.
- Behavioral schemas, History bytes, transaction semantics, and experiment
  outcomes remain protected. This ruling changes API compatibility posture,
  not runtime semantics.

## Review Trigger

Revisit only when Impetus is preparing its first public release or acquires a
real external consumer whose supported API must be declared. At that point,
define versioning and compatibility from the then-current canonical surface;
do not retroactively treat pre-release aliases as promised API.
