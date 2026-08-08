"""Shared, provider-neutral descriptor and compatibility result contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from petrus.agenticus.catalog.descriptor import (
    CapabilityDescriptor,
    CompatibilityRequirement,
    DescriptorIdentity,
    DescriptorKind,
)
from petrus.agenticus.catalog.result import CompatibilityIssue, CompatibilityResult

FIXTURE = Path(__file__).parents[1] / "conformance" / "catalog-descriptor-v1.json"
RESULT_FIXTURE = Path(__file__).parents[1] / "conformance" / "catalog-result-v1.json"


def test_versioned_plain_data_fixture_round_trips_without_concrete_adapters() -> None:
    fixture = json.loads(FIXTURE.read_text())

    assert set(fixture) == {"format", "version", "contract", "cases"}
    assert fixture["format"] == "petrus.agenticus.conformance"
    assert fixture["version"] == 1
    assert fixture["contract"] == "catalog.descriptor"
    for case in fixture["cases"]:
        descriptor = CapabilityDescriptor.from_data(case["descriptor"])
        assert descriptor.to_data() == case["descriptor"]


def test_versioned_result_fixture_round_trips_without_concrete_adapters() -> None:
    fixture = json.loads(RESULT_FIXTURE.read_text())

    assert set(fixture) == {"format", "version", "contract", "cases"}
    assert fixture["format"] == "petrus.agenticus.conformance"
    assert fixture["version"] == 1
    assert fixture["contract"] == "catalog.result"
    for case in fixture["cases"]:
        result = CompatibilityResult.from_data(case["result"])
        assert result.to_data() == case["result"]
        assert result.compatible is case["compatible"]


def test_descriptor_values_are_immutable_normalized_and_exactly_versioned() -> None:
    requirement = CompatibilityRequirement(
        kind=DescriptorKind.HANDS,
        name=None,
        contract_version=1,
        capabilities={"workspace.write", "workspace.read"},
    )
    descriptor = CapabilityDescriptor(
        identity=DescriptorIdentity(DescriptorKind.RUNTIME, "pi.application-owned", 1),
        offers={"continuation.opaque", "program.harness-owned"},
        requires=[requirement],
    )

    assert descriptor.offers == frozenset({"continuation.opaque", "program.harness-owned"})
    assert descriptor.requires == (requirement,)
    assert descriptor.to_data()["offers"] == ["continuation.opaque", "program.harness-owned"]
    with pytest.raises(AttributeError):
        descriptor.offers = frozenset()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data | {"unexpected": True},
        lambda data: data | {"schema_version": 2},
        lambda data: data | {"identity": data["identity"] | {"contract_version": True}},
        lambda data: data | {"offers": ["workspace.read", "workspace.read"]},
    ),
)
def test_descriptor_decoder_refuses_ambiguous_or_noncanonical_data(mutation) -> None:
    data = json.loads(FIXTURE.read_text())["cases"][0]["descriptor"]

    with pytest.raises((TypeError, ValueError)):
        CapabilityDescriptor.from_data(mutation(data))


def test_compatibility_result_cannot_claim_success_without_a_candidate() -> None:
    candidate = DescriptorIdentity(DescriptorKind.RUNTIME, "pi.application-owned", 1)
    assert CompatibilityResult(candidate=candidate).compatible is True

    issue = CompatibilityIssue("missing-capability", "workspace.write")
    blocked = CompatibilityResult(candidate=candidate, issues=[issue])
    assert blocked.compatible is False
    assert blocked.issues == (issue,)

    with pytest.raises(ValueError, match="candidate"):
        CompatibilityResult(candidate=None)
