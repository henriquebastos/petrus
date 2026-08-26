# Guarded decision net — ES-059 experiment v2 (Option B)

A bounded variant of the
[typed functional flow vertical slice](../typed-flow-vertical-slice/README.md).
It changes exactly one thing and measures the consequences.

| | v1 — typed-flow-vertical-slice | v2 — this experiment |
| --- | --- | --- |
| CI routing source | one pure `route_ci` returning `Decision[state, outcome-union]` | five `rung(...)` values: predicate + fold + emission |
| Lowered to | ONE transition `readiness.route_ci.fire` | FIVE guarded transitions `readiness.route_ci.<rung>.fire` |
| Exclusivity | by construction (one function, one return) | an authoring obligation, checked only by tests |
| "Nothing happened" | an `Ignored` outcome that produced no token | its own named firing, `…route_ci.ignore.fire` |
| Topology | 14 places, 9 transitions, 28 arcs | 14 places, **13** transitions, **40** arcs |
| History per decision | one firing, one row set | **unchanged** — one firing, one row set |

Read [report.md](report.md) for the verdict and the evidence.

## Boundary

Everything here lives in this one directory. No file under `src/petrus/**`,
`spec/**`, `tests/**`, ES-059's `index.md`, or the v1 slice was created or
modified. v1's `domain`, `scenario`, `lowering`, `source_map`, `harness`, and
`explain` modules are imported **read-only**; every module and test file here
carries a `guarded_` prefix so the two experiments share one `sys.path`
without colliding.

## Files

```text
conftest.py                  puts this directory and v1's on sys.path
guarded_algebra.py           Rung/Branch source values, branch(...).route(...)
guarded_lowering.py          v1's _Lowering subclassed: one transition per rung
guarded_scenario.py          the authored flow: five predicates, five folds
guarded_counterexample.py    two deliberately broken toy branches
guarded_harness.py           the one door v1 lacks: an explicit selection policy
guarded_run.py               v1's exact 24-step fixture + the evidence bundle
test_guarded_algebra.py      pre-motion composition refusals
test_guarded_lowering.py     topology, guards, source map, byte stability
test_guarded_exclusivity.py  the proof obligation and the counterexamples
test_guarded_scenario.py     Engine-executed semantics, rung by rung
test_guarded_resume.py       restart, replay, attribution, grain vs v1
golden/                      net-v3, source-map, explained-history
artifacts/                   DOT, machine-readable report, fixture History
```

## Commands

From the Petrus repository root:

```bash
EXP=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments
V2="$EXP/guarded-decision-net"

# All 52 tests.
UV_FROZEN=1 uv run pytest -q "$V2"

# v1 must still pass untouched (27 tests).
UV_FROZEN=1 uv run pytest -q "$EXP/typed-flow-vertical-slice"

# Style and types.
UV_FROZEN=1 uv run ruff check "$V2"
UV_FROZEN=1 uv run ruff format --check "$V2"
UV_FROZEN=1 uv run ty check \
  --extra-search-path "$EXP/typed-flow-vertical-slice" --extra-search-path "$V2" \
  "$V2/guarded_algebra.py" "$V2/guarded_lowering.py" "$V2/guarded_scenario.py" \
  "$V2/guarded_harness.py" "$V2/guarded_counterexample.py" "$V2/guarded_run.py"

# Evidence bundle: scratch first, retained goldens only after inspection.
rm -rf /tmp/petrus-es-059-guarded
UV_FROZEN=1 uv run python "$V2/guarded_run.py" --output /tmp/petrus-es-059-guarded
UV_FROZEN=1 uv run python "$V2/guarded_run.py" --output /tmp/petrus-es-059-guarded --update-goldens
```

`ty` needs both `--extra-search-path` flags because this experiment's modules
import v1's from a sibling directory; `pytest` gets the same paths from
`conftest.py`. The repository's `testpaths = ["tests"]` excludes this
directory, so these tests run only when invoked explicitly.
