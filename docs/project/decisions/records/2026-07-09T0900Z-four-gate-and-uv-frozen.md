---
status: Decided
raised: 2026-07-09
decided: 2026-07-09
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/process/development-guide.md
---

# The gate is four checks; uv runs frozen

## Question

What exactly is "green", and how do we stop `uv` from rewriting `uv.lock` on every
routine command (which was producing one-line `exclude-newer` timestamp churn that had
to be discarded on every gate run)?

## Decision

"Green" is **four gates**, all run with `UV_FROZEN=1`:

1. `uv run pytest -q` — all retained tests pass with zero skipped.
2. `uv run ruff check .` — clean.
3. `uv run ruff format --check .` — clean. **Enforced, not advisory** — a unit is not
   green while any file would reformat.
4. `uvx --from ast-grep-cli sg scan` — exit 0.

`uv` runs **frozen** (`UV_FROZEN=1` exported in the shell profile, equivalently
`uv run --frozen`): routine commands never rewrite `uv.lock`. A lockfile change must be
a deliberate `uv add` / `uv lock`, never incidental — if `uv.lock` appears in a diff, it
is a real change to inspect, not noise to discard.

## Why

`ruff format --check` was already documented in the development guide as clean-criteria,
but was not enforced — three pre-existing files failed it. Making it a real gate makes
reality match the documented contract and keeps formatting out of review. Freezing `uv`
removes the per-run `uv.lock` timestamp churn entirely, so the working tree stays clean
between gate runs and a lockfile diff becomes meaningful.

## Consequences

- Adopted 2026-07-09 during the gate-hardening between kernel slices; the repo was
  formatted clean first (`chore(lint)`), then the gate + policy recorded in
  `development-guide.md`.
- The test gate covers the retained test suite and requires zero skipped tests.
- Recorded here for discoverability; the operating detail lives in
  `docs/process/development-guide.md` and `build-method.md`.
