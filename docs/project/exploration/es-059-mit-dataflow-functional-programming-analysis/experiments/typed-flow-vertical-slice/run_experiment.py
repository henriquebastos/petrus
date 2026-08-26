"""Execute the exact fixture trace and write the deterministic evidence bundle.

The fixture is the experiment plan's 24-step trace: deterministic strings,
integer time zero, no wall clock, no randomness, no environment-dependent
values. ``run_fixture`` is importable by the focused tests; the CLI writes
the evidence bundle into a caller-supplied output directory and only touches
the retained goldens under an explicit ``--update-goldens`` after every
in-memory check has passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested, Record
from petrus.impetus.instance import DeliveryDisposition, PriorAcknowledgement, ScopedDeliveryAcknowledgement
from petrus.impetus.net_definition import compile_net_definition, parse_net_definition
from petrus.impetus.petrinet import Marking, NetPath
from petrus.impetus.petrinet.dot import to_dot
from petrus.impetus.scope import LifecycleScope

from domain import CIObserved, Evidence, HeadObserved, Published, ReadinessState
from explain import explain_history, serialize_explained, unattributed_records
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, load, value_at
from lowering import CompiledFlow, compile_flow
from scenario import readiness_flow
from source_map import serialize_source_map

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
ARTIFACTS = HERE / "artifacts"

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
        outcome = engine.advance()
        del outcome
    raise FixtureError("repair ActivityRequested never became durable")


def run_fixture(history_path: Path | str, *, interrupt: bool) -> FixtureRun:
    """Run the exact 24-step trace; ``interrupt`` adds the step-13 restart."""
    history_path = Path(history_path)
    ledger = FakeProviderLedger()
    compiled = compile_flow(readiness_flow())
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

    # 6-9: reset to generation 2, admit superseded h2, first failure reruns.
    generation_2 = engine.reset_scope(generation_1)
    deliver_head(engine, compiled, HeadObserved("h2", "superseded", 2, "L2"), identity="head-h2-g2", scope=generation_2)
    failure = CIObserved("h2", Evidence(20, 1), "failure", fingerprint="build")
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "one rerun operation rerun:L2:build")
    _expect("repair:L2:build" not in ledger.attempts, "no repair before the rerun rung is spent")

    # 10: exact redelivery is answered with the prior acknowledgement.
    before = len(engine.records)
    acknowledged = deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    _expect(isinstance(acknowledged, PriorAcknowledgement), "redelivery answers with PriorAcknowledgement")
    _expect(len(engine.records) == before, "redelivery appends nothing and spends nothing")

    # 11: same evidence under a new ingress identity is absorbed as Ignored.
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2-echo", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "duplicate evidence spends no budget")

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
        compiled = compile_flow(readiness_flow())  # reconstruct the source value
        engine = load(compiled, history_path, ledger)  # fresh store, Dispatch, Engine
    drain(engine)
    _expect(ledger.attempts.get("repair:L2:build") == (2 if interrupt else 1), "repair redispatch count")
    _expect(len(ledger.results.get("repair:L2:build", {})) > 0, "one logical repair effect")

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

    # 24: reload once more from the final History.
    pre_reload_marking = engine.marking
    engine.close()
    compiled = compile_flow(readiness_flow())
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

    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())
    if first.definition_bytes != second.definition_bytes:
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

        failures = unattributed_records(uninterrupted.records, first.source_map)
        if failures:
            raise FixtureError(f"unattributed records: {failures}")
        explained = serialize_explained(explain_history(uninterrupted.records, first.source_map))
        source_map_bytes = serialize_source_map(first.source_map)
        canonical = compile_net_definition(parse_net_definition(first.definition_bytes))
        dot = to_dot(canonical)

        (output / "readiness.net-v3.json").write_bytes(first.definition_bytes)
        (output / "readiness.source-map-v1.json").write_bytes(source_map_bytes)
        (output / "readiness.explained-history-v1.json").write_bytes(explained)
        (output / "readiness.net.dot").write_text(dot, encoding="utf-8", newline="")

        report = {
            "format": "petrus-es059-typed-flow-experiment-report",
            "version": 1,
            "topology": {
                "places": len(first.built.net.places),
                "transitions": len(first.built.net.transitions),
                "arcs": len(first.built.net.arcs),
            },
            "records": len(uninterrupted.records),
            "hashes": {
                "net_v3": _sha256(first.definition_bytes),
                "source_map": _sha256(source_map_bytes),
                "explained_history": _sha256(explained),
                "history_uninterrupted": _sha256(history_bytes),
                "history_restarted": _sha256(restarted_bytes),
                "dot": _sha256(dot.encode("utf-8")),
            },
            "results": {
                "histories_byte_identical": history_bytes == restarted_bytes,
                "unattributed_records": 0,
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
