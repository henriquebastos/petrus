"""Execute the fixture trace and write the deterministic evidence bundle.

The trace adapts v1's 24-step fixture *semantics* — the same delivery sequence,
identities, scope resets, and interruption point — to this experiment's topology.
Byte parity with v1 is explicitly not a goal here: the topology, the paths, and
the state representation all differ by design. Self-parity is: the uninterrupted
and restarted runs must produce byte-identical canonical History.

Deterministic strings, integer time zero, no wall clock, no randomness, no
environment-dependent value enters a golden.
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

from inet_explain import explain_history, serialize_explained, unattributed_records
from inet_harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, fired_branches, load, value_at
from inet_lowering import CompiledFlow, compile_flow
from inet_scenario import readiness_flow
from inet_tokens import CIObserved, EvidenceId, HeadFact, HeadObserved, Published
from source_map import serialize_source_map

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
ARTIFACTS = HERE / "artifacts"

REPAIR = NetPath("decide.repair")


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
    branches: tuple[str, ...]


def _advance_until_repair_requested(engine: Engine) -> None:
    """Advance only until the repair ``ActivityRequested`` is durable."""
    for _ in range(64):
        if any(isinstance(record, ActivityRequested) and record.transition == REPAIR for record in engine.records):
            return
        engine.advance()
    raise FixtureError("repair ActivityRequested never became durable")


def run_fixture(history_path: Path | str, *, interrupt: bool) -> FixtureRun:
    """Run the fixture trace; ``interrupt`` adds the restart at the durable request boundary."""
    history_path = Path(history_path)
    ledger = FakeProviderLedger()
    compiled = compile_flow(readiness_flow())
    engine = create(compiled, history_path, ledger)

    # 1-5: create, open branch generation 1, admit h1, publish on clean CI.
    generation_1 = engine.open_scope("branch")
    deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=generation_1)
    deliver_ci(
        engine, compiled, CIObserved("h1", EvidenceId(10, 1), "success"), identity="ci-10-1-g1", scope=generation_1
    )
    drain(engine)
    _expect(ledger.attempts.get("publish:h1:g1") == 1, "publish:h1:g1 executed exactly once")
    _expect(
        value_at(engine, "terminal.published", Published) == Published("publish:h1:g1", "h1", 1),
        "Published(h1, g1) reached its terminal",
    )
    _expect(fired_branches(engine.records) == ("publish",), "one branch firing answered the clean observation")

    # 6-9: reset to generation 2, admit superseded h2, first failure spends the rerun rung.
    generation_2 = engine.reset_scope(generation_1)
    _expect(
        engine.marking.place(NetPath("ladder.rerun")) == () and engine.marking.place(NetPath("readiness.head")) == (),
        "scope reset discarded the whole generation's structural state",
    )
    deliver_head(engine, compiled, HeadObserved("h2", "superseded", 2, "L2"), identity="head-h2-g2", scope=generation_2)
    _expect(
        len(engine.marking.place(NetPath("ladder.rerun"))) == 1
        and len(engine.marking.place(NetPath("ladder.repair"))) == 1,
        "the successor head re-armed both rungs structurally",
    )
    failure = CIObserved("h2", EvidenceId(20, 1), "failure", fingerprint="build")
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "one rerun operation rerun:L2:build")
    _expect("repair:L2:build" not in ledger.attempts, "no repair before the rerun rung is spent")
    _expect(engine.marking.place(NetPath("ladder.rerun")) == (), "the rerun rung is spent: its place is empty")

    # 10: exact redelivery is answered with the prior acknowledgement.
    before = len(engine.records)
    acknowledged = deliver_ci(engine, compiled, failure, identity="ci-20-1-g2", scope=generation_2)
    _expect(isinstance(acknowledged, PriorAcknowledgement), "redelivery answers with PriorAcknowledgement")
    _expect(len(engine.records) == before, "redelivery appends nothing and spends nothing")

    # 11: same evidence under a new ingress identity is durably absorbed as [stale].
    deliver_ci(engine, compiled, failure, identity="ci-20-1-g2-echo", scope=generation_2)
    drain(engine)
    _expect(ledger.attempts.get("rerun:L2:build") == 1, "duplicate evidence spends no budget")
    _expect(fired_branches(engine.records)[-1] == "stale", "the absorbed duplicate names its branch in History")

    # 12-15: strictly newer matching failure spends the repair rung; optionally
    # interrupt after its durable request and reconstruct everything live.
    deliver_ci(
        engine,
        compiled,
        CIObserved("h2", EvidenceId(20, 2), "failure", fingerprint="build"),
        identity="ci-20-2-g2",
        scope=generation_2,
    )
    if interrupt:
        _advance_until_repair_requested(engine)
        request = next(
            record for record in engine.records if isinstance(record, ActivityRequested) and record.transition == REPAIR
        )
        _expect(
            not any(
                isinstance(record, ActivityCompleted) and record.occurrence == request.occurrence
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
    _expect(fired_branches(engine.records)[-1] == "repair", "the repair rung answered, not a second rerun")

    # 16-19: confirmed repair head keeps lineage L2 in generation 3.
    generation_3 = engine.reset_scope(generation_2)
    deliver_head(
        engine, compiled, HeadObserved("h2r", "confirmed", 3, "L2"), identity="head-h2r-g3", scope=generation_3
    )
    deliver_ci(
        engine, compiled, CIObserved("h2r", EvidenceId(21, 1), "success"), identity="ci-21-1-g3", scope=generation_3
    )
    drain(engine)
    _expect(ledger.attempts.get("publish:h2r:g3") == 1, "publish:h2r:g3 executed exactly once")
    head = value_at(engine, "readiness.head", HeadFact)
    _expect(head.lineage == "L2", "confirmed head retains lineage L2")

    # 20-23: unrelated h3 in generation 4; stale and future scoped deliveries.
    generation_4 = engine.reset_scope(generation_3)
    deliver_head(engine, compiled, HeadObserved("h3", "superseded", 4, "L4"), identity="head-h3-g4", scope=generation_4)
    stale = CIObserved("h3", EvidenceId(30, 1), "success")
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
    branches = fired_branches(engine.records)
    engine.close()
    compiled = compile_flow(readiness_flow())
    engine = load(compiled, history_path, ledger)
    _expect(dict(engine.active_scopes) == {"branch": generation_4}, "active scope is generation 4")
    _expect(engine.marking == pre_reload_marking, "reloaded marking is identical")
    reloaded = value_at(engine, "readiness.head", HeadFact)
    _expect(reloaded.head == "h3" and reloaded.lineage == "L4", "state is h3/L4")
    _expect(
        len(engine.marking.place(NetPath("ladder.rerun"))) == 1
        and len(engine.marking.place(NetPath("ladder.repair"))) == 1
        and engine.marking.place(NetPath("publication.admitted")) == (),
        "generation 4 starts with a fresh ladder budget and an open publication latch",
    )

    return FixtureRun(
        compiled=compiled,
        engine=engine,
        ledger=ledger,
        history_path=history_path,
        pre_reload_marking=pre_reload_marking,
        records=engine.records,
        branches=branches,
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


GOLDEN_FILES = (
    "inscription.net-v3.json",
    "inscription.source-map-v1.json",
    "inscription.explained-history-v1.json",
)
ARTIFACT_FILES = ("inscription.net.dot", "experiment-report.json", "inscription.history.jsonl")


def build_evidence(output: Path) -> dict[str, object]:
    """Run both fixture variants and write the evidence bundle into ``output``."""
    output.mkdir(parents=True, exist_ok=True)
    for stale in ("inscription.history.jsonl", "inscription.history.restarted.jsonl"):
        (output / stale).unlink(missing_ok=True)  # a prior bundle's History would refuse create

    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())
    if first.definition_bytes != second.definition_bytes:
        raise FixtureError("repeated lowering is not byte-stable")

    uninterrupted = run_fixture(output / "inscription.history.jsonl", interrupt=False)
    restarted = run_fixture(output / "inscription.history.restarted.jsonl", interrupt=True)
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

        (output / "inscription.net-v3.json").write_bytes(first.definition_bytes)
        (output / "inscription.source-map-v1.json").write_bytes(source_map_bytes)
        (output / "inscription.explained-history-v1.json").write_bytes(explained)
        (output / "inscription.net.dot").write_text(dot, encoding="utf-8", newline="")

        deliveries = len([branch for branch in uninterrupted.branches])
        report = {
            "format": "petrus-es059-inscription-net-experiment-report",
            "version": 1,
            "topology": {
                "places": len(first.built.net.places),
                "transitions": len(first.built.net.transitions),
                "arcs": len(first.built.net.arcs),
                "guards": len(first.guards),
                "cel_arc_filters": len([arc for arc in first.built.net.arcs if arc.filter is not None]),
            },
            "records": len(uninterrupted.records),
            "grain": {
                "decision_firings": deliveries,
                "branches_fired": list(uninterrupted.branches),
                "firings_per_delivered_observation": 1,
            },
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
    for name in GOLDEN_FILES:
        (GOLDEN / name).write_bytes((output / name).read_bytes())
    for name in ARTIFACT_FILES:
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
