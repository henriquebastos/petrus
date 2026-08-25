---
artifact: exploration
code: ES-058
title: Mutmut and Cosmic Ray comparison for Petrus
status: Completed
status_reason: >-
  Current documentation, pinned implementation inspection, and executable
  Python 3.14 probes support retaining Mutmut as Petrus's primary mutation
  diagnostic. Cosmic Ray's wider syntax and operator reach does not offset its
  annotation noise, full-command-per-mutant execution, serial local distributor,
  manual session invalidation, and coarser result classification for this project.
opened: 2026-08-25
updated: 2026-08-25
related:
  - docs/process/development-guide.md
  - scripts/check
source_context:
  - Petrus commit 39eac9d39a8050541db2d4b11c12ab967f9492b9
research_sources:
  - https://cosmic-ray.readthedocs.io/en/latest/
  - https://pypi.org/project/cosmic-ray/
  - https://github.com/sixty-north/cosmic-ray/tree/caf9a3193606ddd90cc37126b7fa95acefc47695
  - https://pypi.org/project/mutmut/
  - https://github.com/boxed/mutmut/tree/4f1208093517575a9402b99cfdcc7dea54c40e67
promotes_to: []
promoted_to: []
promoted_at:
---

# Mutmut and Cosmic Ray comparison for Petrus

## Inquiry

Should Petrus replace its curated Mutmut mutation diagnostic with Cosmic Ray,
and what concrete evidence should govern that choice rather than general tool
reputation?

Sources and probes were checked on 2026-08-25. Claims use Petrus's evidence
grades: `[E]` executable evidence in this checkout, `[D]` authoritative source
or documentation, `[R]` reported but unverified, and `[X]` refuted.

## Executive conclusion

**Retain Mutmut as Petrus's primary mutation-testing tool.** Cosmic Ray is not
better for the current Petrus profile.

Petrus deliberately runs mutation testing as a periodic, bounded diagnostic
over two fast semantic files and two focused pytest files. Mutmut already fits
that contract: it maps mutants to tests that reach their enclosing function,
distinguishes `no tests` from surviving mutants, supports local fork-based
parallelism, and retains incremental results. `[D/E]`

Cosmic Ray's real advantages are wider syntactic reach, explicit and extensible
operator plugins, line/operator/Git filters, SQLite sessions, HTML/XML reports,
and HTTP distribution. `[D]` Those strengths matter when a project needs to
mutate decorators, properties, module-level code, or custom operators. Petrus's
current profile does not need those capabilities enough to accept Cosmic Ray's
costs and result noise.

The bounded follow-up candidate is a maintenance upgrade from Mutmut 3.6.0 to
3.7.0. Version 3.7 officially supports Python 3.14 and improves function,
dependency, and configuration cache invalidation. `[D]` A local 3.7 probe
produced the same current profile outcomes as 3.6. `[E]` This inquiry does not
change the dependency or authorize that maintenance work.

## Current and proposed state

### Current state

Petrus pins `mutmut==3.6.0`. `scripts/check mutation` selects:

- `fold_history` and `_cursor` in `petrus.impetus.selection`;
- `TokenQueue` methods in `petrus.impetus.petrinet.marking`;
- the focused Selection and TokenQueue test files; and
- one child process, with no score threshold.

The development guide explicitly classifies `no tests` separately and warns
that the profile does not represent whole-module mutation coverage. `[D]`

### Proposed state

Keep Mutmut and the bounded diagnostic contract. Consider upgrading the exact
pin to 3.7.0 as separate Maintenance after ordinary dependency and command
verification. Do not add Cosmic Ray as a second standing mutation system;
retain it as an available one-off probe if future work specifically requires
decorator, property, module-level, or custom-operator mutation.

## Project-specific evidence

### Baseline and Mutmut

`[E]` The two focused test files passed on Python 3.14:

```text
35 passed in 0.86s
```

`[E]` The current Mutmut 3.6 profile completed in 10.97 seconds with one child.
Mutmut 3.7 completed the same profile in 11.90 seconds and produced the same
status counts:

```text
killed       129
survived      24
no tests      38
not checked   36
total        227
```

The 36 `not checked` mutants are generated from the two allowlisted files but
fall outside the command's function/class globs. `no tests` correctly exposes
that the focused test selection does not reach `TokenQueue.selected()` or
`TokenQueue.discard()`; it is not folded into the survivor count.

`[E]` Both Mutmut 3.6 and 3.7 generated ordinary `TokenQueue` method mutants but
no mutants for its `@property` methods. Both generated only the two module-level
functions in the Selection file, not methods under its
`@dataclass(frozen=True...)` classes. The existing development-guide limitation
therefore remains true after the candidate upgrade.

