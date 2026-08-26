"""Execute v1's exact 24-step fixture over the guarded decision net.

Adapted from ``../typed-flow-vertical-slice/run_experiment.py``: the trace,
the deterministic strings, integer time zero, the interruption point, and
every domain expectation are identical, so the two experiments' *outcomes* are
directly comparable. What differs is the topology under them, so this runner
additionally pins the **grain claim**: exactly one rung transition fires per
delivered CI observation, and the fired rung is named in canonical History.

Canonical History bytes cannot equal v1's — the transition paths differ — so
the byte-equality claim is made between this experiment's own uninterrupted
and restarted runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_V1 = HERE.parent / "typed-flow-vertical-slice"
for _directory in (str(_V1), str(HERE)):  # importable as a script as well as under pytest
    if _directory not in sys.path:
        sys.path.insert(0, _directory)

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from petrus.engine import Engine  # noqa: E402
from petrus.impetus.history import ActivityCompleted, ActivityRequested, ExternalEventDelivered, Record  # noqa: E402
from petrus.impetus.instance import (  # noqa: E402
    DeliveryDisposition,
    PriorAcknowledgement,
    ScopedDeliveryAcknowledgement,
)
from petrus.impetus.net_definition import compile_net_definition, parse_net_definition  # noqa: E402
from petrus.impetus.petrinet import Marking, NetPath  # noqa: E402
from petrus.impetus.petrinet.dot import to_dot  # noqa: E402
from petrus.impetus.scope import LifecycleScope  # noqa: E402

from domain import CIObserved, Evidence, HeadObserved, Published, ReadinessState  # noqa: E402
from explain import explain_history, serialize_explained, unattributed_records  # noqa: E402
from guarded_harness import fired_rungs  # noqa: E402
from guarded_lowering import compile_guarded  # noqa: E402
from guarded_scenario import guarded_readiness_flow  # noqa: E402
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, load, value_at  # noqa: E402
from lowering import CompiledFlow  # noqa: E402
from source_map import serialize_source_map  # noqa: E402

GOLDEN = HERE / "golden"
ARTIFACTS = HERE / "artifacts"

BRANCH = "readiness.route_ci"
REPAIR = NetPath("effects.repair.fire")


class FixtureError(AssertionError):
    """The fixture trace observed something other than the plan's expectation."""


def _expect(condition: bool, claim: str) -> None:
    if not condition:
        raise FixtureError(f"fixture expectation failed: {claim}")


@dataclass
class FixtureRun:
    """The observable outcome of one complete fixture execution."""

    compiled: CompiledFlow
    engine: Engine  # the final reloaded Engine, still open
    ledger: FakeProviderLedger
    history_path: Path
    pre_reload_marking: Marking
    records: tuple[Record, ...]


def _advance_until_repair_requested(engine) -> None:
    """Advance only until the repair ``ActivityRequested`` is durable."""
    for _ in range(64):
        if any(isinstance(record, ActivityRequested) and record.transition == REPAIR for record in engine.records):
            return
        engine.advance()
    raise FixtureError("repair ActivityRequested never became durable")


def ci_deliveries(records: tuple[Record, ...]) -> int:
    """How many CI observations actually crossed the ingress source transition."""
    source = NetPath("ingress.ci")
    return sum(isinstance(record, ExternalEventDelivered) and record.source == source for record in records)


def compile_fixture_flow() -> CompiledFlow:
    """Re-author and re-compile the source value; used by every reconstruction."""
    return compile_guarded(guarded_readiness_flow()).compiled


