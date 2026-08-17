---
status: Open
raised: 2026-08-17
decided:
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV19.DS2
  - ../../roadmap/cv19-deterministic-simulation-testing/cv19-ds2-deterministic-event-and-fault-harness.md
  - ../../../process/dst-scenario-v1.md
  - https://github.com/henriquebastos/hamsterdan
---

# Ship a supported cross-project DST test kit

## Question

Should CV19.DS2 graduate its generic deterministic simulation mechanics into a
pytest-independent, supported `petrus.testing.dst` defining module so
Hamsterdan can compose its application World, Timeline, HostService profile,
and independent readiness oracle over the same executor?

This matters because Hamsterdan pins Petrus as a normal Git dependency. It
cannot consume the internal `tests/dst` proof, and copying the scheduler into
Hamsterdan would create competing execution and replay semantics. Conversely,
solving that packaging problem by exposing Petrus's private Coordinator or
mutable runtime handles would violate maintained-host ownership boundaries.

## Decision

Pending.

**Driver recommendation:** accept the supported test-kit boundary. Keep it
separate from both the public `petrus.simulation` product contract and DS1's
internal `petrus-dst-scenario` version 1 proof. Export only the strict generic
contracts from their defining module, with no Petrus-root re-exports.

## Rationale

Petrus and Hamsterdan independently converged on the same executable-world
design after comparison with the Instant Offer precedent: an imperative pytest
Timeline lowers every state-affecting operation to one normalized World
interpreter; expanded strict data, not Python callbacks, owns replay; profiles
compose real opaque host generations; and independent checkers run at legal
atomic boundaries.

The current public Engine doors are sufficient for Petrus's own vertical
profile. A generic profile does not need an Engine assumption or private
runtime access: it validates commands, creates or loads one opaque generation,
applies one atomic command, returns detached scheduled-work proposals, produces
detached observations, and distinguishes abrupt drop from graceful close.
Applications retain ownership of their complete host composition, provider
truth, command vocabulary, observations, and crash mechanism.

The test kit is nevertheless a real supported dependency boundary. Its API
compatibility declaration, artifact schema, profile identity/digest, and
checker manifest/digests must evolve separately and fail closed. That promise
requires Navigator acceptance before implementation or consumption.

## Options Considered

- **Ship `petrus.testing.dst` as a supported test kit — recommended.** One
  executor and replay model serves Petrus and application hosts while domain
  semantics remain application-owned.
- **Keep all DST machinery under Petrus tests.** This preserves an internal
  boundary but leaves Hamsterdan unable to consume the kernel and encourages a
  scheduler fork.
- **Copy or independently implement the kernel in Hamsterdan.** Rejected. It
  creates two interpreters, fairness policies, artifact contracts, and defect
  surfaces for the same abstraction.
- **Widen `petrus.simulation` or export Coordinator/runtime handles.** Rejected.
  The implementation-free hosted-simulation contract has different semantics,
  while private handles would breach Engine ownership and application/runtime
  compatibility boundaries.

## Consequences

If accepted:

- DS2 ships the smallest supported generic kernel plus a Petrus-owned profile
  using only public Engine doors;
- authored Timelines, generated schedules, and artifact replay use exactly one
  normalized interpreter;
- profiles own opaque generations, strict command/observation schemas, initial
  and follow-up work eligibility, graceful close, and non-settling abrupt drop;
- Petrus owns deterministic scheduling, bounds, fairness, generation
  revocation, checker cadence, artifacts, replay, and dispositions;
- DS1 version 1 and `implementation-free-v1` remain unchanged; and
- Hamsterdan consumes only an accepted Petrus commit through its ordinary
  dependency pin and adds its own HostService lifecycle/observation seams.

If declined, CV19.DS2 and Hamsterdan CV18 must revise their shared-kernel
strategy before either project implements a second executor or imports an
unsupported surface.

## Review Trigger

The Navigator should decide this before CV19.DS2 implementation creates package
contracts or Hamsterdan CV18.DS2 consumes Petrus DST code.