### Cosmic Ray

`[D]` Cosmic Ray 8.7.0 declares Python `>=3.9`, but its package classifiers and
CI matrix stop at Python 3.13. `[E]` It nevertheless installed, baselined, and
initialized the current Petrus targets under Python 3.14. That proves this
source subset works; it does not create an upstream Python 3.14 support claim.

`[E]` Cosmic Ray initialized 645 work items over the same two source files:

```text
marking.py                 386
selection/__init__.py     259
total                     645
```

Of those, 242 work items, 37.5%, replace `|` in postponed type annotations with
one of eleven arithmetic or bitwise operators. A representative mutation
changed this parameter without changing runtime behavior:

```diff
-identity: int | None = None,
+identity: int ^ None = None,
```

`[E]` All 35 focused tests still passed and Cosmic Ray classified that mutant as
`survived`. The operator filter can exclude the whole `BitOr` replacement
family, but cannot distinguish type unions from meaningful runtime `|`
operations. Line filtering would require project-maintained source ranges.

`[D]` Cosmic Ray runs one configured test command per mutant. It does not learn
which pytest tests reach a mutation. Its local distributor is serial; parallel
execution requires separately prepared HTTP worker checkouts. A SQLite session
can resume pending work, but source, test, or relevant configuration changes
require reinitializing the session. Cosmic Ray also treats an ordinary nonzero
test-command exit, including collection/import failure, as a killed mutant; the
8.7 implementation treats timeout the same way despite older documentation
saying timeout is incompetent.

These result semantics conflict with Petrus's current diagnostic posture. A
mutation tool should expose untested behavior and invalid/noisy mutations, not
let them silently become survivors or successful kills.

## Comparison

| Criterion | Mutmut 3.7 | Cosmic Ray 8.7 | Petrus judgment |
| --- | --- | --- | --- |
| Python 3.14 | Official classifier and project-specific support evidence `[D/E]` | Local Petrus probe passes, upstream CI/classifiers stop at 3.13 `[D/E]` | Mutmut |
| Test selection | Learns tests reaching each function `[D]` | Runs one manually selected command for every mutant `[D]` | Mutmut |
| Local concurrency | Fork-based workers; Petrus currently chooses one `[D]` | Serial local distributor `[D]` | Mutmut |
| Incremental work | Function/result cache; 3.7 adds dependency/config invalidation `[D]` | Resume pending SQLite work; manually rebuild after changes `[D]` | Mutmut |
| Result classification | Separates survived, no-tests, timeout, suspicious, segfault, and other states `[D/E]` | Coarser exit-code interpretation; no related-test/no-tests state `[D]` | Mutmut |
| Syntax reach | Functions and eligible methods; properties and current decorated Selection classes omitted `[E]` | Module-level code, properties, decorators, and class methods `[D/E]` | Cosmic Ray, but not enough to switch |
| Operator control | Fixed built-ins; source/function selection and pragmas `[D]` | 213 named built-ins, regex filtering, custom provider plugins `[D/E]` | Cosmic Ray |
| Noise on Petrus typing | Annotations skipped `[D/E]` | 242 meaningless `|` annotation mutants in this probe `[E]` | Mutmut |
| Reports and gates | TUI, show/apply, JSON stats; external score policy needed `[D]` | Text, HTML, XML, JSON dump, badge, native survival threshold `[D]` | Cosmic Ray, but Petrus intentionally has no score gate |
| Distribution/platform | Requires `fork`; Windows needs WSL `[D]` | OS-independent package and HTTP workers `[D]` | Cosmic Ray only if those constraints become relevant |

Both projects are active: Mutmut 3.7.0 was released on 2026-07-31 and Cosmic
Ray 8.7.0 on 2026-08-09. `[D]` Maintenance activity and major version numbers do
not decide the fit.

## Disposition

No tool switch and no standing dual-tool setup are recommended. No roadmap,
debt, product principle, runtime documentation, or decision record changes are
required. The current development guide remains accurate.

Promote a maintenance change only if the Navigator chooses to upgrade Mutmut to
3.7. Reopen the Cosmic Ray option if one of these conditions appears:

- mutation of properties, decorated classes, or module-level executable code
  becomes a required recurring diagnostic;
- Petrus needs project-specific mutation operators;
- Cosmic Ray gains official Python 3.14 coverage and annotation-aware operator
  behavior; or
- remote mutation distribution becomes more valuable than related-test
  selection and simple local execution.
