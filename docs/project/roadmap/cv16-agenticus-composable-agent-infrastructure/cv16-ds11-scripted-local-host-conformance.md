---
code: CV16.DS11
level: Delivery Story
status: Done
status_reason: Public scripted lifecycle, process-restart classification, documentation, and release gates are verified.
updated: 2026-08-09
related:
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
  - docs/project/decisions/records/2026-08-05T1405Z-pi-a2-recovery-separates-work-identity-from-process-fences.md
---

# Qualify one hermetic Pi A2 Local host composition

## Intent

Qualify the Petrus-owned **Pi A2 Local host lifecycle — scripted runtime
conformance** as one supported, hermetic, local-first composition without
claiming authenticated Pi, model, or provider execution.

## Scope

- Provide a clearly named public scripted-conformance composition and readiness
  route without exposing arbitrary mutable adapter or probe state.
- Exercise installation-owned one-shot authority, `LocalProcessEnvironment`
  Episode territory, scoped Hands, workspace archive, cleanup-gated output and
  Continuation bodies, terminal replay, and ordered operation/host close.
- Prove that a real process killed after durable admission reopens work as
  restart-indeterminate without authority materialization or runtime redispatch.
- Publish the precise pre-release Agenticus support matrix and run routine and
  release verification with external qualification deselected.

## Acceptance behavior

1. **Given** finite scripted runtime data, synthetic installation-owned
   conformance authority, and no network/provider credentials, **when** an
   operator composes, checks scripted readiness, starts, waits, loads bodies,
   and closes the operation and host through public Python APIs, **then** the
   route completes without caller mutation of private adapter/probe fields, and
   composition and readiness request no authority.
2. **Given** one admitted operation, **when** it runs with one-shot installation
   authority, Local Episode territory, scoped Hands, and a workspace archive,
   **then** output, Continuation, and workspace bodies become readable only
   after aggregate cleanup is verified, and credential bytes enter no durable
   operation/body/workspace state.
3. **Given** terminal settled work, **when** a host is recomposed, **then** it
   replays before probe, authority, territory, or runtime-client creation.
4. **Given** durably admitted work in a real subprocess, **when** the process is
   killed and the host is recomposed, **then** the operation is
   `restart-indeterminate` / `operation-indeterminate` and no authority or
   runtime dispatch occurs.
5. **Given** stale Connection, Attachment, grant, execution, or effect
   authority, **when** publication is attempted, **then** existing fail-closed
   fences remain the supporting contract.
6. **Given** an operator-visible failure, **when** it crosses the host API,
   **then** only bounded runtime/settlement codes are exposed and credentials or
   raw provider diagnostics are absent.

## Driver QA and evidence plan

- Focused `test_pi_a2_host.py` conformance, including the real subprocess-kill
  route and secret-byte assertions.
- Existing Connection, Attachment, Hands/grant, effect, and runtime stale-fence
  suites through `scripts/check full` and `scripts/check release`.
- Release commands retain the explicit deselection of
  `qualification_installation`, `real_provider_acceptance`, and
  `real_gondolin_acceptance`; those routes are not claimed green.

## Exclusions

- Authenticated Pi/model/provider support or model-quality evidence.
- Promotion of `pi.native.a2.local` with an external installation beyond
  experimental, qualification-only status.
- Support claims for every Agenticus descriptor or adapter.
- A generic runtime override, universal Agent/Session abstraction, public Motus
  execution ownership, exactly-once provider effects, or power-loss durability.
- New composed-host stale-publication architecture unless focused evidence
  proves a gap not already owned by the existing fences.

## Evidence and status

**Done.** The public route accepts only finite immutable `PiA2ScriptedTurn` and
`PiA2ScriptedCall` data; Petrus owns the script interpreter and exact
`LocalProcessEnvironment`. Scripted readiness is distinct from external Pi
installation probing. Terminal replay precedes readiness, and a real `SIGKILL`
after durable admission reopens as `restart-indeterminate` without authority or
runtime dispatch. Recovered cleanup remains unverified and host close fails
closed rather than claiming orphan reconciliation.

The public native composer likewise owns its exact `LocalProcessEnvironment`
and normal probed subprocess client. Collaborator-aware composition and the
concrete host implementation are underscored; exported `PiA2RuntimeHost` is the
non-instantiable observation/operation protocol.

Executed evidence on 2026-08-09:

- `UV_FROZEN=1 uv run pytest -q tests/petrus/agenticus/runtime/test_pi_a2_host.py`
  — 23 passed.
- `scripts/check full` — 2021 passed.
- `scripts/check release` — 2021 passed in the parallel full run, followed by
  2021 passed and 17 explicitly deselected in the fixed-order run.

The deselected tests are the configured external installation, authenticated
provider, and Gondolin qualification routes. They were not executed and are not
claimed green.
