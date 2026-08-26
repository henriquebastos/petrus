# Algebraic decision table (ES-059 experiment A)

A bounded follow-up to the committed
[typed-flow vertical slice](../typed-flow-vertical-slice/) ("v1"). v1 proved a
typed functional source can lower to the current canonical Petrus Net v3
without losing a durable boundary. It left one thing opaque: the CI-routing
decision lived inside a single ~60-line pure function, so the *structure* of
the decision — its rungs, their order, what each commits, what each emits —
was invisible to the algebra, to the source map, and to the explained History.

This experiment replaces exactly that one construct. Where v1 wrote

```python
.decide("route_ci", route_ci)
```

v2 writes an ordered, first-match-wins **case table**:

```python
.match(
    "route_ci",
    normalize=refresh_ladder,
    cases=(
        case("foreign",      when=other_head,           fold=keep).drop(),
        case("stale",        when=not_newer,            fold=keep).drop(),
        case("publish",      when=first_clean,          fold=note_publication).emit(request_publication),
        case("published",    when=already_published,    fold=advance).drop(),
        case("unclassified", when=unclassified_failure, fold=advance).drop(),
        case("rerun",        when=rerun_available,      fold=spend_rerun).emit(request_rerun),
        case("repair",       when=repair_available,     fold=spend_repair).emit(request_repair),
        case("human",        when=otherwise,            fold=advance).emit(surface_human_needed),
    ),
)
```

The hard invariant: **one firing and one canonical History row set per
decision, identical grain to v1**. Eight authored rungs lower to exactly one
transition with seven arcs — and, as it turns out, to byte-identical Net v3
bytes and byte-identical canonical History.

The authoritative brief for the shared grain rules, boundary discipline, and
evidence style is [`../../experiment-plan.md`](../../experiment-plan.md). The
result is in [`report.md`](report.md).

## Layout

| File | Role |
| --- | --- |
| `table_algebra.py` | `case` / `otherwise` / `Match`, the table's checks, and its pure evaluator |
| `table_lowering.py` | `_TableLowering`, a subclass of v1's `_Lowering`; one new chain shape |
| `table_scenario.py` | The authored flow: normalize, seven classifiers, five commits, four emissions |
| `table_explain.py` | v1's explained History plus per-firing case attribution |
| `table_run.py` | v1's exact fixture over the table flow; writes the evidence bundle |
| `table_path.py` | `sys.path` bootstrap for direct script execution |
| `conftest.py` | Same bootstrap for pytest (this directory first, then the v1 slice) |
| `golden/` | The two retained artifacts that genuinely differ from v1 |
| `artifacts/` | Machine-readable experiment report (hashes, counts, results) |

Every module and test file is `table_`-prefixed so nothing shadows a v1 module
name on the shared `sys.path`.

### Imported from v1, unmodified

`domain.py`, `algebra.py` (every construct except the decision), `lowering.py`
(`_Lowering`, `FragmentContext`, `FragmentPorts`, `CompiledFlow`),
`source_map.py`, `explain.py`, `harness.py`, and from `scenario.py`:
`admit_head`, `accept_publish`, the three typed fake Activities, the
`publication_gate` descent fragment, and the ordinary helper calculations.
Nothing in `../typed-flow-vertical-slice/` is written to.

### Not retained here

The canonical Net v3 bytes and the canonical History JSONL are **byte-identical
to v1's** retained files, so they are asserted against v1's copies rather than
duplicated. Their hashes are recorded in
[`artifacts/experiment-report.json`](artifacts/experiment-report.json). The DOT
rendering follows from the identical net and is likewise recorded by hash only.

## Commands

From the Petrus repository root:

```bash
EXP=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/algebraic-decision-table
V1=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/typed-flow-vertical-slice

UV_FROZEN=1 uv run pytest -q "$EXP"          # 38 tests
UV_FROZEN=1 uv run pytest -q "$V1"           # 27 tests, unchanged

UV_FROZEN=1 uv run ruff check "$EXP"
UV_FROZEN=1 uv run ruff format --check "$EXP"
UV_FROZEN=1 uv run ty check --extra-search-path "$V1" \
  "$EXP/table_algebra.py" "$EXP/table_lowering.py" "$EXP/table_scenario.py" \
  "$EXP/table_explain.py" "$EXP/table_run.py" "$EXP/table_path.py" "$EXP/conftest.py"

UV_FROZEN=1 uv run python "$EXP/table_run.py" --output /tmp/petrus-es-059-table
```

`ty` needs `--extra-search-path` because this slice imports the v1 modules
from a sibling directory; v1's own command did not.

`table_run.py` writes to a caller-supplied output directory and refuses to
target either retained experiment tree. `--update-goldens` refreshes
`golden/` and `artifacts/` only after every in-memory check has passed.
Regenerate goldens **after** `ruff format`: the source map embeds line numbers.

## Boundary

Out of bounds: `src/petrus/**`, `tests/**`, `spec/**`, every file under
`../typed-flow-vertical-slice/`, ES-059's `index.md` and `experiment-plan.md`,
Hamsterdan imports, external services, credentials, and any generalized
package. This directory is disposable Exploration evidence.