# Complexity exception: this is the plan's 24-step fixture in one readable trace.
def run_fixture(history_path: Path | str, *, interrupt: bool) -> FixtureRun:  # noqa: C901
    """Run v1's exact 24-step trace; ``interrupt`` adds the step-13 restart."""
    history_path = Path(history_path)
    ledger = FakeProviderLedger()
    compiled = compile_fixture_flow()
    engine = create(compiled, history_path, ledger)

    # 1-5: create, open branch generation 1, admit h1, publish on clean CI.
    generation_1 = engine.open_scope("branch")
    deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=generation_1)
    deliver_ci(
        engine, compiled, CIObserved("h1", Evidence(10, 1), "success"), identity="ci-10-1-g1", scope=generation_1
    )
    drain(engine)
    _expect(ledger.attempts.get("publish:h1:g1") == 1, "publish:h1:g1 executed exactly once")
    _expect(
        value_at(engine, "terminal.published", Published) == Published("h1", 1, "publish:h1:g1"),
        "Published(h1, g1) reached its terminal",
    )
    _expect(fired_rungs(engine.records, BRANCH) == ("publish",), "clean CI fired the publish rung")

    # 6-9: reset to generation 2, admit superseded h2, first failure reruns.
    generation_2 = engine.reset_scope(generation_1)
    deliver_head(engine, compiled, HeadObserved("h2", "superseded", 2, "L2"), identity="head-h2-g2", scope=generation_2)
    failure = CIObserved("h2", Evidence(20, 1), "failure", fingerprint="build")
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "one rerun operation rerun:L2:build")
    _expect("repair:L2:build" not in ledger.attempts, "no repair before the rerun rung is spent")
    _expect(fired_rungs(engine.records, BRANCH) == ("publish", "rerun"), "first failure fired the rerun rung")

    # 10: exact redelivery is answered with the prior acknowledgement.
    before = len(engine.records)
    acknowledged = deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    _expect(isinstance(acknowledged, PriorAcknowledgement), "redelivery answers with PriorAcknowledgement")
    _expect(len(engine.records) == before, "redelivery appends nothing and spends nothing")

    # 11: same evidence under a new ingress identity is absorbed by the ignore
    # rung — and, unlike v1, the absorption names itself in canonical History.
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2-echo", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "duplicate evidence spends no budget")
    _expect(
        fired_rungs(engine.records, BRANCH) == ("publish", "rerun", "ignore"),
        "duplicate evidence fired the ignore rung, durably named",
    )

    # 12-15: strictly newer matching failure requests repair; optionally
    # interrupt after its durable request and reconstruct everything live.
    deliver_ci(
        engine,
        compiled,
        CIObserved("h2", Evidence(20, 2), "failure", fingerprint="build"),
        identity="ci-20-2-g2",
        scope=generation_2,
    )
    if interrupt:
        _advance_until_repair_requested(engine)
        repair_request = next(
            record for record in engine.records if isinstance(record, ActivityRequested) and record.transition == REPAIR
        )
        _expect(
            not any(
                isinstance(record, ActivityCompleted) and record.occurrence == repair_request.occurrence
                for record in engine.records
            ),
            "interruption lands before the repair terminal is accepted",
        )
        engine.close()
        compiled = compile_fixture_flow()  # reconstruct the source value
        engine = load(compiled, history_path, ledger)  # fresh store, Dispatch, Engine
    drain(engine)
    _expect(ledger.attempts.get("repair:L2:build") == (2 if interrupt else 1), "repair redispatch count")
    _expect(len(ledger.results.get("repair:L2:build", {})) > 0, "one logical repair effect")
    _expect(
        fired_rungs(engine.records, BRANCH) == ("publish", "rerun", "ignore", "repair"),
        "the newer matching failure fired the repair rung",
    )

    # 16-19: confirmed repair head keeps lineage L2 in generation 3.
    generation_3 = engine.reset_scope(generation_2)
    deliver_head(
        engine, compiled, HeadObserved("h2r", "confirmed", 3, "L2"), identity="head-h2r-g3", scope=generation_3
    )
    deliver_ci(
        engine, compiled, CIObserved("h2r", Evidence(21, 1), "success"), identity="ci-21-1-g3", scope=generation_3
    )
    drain(engine)
    _expect(ledger.attempts.get("publish:h2r:g3") == 1, "publish:h2r:g3 executed exactly once")
    state = value_at(engine, "readiness.state", ReadinessState)
    _expect(state.lineage == "L2", "confirmed head retains lineage L2")

    # 20-23: unrelated h3 in generation 4; stale and future scoped deliveries.
    generation_4 = engine.reset_scope(generation_3)
    deliver_head(engine, compiled, HeadObserved("h3", "superseded", 4, "L4"), identity="head-h3-g4", scope=generation_4)
    stale = CIObserved("h3", Evidence(30, 1), "success")
    dropped = deliver_ci(engine, compiled, stale, identity="ci-stale-g3", scope=generation_3)
    _expect(
        dropped == ScopedDeliveryAcknowledgement("ci-stale-g3", DeliveryDisposition.DROPPED, generation_3),
        "closed-generation delivery is durably dropped",
    )
    future = LifecycleScope("branch", 5)
    quarantined = deliver_ci(engine, compiled, stale, identity="ci-future-g5", scope=future)
    _expect(
        quarantined == ScopedDeliveryAcknowledgement("ci-future-g5", DeliveryDisposition.QUARANTINED, future),
        "unproven future-generation delivery is durably quarantined",
    )

    # Grain: one firing per delivered CI observation, no rung bookkeeping.
    rungs = fired_rungs(engine.records, BRANCH)
    _expect(rungs == ("publish", "rerun", "ignore", "repair", "publish"), "exactly one rung fired per CI delivery")
    _expect(len(rungs) == ci_deliveries(engine.records), "rung firings equal admitted CI deliveries")

    # 24: reload once more from the final History.
    pre_reload_marking = engine.marking
    engine.close()
    compiled = compile_fixture_flow()
    engine = load(compiled, history_path, ledger)
    _expect(dict(engine.active_scopes) == {"branch": generation_4}, "active scope is generation 4")
    _expect(engine.marking == pre_reload_marking, "reloaded marking is identical")
    reloaded_state = value_at(engine, "readiness.state", ReadinessState)
    _expect(reloaded_state.head == "h3" and reloaded_state.lineage == "L4", "state is h3/L4")
    _expect(reloaded_state.ladder.fingerprint is None, "generation 4 starts a fresh retry lineage")

    return FixtureRun(
        compiled=compiled,
        engine=engine,
        ledger=ledger,
        history_path=history_path,
        pre_reload_marking=pre_reload_marking,
        records=engine.records,
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_evidence(output: Path) -> dict[str, object]:
    """Run both fixture variants and write the evidence bundle into ``output``."""
    output.mkdir(parents=True, exist_ok=True)
    for stale in ("readiness.history.jsonl", "readiness.history.restarted.jsonl"):
        (output / stale).unlink(missing_ok=True)  # a prior bundle's History would refuse create

    first = compile_guarded(guarded_readiness_flow())
    second = compile_guarded(guarded_readiness_flow())
    if first.compiled.definition_bytes != second.compiled.definition_bytes:
        raise FixtureError("repeated lowering is not byte-stable")

    uninterrupted = run_fixture(output / "readiness.history.jsonl", interrupt=False)
    restarted = run_fixture(output / "readiness.history.restarted.jsonl", interrupt=True)
    try:
        history_bytes = uninterrupted.history_path.read_bytes()
        restarted_bytes = restarted.history_path.read_bytes()
        if history_bytes != restarted_bytes:
            raise FixtureError("restarted and uninterrupted canonical histories differ")
        if uninterrupted.engine.marking != restarted.engine.marking:
            raise FixtureError("restarted and uninterrupted markings differ")

        source_map = first.compiled.source_map
        failures = unattributed_records(uninterrupted.records, source_map)
        if failures:
            raise FixtureError(f"unattributed records: {failures}")
        explained = serialize_explained(explain_history(uninterrupted.records, source_map))
        source_map_bytes = serialize_source_map(source_map)
        canonical = compile_net_definition(parse_net_definition(first.compiled.definition_bytes))
        dot = to_dot(canonical)

        (output / "readiness.net-v3.json").write_bytes(first.compiled.definition_bytes)
        (output / "readiness.source-map-v1.json").write_bytes(source_map_bytes)
        (output / "readiness.explained-history-v1.json").write_bytes(explained)
        (output / "readiness.net.dot").write_text(dot, encoding="utf-8", newline="")

        net = first.compiled.built.net
        report = {
            "format": "petrus-es059-guarded-decision-net-experiment-report",
            "version": 1,
            "variant": "option-b-one-transition-per-rung",
            "topology": {
                "places": len(net.places),
                "transitions": len(net.transitions),
                "arcs": len(net.arcs),
                "guards": len(first.compiled.guards),
            },
            "rungs": [
                {
                    "id": plan.id,
                    "transition": plan.transition,
                    "predicate": plan.predicate,
                    "outcome": plan.outcome,
                    "target": plan.target,
                }
                for plan in first.rungs
            ],
            "records": len(uninterrupted.records),
            "hashes": {
                "net_v3": _sha256(first.compiled.definition_bytes),
                "source_map": _sha256(source_map_bytes),
                "explained_history": _sha256(explained),
                "history_uninterrupted": _sha256(history_bytes),
                "history_restarted": _sha256(restarted_bytes),
                "dot": _sha256(dot.encode("utf-8")),
            },
            "results": {
                "histories_byte_identical": history_bytes == restarted_bytes,
                "unattributed_records": 0,
                "ci_deliveries": ci_deliveries(uninterrupted.records),
                "rung_firings": list(fired_rungs(uninterrupted.records, BRANCH)),
                "operations_uninterrupted": dict(sorted(uninterrupted.ledger.attempts.items())),
                "operations_restarted": dict(sorted(restarted.ledger.attempts.items())),
            },
        }
        (output / "experiment-report.json").write_bytes(
            (json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        )
        return report
    finally:
        uninterrupted.engine.close()
        restarted.engine.close()


def update_goldens(output: Path) -> None:
    """Deliberately refresh retained goldens/artifacts from an inspected bundle."""
    GOLDEN.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)
    for name in ("readiness.net-v3.json", "readiness.source-map-v1.json", "readiness.explained-history-v1.json"):
        (GOLDEN / name).write_bytes((output / name).read_bytes())
    for name in ("readiness.net.dot", "experiment-report.json", "readiness.history.jsonl"):
        (ARTIFACTS / name).write_bytes((output / name).read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="evidence output directory")
    parser.add_argument(
        "--update-goldens",
        action="store_true",
        help="after all in-memory checks pass, refresh the retained goldens and artifacts",
    )
    arguments = parser.parse_args(argv)
    output = arguments.output.resolve()
    if output == HERE or output in (GOLDEN, ARTIFACTS):
        parser.error("--output must be a scratch directory, never the retained experiment tree")

    report = build_evidence(output)
    print(json.dumps(report["results"], indent=2))
    print(f"evidence bundle written to {output}")
    if arguments.update_goldens:
        update_goldens(output)
        print("retained goldens and artifacts refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
