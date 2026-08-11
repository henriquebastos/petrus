---
date: 2026-08-11T19:37:04Z
author: Amp
kind: milestone
related:
  - spec/net-schema.md
verification:
  - focused red test — failed because petrus.impetus.dsl.typed_guard was absent
  - focused DSL and typed-binding suite — 59 passed
  - scripts/check quick — all touched Python paths passed
  - scripts/check full — 2170 passed
  - scripts/check release — 2170 passed, then 2170 passed with 17 external qualification routes deselected
  - independent adversarial review — accept, no blocker or important finding
---

# Exposed converter-aware typed guard authoring

## What changed

`petrus.impetus.dsl.typed_guard` now provides decorator and direct-factory
forms for a pure typed predicate whose selected inputs are decoded by an
explicit `PayloadConverter`. It lowers through the existing typed-guard path
and remains an anonymous canonical guard declaration.

Ordinary callable guards retain `DataclassPayloadConverter`, and typed guards
retain their exact-`bool` result requirement. No canonical Net, History, wire,
runtime, handler, or Activity contract changed.

## Why it matters

Typed domain authors can choose strict replay hydration without reconstructing
private DSL guard flavors or searching token types at runtime. The public seam
is the smallest adapter over converter support already owned by `GuardSpec` and
the typed binding layer.

## Verification

The first focused test failed because the public factory was absent. After the
implementation, focused DSL and binding tests passed 59 tests, including one
consumed and one read input decoded through a recording converter, exact-bool
rejection, anonymous declaration display identity, and canonical declaration
URI. `scripts/check quick` passed for touched Python paths and
`scripts/check full` passed 2170 tests. An independent adversarial review found
no blocker or important issue and judged compatibility risk low.
`scripts/check release` then passed 2170 tests in parallel and 2170 tests with
17 external qualification routes deselected in fixed order.

## Follow-up

Consumers maintaining private typed-guard wrappers can import `typed_guard`
from `petrus.impetus.dsl` and pass their converter directly. No migration is
required for ordinary callable guards.
