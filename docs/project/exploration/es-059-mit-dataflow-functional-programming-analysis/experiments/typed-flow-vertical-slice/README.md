# Typed functional flow vertical slice

Executable experiment for ES-059's bounded question: can one Hamsterdan-shaped
durable workflow be authored as a small typed, functional value and lowered
deterministically into the current canonical Petrus Net v3 while preserving
every durable boundary, replay, resume, byte-stable topology, and
source-to-History attribution?

The authoritative brief is [`../../experiment-plan.md`](../../experiment-plan.md).
This directory is disposable Exploration evidence, not a public API, runtime
change, or roadmap story. Nothing here may leak outside
`docs/project/exploration/es-059-.../experiments/typed-flow-vertical-slice/`.

## Layout

| File | Role |
| --- | --- |
| `domain.py` | Frozen domain dataclasses, JSON-faithful encode/decode, converter |
| `algebra.py` | Immutable typed source values and composition checks |
| `lowering.py` | One pure compilation passage source → `NetSpec` → canonical Net v3 |
| `source_map.py` | Deterministic experiment-only source-map sidecar |
| `scenario.py` | The authored readiness flow and its pure domain functions |
| `harness.py` | Test/application assembly around the current Engine |
| `explain.py` | Join canonical History records to the source map |
| `run_experiment.py` | Execute the exact fixture and write the evidence bundle |
| `golden/` | Retained deterministic goldens (Net v3, source map, explained History) |
| `artifacts/` | Retained DOT source and machine-readable experiment report |
| `report.md` | The human-readable Experience Report |

## Commands

From the Petrus repository root:

```bash
EXP=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/typed-flow-vertical-slice

UV_FROZEN=1 uv run pytest -q "$EXP"

UV_FROZEN=1 uv run python "$EXP/run_experiment.py" --output /tmp/petrus-es-059-typed-flow
```

`run_experiment.py` writes to a caller-supplied output directory and refuses
to overwrite retained goldens unless `--update-goldens` is passed after all
in-memory checks pass. Tests never rewrite tracked artifacts.

## Boundary

Out of bounds: `src/petrus/**`, `tests/**`, `spec/**`, Hamsterdan imports or
checkouts, external services, credentials, a second scheduler/event
log/workflow interpreter, and any generalized package. If a claim requires a
production change, the experiment stops at the red test and documents the
missing seam.
