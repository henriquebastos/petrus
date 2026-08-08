"""Static runtime profiles remain complete, honest, and provider-independent."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from petrus.agenticus.catalog.descriptor import DescriptorKind
from petrus.agenticus.runtime.profiles import (
    CV16_HANDS_TERRITORY_TARGETS,
    RUNTIME_PROFILES,
    RUNTIME_TERRITORY_PROFILES,
    EmbodimentArchetype,
    QualificationExpectation,
    RuntimeFamily,
    TerritoryProfile,
    runtime_territory_profile,
    territory_identity,
)


BINDING_CELLS = {
    (RuntimeFamily.AMP, TerritoryProfile.PROVIDER_MANAGED, EmbodimentArchetype.A1),
    (RuntimeFamily.CODEX, TerritoryProfile.LOCAL, EmbodimentArchetype.A2),
    (RuntimeFamily.CODEX, TerritoryProfile.GONDOLIN, EmbodimentArchetype.A3),
    (RuntimeFamily.CLAUDE, TerritoryProfile.LOCAL, EmbodimentArchetype.A2),
    (RuntimeFamily.PI_NATIVE, TerritoryProfile.LOCAL, EmbodimentArchetype.A2),
    (RuntimeFamily.PI_NATIVE, TerritoryProfile.GONDOLIN, EmbodimentArchetype.A4),
    (RuntimeFamily.PI_NATIVE, TerritoryProfile.E2B, EmbodimentArchetype.A4),
    (RuntimeFamily.PI_APPLICATION_OWNED, TerritoryProfile.GONDOLIN, EmbodimentArchetype.A5),
    (RuntimeFamily.PI_APPLICATION_OWNED, TerritoryProfile.E2B, EmbodimentArchetype.A5),
    (RuntimeFamily.AGENT_AS_NET, TerritoryProfile.LOCAL, EmbodimentArchetype.A5),
}

STRUCTURALLY_UNSUPPORTED_CELLS = {
    (RuntimeFamily.PI_APPLICATION_OWNED, TerritoryProfile.PROVIDER_MANAGED),
    (RuntimeFamily.AGENT_AS_NET, TerritoryProfile.PROVIDER_MANAGED),
}

PROFILE_OWNERSHIP = {
    "amp.a1.provider-managed": (
        "connection.amp",
        "program.provider-owned",
        "hands.provider-managed",
        "continuation.amp-native",
        "loop.provider-owned",
        "topology.provider-managed",
    ),
    "codex.a2.local": (
        "connection.codex",
        "program.provider-owned",
        "hands.collocated",
        "continuation.codex-native",
        "loop.provider-owned",
        "topology.durable-collocated",
    ),
    "codex.a3.gondolin": (
        "connection.codex",
        "program.provider-owned",
        "hands.collocated",
        "continuation.codex-native",
        "loop.provider-owned",
        "topology.ephemeral-collocated",
    ),
    "claude.a2.local": (
        "connection.claude",
        "program.provider-owned",
        "hands.collocated",
        "continuation.claude-native",
        "loop.provider-owned",
        "topology.durable-collocated",
    ),
    "pi.native.a2.local": (
        "connection.pi-compatible",
        "program.harness-owned",
        "hands.collocated",
        "continuation.pi-native",
        "loop.harness-owned",
        "topology.durable-collocated",
    ),
    "pi.native.a4.gondolin": (
        "connection.pi-compatible",
        "program.harness-owned",
        "hands.capability-scoped",
        "continuation.pi-native",
        "loop.harness-owned",
        "topology.split",
    ),
    "pi.native.a4.e2b": (
        "connection.pi-compatible",
        "program.harness-owned",
        "hands.capability-scoped",
        "continuation.pi-native",
        "loop.harness-owned",
        "topology.split",
    ),
    "pi.application-owned.a5.gondolin": (
        "connection.pi-compatible",
        "program.application-owned",
        "hands.capability-scoped",
        "continuation.application-owned",
        "loop.application-owned",
        "topology.split",
    ),
    "pi.application-owned.a5.e2b": (
        "connection.pi-compatible",
        "program.application-owned",
        "hands.capability-scoped",
        "continuation.application-owned",
        "loop.application-owned",
        "topology.split",
    ),
    "agent-as-net.a5.local": (
        "connection.model-call",
        "program.net-owned",
        "hands.capability-scoped",
        "continuation.net-owned",
        "loop.net-owned",
        "topology.application-owned",
    ),
}


def test_support_table_exhaustively_classifies_every_family_territory_pair() -> None:
    expected = {(family, territory) for family in RuntimeFamily for territory in TerritoryProfile}
    observed = {(cell.family, cell.territory) for cell in RUNTIME_TERRITORY_PROFILES}

    assert observed == expected
    assert len(RUNTIME_TERRITORY_PROFILES) == len(expected)
    assert {
        (cell.family, cell.territory, cell.archetype)
        for cell in RUNTIME_TERRITORY_PROFILES
        if cell.expectation is QualificationExpectation.BINDING_TARGET
    } == BINDING_CELLS
    assert any(cell.expectation is QualificationExpectation.UNQUALIFIED for cell in RUNTIME_TERRITORY_PROFILES)
    assert {
        (cell.family, cell.territory)
        for cell in RUNTIME_TERRITORY_PROFILES
        if cell.expectation is QualificationExpectation.UNSUPPORTED
    } == STRUCTURALLY_UNSUPPORTED_CELLS
    assert CV16_HANDS_TERRITORY_TARGETS == {
        TerritoryProfile.LOCAL,
        TerritoryProfile.DOCKER,
        TerritoryProfile.GONDOLIN,
        TerritoryProfile.E2B,
    }


def test_only_binding_target_cells_publish_descriptors_and_none_claims_live_execution() -> None:
    binding = tuple(
        cell for cell in RUNTIME_TERRITORY_PROFILES if cell.expectation is QualificationExpectation.BINDING_TARGET
    )

    assert tuple(cell.descriptor for cell in binding) == RUNTIME_PROFILES
    assert len({profile.identity for profile in RUNTIME_PROFILES}) == len(BINDING_CELLS)
    for cell in RUNTIME_TERRITORY_PROFILES:
        assert cell.reason
        if cell.expectation is QualificationExpectation.BINDING_TARGET:
            assert cell.descriptor is not None
            assert cell.descriptor.identity.kind is DescriptorKind.RUNTIME
            assert all(offer.startswith(("archetype.", "loop.", "topology.")) for offer in cell.descriptor.offers)
        else:
            assert cell.descriptor is None
            assert cell.archetype is None


@pytest.mark.parametrize("profile", RUNTIME_PROFILES, ids=lambda profile: profile.identity.name)
def test_profile_ownership_vocabulary_remains_explicit(profile) -> None:
    connection, program, hands, continuation, loop, topology = PROFILE_OWNERSHIP[profile.identity.name]
    by_kind = {requirement.kind: requirement for requirement in profile.requires}

    assert by_kind[DescriptorKind.CONNECTION].capabilities == {connection}
    assert by_kind[DescriptorKind.PROGRAM].capabilities == {program}
    assert by_kind[DescriptorKind.HANDS].capabilities == {hands}
    assert by_kind[DescriptorKind.CONTINUATION].capabilities == {continuation}
    assert by_kind[DescriptorKind.EFFECT].capabilities == {"effect.host-fenced"}
    assert loop in profile.offers
    assert topology in profile.offers
    assert len({offer for offer in profile.offers if offer.startswith("archetype.")}) == 1


@pytest.mark.parametrize("cell", RUNTIME_TERRITORY_PROFILES, ids=lambda cell: f"{cell.family}-{cell.territory}")
def test_every_binding_profile_pins_exact_territory_without_interpreting_motus_capability_keys(cell) -> None:
    assert runtime_territory_profile(cell.family, cell.territory) is cell
    if cell.descriptor is None:
        return

    territory_requirements = [
        requirement for requirement in cell.descriptor.requires if requirement.kind is DescriptorKind.TERRITORY
    ]
    assert territory_requirements == [
        next(requirement for requirement in cell.descriptor.requires if requirement.kind is DescriptorKind.TERRITORY)
    ]
    requirement = territory_requirements[0]
    assert requirement.name == cell.territory.value
    assert requirement.contract_version == 1
    assert requirement.capabilities == frozenset()
    assert territory_identity(cell.territory).name == requirement.name


def test_profile_and_catalog_inspection_import_without_optional_provider_sdks() -> None:
    code = r"""
import importlib.abc
import json
import sys

blocked = {'amp', 'anthropic', 'claude_agent_sdk', 'docker', 'e2b', 'gondolin', 'openai'}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in blocked:
            raise AssertionError(f'optional provider import attempted: {fullname}')
        return None

sys.meta_path.insert(0, Blocker())
from petrus.agenticus.catalog.resolution import Catalog
from petrus.agenticus.runtime.profiles import RUNTIME_PROFILES, RUNTIME_TERRITORY_PROFILES

catalog = Catalog()
for descriptor in RUNTIME_PROFILES:
    catalog.register(descriptor)
print(json.dumps({'entries': len(catalog.inspect()), 'cells': len(RUNTIME_TERRITORY_PROFILES)}))
"""

    completed = subprocess.run([sys.executable, "-c", code], check=True, text=True, capture_output=True)

    assert json.loads(completed.stdout) == {"entries": len(BINDING_CELLS), "cells": 30}
