---
code: CV19.DS4.TS2
level: Technical Story
status: Done
status_reason: The qualified liveness mutation now passes the complete reproduce, exact replay, minimize, bounded credential-refusing retention, replay, and ordinary-green-promotion operation
updated: 2026-08-19
related:
  - index.md
  - cv19-ds4-campaign-and-production-boundary-qualification.md
  - cv19-ds4-ts1-bounded-campaign-tiers.md
  - cv19-ds3-ts3-fair-shrinking-and-semantic-coverage.md
---

# CV19.DS4.TS2 — Failure retention and promotion

## Intent

Make a generated DST failure a safe, bounded, exact handoff from discovery to
triage and stable regression instead of leaving the reproduction in Hypothesis
output or an agent transcript.

## Scope

- Reuse the qualified fair-liveness mutation to rehearse failure, exact replay,
  shrinking, minimized replay, and green regression promotion.
- Retain a portable bundle containing the canonical failed v4 artifact plus a
  strict manifest with commit/runtime/dependency identity, property, discovery
  seed, shrink lineage, exact replay command, concise semantic coverage, and
  promoted fixture identity.
- Validate and bound the complete bundle before atomically publishing it.
- Fail closed on credential-like field names or values. Never alter artifact
  bytes to redact them because that would invalidate exact replay; profiles
  must normalize sensitive provider data before it reaches World.
- Add one executable `tests.dst.failure` demonstrate/replay route and document
  triage and retention policy under the existing DST guidance.

## Acceptance / Done Condition

1. A deliberate safety-preserving liveness defect produces a minimized failed
   artifact which replays with the same failure, disposition, and journal.
2. The retained manifest records exact commit/runtime/dependency, property,
   seed, before/after shrink, replay command, semantic reach, and green
   regression identity without scenario payload duplication.
3. Suspicious credential/provider fields, credential-shaped values, tampered
   artifacts, schema mismatch, and bundle overage fail before replay/promotion.
4. The existing unmutated minimized fixture replays green through the ordinary
   test path and remains the promoted regression; the mutation is never
   promoted.
5. Focused demonstration, ordinary DST, full, and release gates pass.

## Delivered evidence

- `tests.dst.failure demonstrate` constructs the already-qualified noisy
  test-only liveness mutation, replays it exactly, uses deterministic Hypothesis
  generation/shrinking to remove one retry plus observation/crash/observation
  noise, replays the minimum, writes a two-file bundle, replays that bundle,
  and verifies the existing ordinary green fixture.
- The parent and minimum both end at the fixed 28-action budget and therefore
  both contain 29 operations. The truthful shrink evidence records fair-phase
  entry moving from operation 16 to operation 9 and canonical bytes falling
  from 130,303 to 128,910 rather than claiming a lower terminal operation
  count.
- The minimum artifact has digest
  `sha256:98c5e51326430be34f57babbcfa5d2eea959e1ebb53153bc78de3cf3bbebd230`.
  Standard replay returned `pass` / `budget_exhausted` with journal digest
  `sha256:e708ca6761138b78003cce9edf7cfe733dce76234bbf6da3ba577cf9bd127b8a`;
  promotion replay returned `pass` / `quiescent` for
  `generated-runtime-minimized-fair-regression-v4`.
- The retained directory contains only canonical `scenario.json` and strict
  `manifest.json`. Replay refuses credential-like keys/values, unknown or
  duplicate schema data, extra files, artifact tampering, manifest/artifact
  provenance mismatch, and byte overage. It never rewrites execution data.
- Focused failure/generated-runtime qualification passed 11 tests; the
  complete ordinary DST suite passed 215 tests with skips forbidden; the full
  gate passed 2,403 tests; and release qualification passed 2,403 tests in both
  bounded-parallel and fixed-serial orders.

No production runtime, `petrus.testing.dst/v4` API, v4 artifact schema,
profile/checker identity, or scheduler behavior changed.

## Correctness sketch

- **Authority:** canonical encoded v4 artifact bytes are replay authority; the
  manifest pins their digest and describes provenance only.
- **Safety:** retention cannot mutate operations, accept a secret-shaped value,
  overwrite an existing bundle, or label a failed/tampered replay as promoted.
- **Liveness:** bundle replay has the same deterministic bounds as its artifact;
  outer wall-clock containment remains a separate runner concern.
- **Bounds:** artifact, manifest, semantic summary, file count, and total bundle
  bytes have fixed ceilings and no unbounded stdout/provider capture.
- **Nondeterminism:** the discovery seed and Hypothesis version are provenance;
  minimized expanded operations remain authoritative.
- **Crash cuts:** this qualification has generated runtime crash/load cuts but
  does not reinterpret an operating-system process kill.
- **Independent judgment:** the existing generated-runtime authority checker
  must remain green while the distinct fair-liveness failure reproduces.

## Out of Scope

- Automatically uploading bundles or CI artifacts to an external service.
- Attempting to infer or sanitize arbitrary provider payload semantics.
- Changing the v4 artifact schema or supported DST test-kit API.
- Real PostgreSQL, Absurd Worker, ZeroMQ, or process-boundary qualification.
