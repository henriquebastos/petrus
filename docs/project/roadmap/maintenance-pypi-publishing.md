---
level: Maintenance
status: Validated
status_reason: Linux release qualification and package checks pass; push and PyPI registration remain before the first upload.
updated: 2026-09-08
---

# 1 PyPI publishing

## 1a Scope and acceptance

Prepare version `0.1.0a1` under the working distribution name `petrus-runtime`.
The Navigator requested public PyPI distribution, publishing after creating a
GitHub release, and a `0.x` maturity policy. The Driver selected `petrus-runtime`
as the working default after checking name availability and inviting Navigator
feedback. Imports remain under `petrus`.

1. A published GitHub release with a matching tag and prerelease flag qualifies,
   builds, checks, and uploads the wheel and source archive.
2. A mismatched tag or prerelease flag refuses before publishing.
3. Manual release validation builds and checks without uploading.
4. A fresh wheel installation executes the README net with the documented output.
5. Metadata, optional extras, installation instructions, and release guidance
   refer to the intended distribution.

Driver plan recommendation: proceed at above 90% confidence for the mechanism.
PyPI account setup and the actual first release remain external completion steps.
Runtime redesign and live-provider qualification are outside this change.

## 1b Correctness sketch

The release commit's `pyproject.toml` owns the version. GitHub owns the release
event and tag; PyPI owns accepted distributions. The workflow must check the
tag and prerelease flag, qualify that checkout, and pass only that run's built
artifacts to a separate publishing job. Only that job receives OIDC permission.

Progress depends on GitHub runners, dependency indexes, Docker, and a matching
PyPI Trusted Publisher. Jobs have finite timeouts; one release ref runs at a time
without cancelling an upload. No automatic retry or overwrite is introduced.
Runner scheduling, index availability, and remote upload outcomes remain external.
Tests exercise event fixtures; actionlint checks workflow syntax; building,
Twine, archive inspection, and an isolated README execution check the output.
Local evidence cannot prove PyPI's OIDC exchange.

Interruption before upload leaves PyPI unchanged. Interruption during upload
may leave one distribution accepted. Inspect PyPI before recovery; do not
rebuild and overwrite the same published version. The release guide owns recovery.

## 1c Evidence and review

The existing `release-check.yml` now handles published releases and manual
validation. The upload job depends on qualification and artifact checks, uses
the `pypi` environment, and alone receives `id-token: write`. The GitHub
environment was created and read back with no required reviewers. No release
or PyPI upload was performed.

The [release guide](../../process/releasing.md) owns the name, version policy,
exact pending-publisher fields, release sequence, and recovery. The README and
briefing now identify the prepared alpha. Package extras, missing-dependency
messages, and DST metadata queries use the new distribution name. Existing
campaign report keys and retained historical fixture identities remain intact.
License notices now accompany both distributions. The README uses absolute
documentation links that also work when rendered on PyPI.

| Check | Result |
| --- | --- |
| Release guard and import-boundary tests | Initial 33 cases passed; a further canonical-version refusal case is included in the complete suite. |
| `actionlint .github/workflows/release-check.yml` | Passed. |
| Isolated `python -m build` and `twine check --strict` | Source archive and wheel built successfully; both metadata checks passed. The wheel was built from the source archive. |
| Fresh Python 3.14 wheel installation | README net printed `['Hello, Petrus!']`; import path pointed to installed `site-packages/petrus`; metadata reported `0.1.0a1`. |
| Installed extras and resource probe | Absurd, PostgreSQL, and ZeroMQ imported; schema and JavaScript helpers were present; the unrelated `petrus` distribution was absent. |
| Link and diff checks | 34 repository links resolved; `git diff --check` passed. |
| Linux `scripts/check release` | First full pass: 2,609 passed in 75.19 seconds. Additional serial pass: 2,609 passed in 154.53 seconds. The 17 opt-in provider, guest, and installation acceptance tests were deliberately deselected; no selected test skipped. |
| Scheduled DST campaign | All four profiles passed in 22.306 seconds under campaign identity `pypi-preparation-2026-09-08`, using the updated installed package metadata. |

Linux validation uses a disposable `node:24-bookworm` container, Python 3.14,
uv 0.12.7, Docker, Graphviz, Git, system Python, and `flock`, with the project
mounted at `/workspace`, `UV_PROJECT_ENVIRONMENT=/tmp/petrus-venv`, and
`TMPDIR=/tmp`. The host Docker socket and host networking support the real
PostgreSQL and Worker boundary tests. This supplies Linux execution evidence;
GitHub event delivery and PyPI's OIDC exchange still require the first live run.

Initial macOS qualification exposed stale distribution metadata lookups and
the archive notice allowlist; both were fixed and passed focused checks.
macOS also needs a short `TMPDIR` for nested Unix sockets. With that setting,
the final macOS run had 2,606 passes and three Pi runtime failures. Two
repeatable Pi A2 host failures also failed on untouched commit `913acb0` in a
separate checkout. These platform limitations remain recorded here; this
change does not claim a green macOS suite or alter Pi runtime behavior.

## 1d Review and remaining activation

No runtime refactoring was needed. Packaging naming gaps and the missing
notice contents were resolved. No new runtime debt or glossary change was
introduced. The release policy explicitly overrides Ariad's roadmap-based
major-version default under the Navigator's requested `0.x` direction.

Driver Experience and Review recommendations: accept the prepared mechanism at
above 90% confidence, with the live-upload limit stated explicitly. The history
recommendation is one coherent `feat(release)` commit on `main`. Navigator
acceptance of the name and first publication is not implied by that recommendation.

Ask before pushing under the local development policy. Activation also requires
the pending PyPI publisher described in the release guide. The Navigator creates
the first release; the workflow's actual upload remains unverified until that
event. Change this record to Done after the workflow is pushed and the publisher
is registered; record actual first-publication evidence in a release milestone.
