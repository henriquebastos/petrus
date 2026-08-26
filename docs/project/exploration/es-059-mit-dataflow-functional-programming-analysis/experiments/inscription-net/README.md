# Inscription net — ES-059 experiment v4

The fourth spelling of the readiness workflow. Thesis: **impure = transition,
pure = inscription**. The developer authors a combinator expression over rich
domain tokens; the compiler generates the topology *and* the guards.

Read [report.md](report.md) for the result. Read the sibling experiments first
for context: [v1 typed-flow-vertical-slice](../typed-flow-vertical-slice/report.md),
[A algebraic-decision-table](../algebraic-decision-table/report.md), and
[B guarded-decision-net](../guarded-decision-net/report.md).

This is disposable Exploration evidence under ES-059. Nothing here is a public
API, a runtime change, or a roadmap commitment.

## Tree

```text
inscription-net/
  README.md            this file
  report.md            the Experience Report
  conftest.py          sys.path for this directory and the v1 slice
  inet_tokens.py       rich frozen tokens; pure methods are the guard vocabulary
  inet_kernel.py       the seven combinators and every pre-motion refusal
  inet_lowering.py     topology + generated exclusive guards + fused Activity bridge
  inet_scenario.py     THE AUTHORED FLOW (read this one)
  inet_harness.py      Engine/Dispatch/JSONL assembly, no semantics
  inet_explain.py      History attribution, plus the branch-level decision index
  inet_run.py          the fixture trace and the evidence bundle
  test_inet_kernel.py
  test_inet_lowering.py
  test_inet_exclusivity.py
  test_inet_behavior.py
  test_inet_resume.py
  golden/
    inscription.net-v3.json
    inscription.source-map-v1.json
    inscription.explained-history-v1.json
  artifacts/
    inscription.net.dot
    inscription.history.jsonl
    experiment-report.json
```

## Commands

From the repository root:

```bash
EXP=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/inscription-net
V1=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/typed-flow-vertical-slice

UV_FROZEN=1 uv run pytest -q "$EXP"

UV_FROZEN=1 uv run ruff check "$EXP"
UV_FROZEN=1 uv run ruff format --check "$EXP"
UV_FROZEN=1 uv run ty check --extra-search-path "$EXP" --extra-search-path "$V1" "$EXP"/inet_*.py

# Evidence bundle: a scratch directory first, retained goldens only after inspection.
rm -rf /tmp/petrus-es-059-inet
UV_FROZEN=1 PYTHONPATH="$V1:$EXP" uv run python "$EXP/inet_run.py" --output /tmp/petrus-es-059-inet

# The whole ES-059 experiments tree must stay green.
UV_FROZEN=1 uv run pytest -q docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments
```

Regenerate goldens with `--update-goldens` **after** the final `ruff format`
pass: the source map embeds line numbers.
