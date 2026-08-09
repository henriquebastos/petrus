---
date: 2026-08-09T13:00:00Z
author: Amp
kind: milestone
related:
  - CV16.DS11
verification:
  - focused Pi A2 host conformance — 23 passed
  - scripts/check full — 2021 passed
  - scripts/check release — 2021 passed, then 2021 passed and 17 external qualification tests deselected
---

# Closed the Pi A2 public construction bypass

## What changed

The native public composer no longer accepts provider or runtime-client
collaborators. It owns an exact `LocalProcessEnvironment` and the ordinary
probe-selected subprocess client. Collaborator-aware construction and the
concrete host class are internal; exported `PiA2RuntimeHost` is now only the
non-instantiable public observation/operation protocol. The scripted public
composer remains finite immutable data-only.

## Why it matters

An injected factory could previously survive a successful native probe and run
arbitrary caller code behind genuine READY installation facts. Closing every
public construction route makes the DS11 support boundary structural rather
than dependent on callers choosing the safer composer.

## Verification

API-boundary tests pin both public composer signatures, prevent direct public
host construction, and verify exact local-provider ownership plus the normal
native client-factory posture. Focused conformance passed 23 tests;
`scripts/check full` passed 2021 tests; `scripts/check release` passed 2021 tests
in parallel and then 2021 tests with 17 external qualification routes explicitly
deselected in fixed order.

## Follow-up

None for this blocker. The previously recorded provider-qualification and
power-loss exclusions remain unchanged.
