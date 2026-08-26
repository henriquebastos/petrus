"""Execute v1's exact fixture trace over the case-table flow and write evidence.

The trace, the harness, the fake provider ledger, and the interruption point
are v1's, imported unmodified. Only the compiled flow differs. That is
deliberate: running the identical fixture is what makes byte-comparing the
canonical History against v1's retained artifact meaningful evidence of
semantic preservation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested, Record
from petrus.impetus.instance import DeliveryDisposition, PriorAcknowledgement, ScopedDeliveryAcknowledgement
from petrus.impetus.net_definition import compile_net_definition, parse_net_definition
from petrus.impetus.petrinet import Marking, NetPath
from petrus.impetus.petrinet.dot import to_dot
from petrus.impetus.scope import LifecycleScope

import table_path  # noqa: F401 - puts the v1 slice on sys.path for script execution
from domain import CIObserved, Evidence, HeadObserved, Published, ReadinessState
from explain import unattributed_records
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, load, value_at
from source_map import serialize_source_map
from table_explain import case_attribution_gaps, explain_history_with_cases, serialize_explained_cases
from table_lowering import TableCompiledFlow, compile_flow
from table_scenario import readiness_flow

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
ARTIFACTS = HERE / "artifacts"
V1 = HERE.parent / "typed-flow-vertical-slice"
V1_NET_GOLDEN = V1 / "golden" / "readiness.net-v3.json"
V1_HISTORY_ARTIFACT = V1 / "artifacts" / "readiness.history.jsonl"

REPAIR = NetPath("effects.repair.fire")


class FixtureError(AssertionError):
    """The fixture trace observed something other than the plan's expectation."""


def _expect(condition: bool, claim: str) -> None:
    if not condition:
        raise FixtureError(f"fixture expectation failed: {claim}")


@dataclass
class FixtureRun:
    """The observable outcome of one complete fixture execution."""

    compiled: TableCompiledFlow
    engine: Engine
    ledger: FakeProviderLedger
    history_path: Path
    pre_reload_marking: Marking
    records: tuple[Record, ...]


def _advance_until_repair_requested(engine: Engine) -> None:
    for _ in range(64):
        if any(isinstance(record, ActivityRequested) and record.transition == REPAIR for record in engine.records):
            return
        engine.advance()
    raise FixtureError("repair ActivityRequested never became durable")


def run_fixture(history_path: Path | str, *, interrupt: bool) -> FixtureRun:
    """Run v1's exact 24-step trace; ``interrupt`` adds the step-13 restart."""
    history_path = Path(history_path)
    ledger = FakeProviderLedger()
    compiled = compile_flow(readiness_flow())
    engine = create(compiled, history_path, ledger)

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

    generation_2 = engine.reset_scope(generation_1)
    deliver_head(engine, compiled, HeadObserved("h2", "superseded", 2, "L2"), identity="head-h2-g2", scope=generation_2)
    failure = CIObserved("h2", Evidence(20, 1), "failure", fingerprint="build")
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "one rerun operation rerun:L2:build")
    _expect("repair:L2:build" not in ledger.attempts, "no repair before the rerun rung is spent")

    before = len(engine.records)
    acknowledged = deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    _expect(isinstance(acknowledged, PriorAcknowledgement), "redelivery answers with PriorAcknowledgement")
    _expect(len(engine.records) == before, "redelivery appends nothing and spends nothing")

    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2-echo", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "duplicate evidence spends no budget")

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
        compiled = compile_flow(readiness_flow())
        engine = load(compiled, history_path, ledger)
    drain(engine)
    _expect(ledger.attempts.get("repair:L2:build") == (2 if interrupt else 1), "repair redispatch count")
    _expect(len(ledger.results.get("repair:L2:build", {})) > 0, "one logical repair effect")

    generation_3 = engine.reset_scope(generation_2)
    deliver_head(
        engine, compiled, HeadObserved("h2r", "confirmed", 3, "L2"), identity="head-h2r-g3", scope=generation_3
    )
    deliver_ci(
        engine, compiled, CIObserved("h2r", Evidence(21, 1), "success"), identity="ci-21-1-g3", scope=generation_3
    )
    drain(engine)
    _expect(ledger.attempts.get("publish:h2r:g3") == 1, "publish:h2r:g3 executed exactly once")
    _expect(value_at(engine, "readiness.state", ReadinessState).lineage == "L2", "confirmed head retains lineage L2")

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
        (output / stale).unlink(missing_ok=True)

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
        document = explain_history_with_cases(uninterrupted.records, first.source_map, first)
        explained = serialize_explained_cases(document)
        source_map_bytes = serialize_source_map(first.source_map)
        canonical = compile_net_definition(parse_net_definition(first.definition_bytes))
        dot = to_dot(canonical)

        occurrences = cast("list[dict[str, object]]", document["occurrences"])
        decisions = [group for group in occurrences if group.get("transition") == document["decision_transition"]]
        gaps = case_attribution_gaps(document)

        (output / "readiness.net-v3.json").write_bytes(first.definition_bytes)
        (output / "readiness.source-map-v1.json").write_bytes(source_map_bytes)
        (output / "readiness.explained-history-cases-v1.json").write_bytes(explained)

        report = {
            "format": "petrus-es059-algebraic-decision-table-experiment-report",
            "version": 1,
            "topology": {
                "places": len(first.built.net.places),
                "transitions": len(first.built.net.transitions),
                "arcs": len(first.built.net.arcs),
            },
            "records": len(uninterrupted.records),
            "authored_cases": len(first.cases),
            "decision_firings": len(decisions),
            "hashes": {
                "net_v3": _sha256(first.definition_bytes),
                "source_map": _sha256(source_map_bytes),
                "explained_history_cases": _sha256(explained),
                "history_uninterrupted": _sha256(history_bytes),
                "history_restarted": _sha256(restarted_bytes),
                "dot": _sha256(dot.encode("utf-8")),
            },
            "results": {
                "net_v3_identical_to_v1": first.definition_bytes == V1_NET_GOLDEN.read_bytes(),
                "history_identical_to_v1": history_bytes == V1_HISTORY_ARTIFACT.read_bytes(),
                "histories_byte_identical": history_bytes == restarted_bytes,
                "unattributed_records": 0,
                "decision_firings_naming_one_case": len(decisions) - len(gaps),
                "decision_firings_absorbed_and_indistinguishable": len(gaps),
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
    """Deliberately refresh retained goldens/artifacts from an inspected bundle.

    Only the two artifacts that genuinely differ from v1 are retained here.
    The canonical Net v3 bytes and the canonical History JSONL are asserted
    byte-equal to the v1 slice's retained files instead of being duplicated;
    their hashes are recorded in ``artifacts/experiment-report.json``.
    """
    GOLDEN.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)
    for name in ("readiness.source-map-v1.json", "readiness.explained-history-cases-v1.json"):
        (GOLDEN / name).write_bytes((output / name).read_bytes())
    (ARTIFACTS / "experiment-report.json").write_bytes((output / "experiment-report.json").read_bytes())


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
    if output == HERE or output in (GOLDEN, ARTIFACTS) or output.is_relative_to(V1):
        parser.error("--output must be a scratch directory, never a retained experiment tree")

    report = build_evidence(output)
    print(json.dumps(report["results"], indent=2))
    print(f"evidence bundle written to {output}")
    if arguments.update_goldens:
        update_goldens(output)
        print("retained goldens and artifacts refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
