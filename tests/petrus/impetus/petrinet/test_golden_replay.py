"""Every normative Impetus golden fixture replays through public runtime APIs."""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.harness import TRACES, fixture_names, load_fixture, replay


def test_manifest_hashes_every_normative_fixture() -> None:
    manifest = json.loads((TRACES / "manifest.json").read_text())
    assert manifest["format"] == "petrus-impetus-golden-trace-manifest"
    assert manifest["version"] == 2
    files = [entry["file"] for entry in manifest["fixtures"]]
    names = [entry["name"] for entry in manifest["fixtures"]]
    assert len(files) == len(set(files))
    assert len(names) == len(set(names))
    assert files == [f"{name}.json" for name in names]
    assert set(files) == {path.name for path in TRACES.glob("*.json")} - {"manifest.json"}
    for entry in manifest["fixtures"]:
        payload = (TRACES / entry["file"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert len(json.loads(payload)["walk"]) == entry["walkSteps"]


def test_migration_contracts_are_visible_in_raw_fixtures() -> None:
    per_arc = load_fixture("per_arc_passthrough")
    assert per_arc["walk"][0]["outcome"]["produced"] == [
        {"place": place, "token": {"color": "X", "data": {"n": value}}}
        for place in ("left", "right")
        for value in (1, 2)
    ]
    assert all(produced["token"]["color"] != "Config" for produced in per_arc["walk"][0]["outcome"]["produced"])

    guarded = load_fixture("guard_enumeration")["walk"][0]["candidatesBefore"]
    assert [(binding["transition"], binding["consumed"][0]["tokens"][0]["data"]["amount"]) for binding in guarded] == [
        ("accept", 150),
        ("reject", 40),
    ]

    records = [record["record"] for record in load_fixture("source_delivery")["history"]]
    assert records.index("ExternalEventDelivered") < records.index("FiringBegun") < records.index("TokensProduced")

    produced = load_fixture("heterogeneous_fanout")["walk"][0]["outcome"]["produced"]
    assert [(entry["place"], entry["token"]["color"]) for entry in produced] == [
        ("approved", "ApprovalNotice"),
        ("ledger", "LedgerEntry"),
    ]


@pytest.mark.parametrize("name", fixture_names())
def test_normative_fixture_replays(name: str):
    replay(load_fixture(name))
