"""Static runtime profile descriptors and non-vacuous CV16 qualification targets.

This module contains no adapter or provider SDK imports. A profile describes a
planned composition only; catalog presence and a binding target do not claim
installation, live execution, or product support. The supported CV16 surface is
the separately named Pi A2 Local scripted host-lifecycle conformance route.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from petrus.agenticus.catalog.descriptor import (
    CapabilityDescriptor,
    CompatibilityRequirement,
    DescriptorIdentity,
    DescriptorKind,
)


class RuntimeFamily(StrEnum):
    AMP = "amp"
    CODEX = "codex"
    CLAUDE = "claude"
    PI_NATIVE = "pi.native"
    PI_APPLICATION_OWNED = "pi.application-owned"
    AGENT_AS_NET = "agent-as-net"


class TerritoryProfile(StrEnum):
    """The selected Episode Hands territory.

    Collocated A2/A3 profiles place the runtime there too. Split A4/A5 profiles
    keep Brain/runtime placement independent and bind only their Hands to this
    territory identity.
    """

    PROVIDER_MANAGED = "amp.provider-managed"
    LOCAL = "motus.local"
    DOCKER = "motus.docker"
    GONDOLIN = "motus.gondolin"
    E2B = "motus.e2b"


class EmbodimentArchetype(StrEnum):
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"
    A5 = "A5"


class QualificationExpectation(StrEnum):
    """Whether live qualification is binding, still open, or structurally excluded."""

    BINDING_TARGET = "binding-target"
    UNQUALIFIED = "unqualified"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RuntimeTerritoryProfile:
    """One explicit runtime-family × Episode-Hands-territory qualification cell."""

    family: RuntimeFamily
    territory: TerritoryProfile
    expectation: QualificationExpectation
    reason: str
    archetype: EmbodimentArchetype | None = None
    descriptor: CapabilityDescriptor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.family, RuntimeFamily):
            raise TypeError("runtime profile family must be RuntimeFamily")
        if not isinstance(self.territory, TerritoryProfile):
            raise TypeError("runtime profile territory must be TerritoryProfile")
        if not isinstance(self.expectation, QualificationExpectation):
            raise TypeError("runtime profile expectation must be QualificationExpectation")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("runtime profile reason must be non-empty")
        if self.expectation is QualificationExpectation.BINDING_TARGET:
            if self.archetype is None or self.descriptor is None:
                raise ValueError("a binding runtime profile needs an archetype and descriptor")
        elif self.archetype is not None or self.descriptor is not None:
            raise ValueError("an unqualified or unsupported cell must not expose a runtime descriptor")


def territory_identity(territory: TerritoryProfile) -> DescriptorIdentity:
    """Return the exact version-1 Episode Hands territory envelope identity.

    Motus owns the meaning of territory capability keys. These static profiles
    therefore pin identity only and require no interpreted territory keys.
    """

    if not isinstance(territory, TerritoryProfile):
        raise TypeError("territory must be TerritoryProfile")
    return DescriptorIdentity(DescriptorKind.TERRITORY, territory.value, 1)


def runtime_territory_profile(family: RuntimeFamily, territory: TerritoryProfile) -> RuntimeTerritoryProfile:
    """Inspect one exact static table cell."""

    if not isinstance(family, RuntimeFamily) or not isinstance(territory, TerritoryProfile):
        raise TypeError("runtime profile lookup requires RuntimeFamily and TerritoryProfile")
    return next(cell for cell in RUNTIME_TERRITORY_PROFILES if cell.family is family and cell.territory is territory)


def _runtime_descriptor(
    name: str,
    archetype: EmbodimentArchetype,
    territory: TerritoryProfile,
    *,
    connection: str,
    program: str,
    hands: str,
    continuation: str,
    loop: str,
    topology: str,
    additional_offers: frozenset[str] = frozenset(),
) -> CapabilityDescriptor:
    requirements = (
        _capability_requirement(DescriptorKind.CONNECTION, connection),
        _capability_requirement(DescriptorKind.PROGRAM, program),
        _capability_requirement(DescriptorKind.HANDS, hands),
        CompatibilityRequirement(
            kind=DescriptorKind.TERRITORY,
            name=territory.value,
            contract_version=1,
            capabilities=frozenset(),
        ),
        _capability_requirement(DescriptorKind.CONTINUATION, continuation),
        _capability_requirement(DescriptorKind.EFFECT, "effect.host-fenced"),
    )
    return CapabilityDescriptor(
        identity=DescriptorIdentity(DescriptorKind.RUNTIME, name, 1),
        offers=frozenset({f"archetype.{archetype.value.lower()}", loop, topology, *additional_offers}),
        requires=requirements,
    )


def _capability_requirement(kind: DescriptorKind, capability: str) -> CompatibilityRequirement:
    return CompatibilityRequirement(kind=kind, name=None, contract_version=1, capabilities=frozenset({capability}))


AMP_A1 = _runtime_descriptor(
    "amp.a1.provider-managed",
    EmbodimentArchetype.A1,
    TerritoryProfile.PROVIDER_MANAGED,
    connection="connection.amp",
    program="program.provider-owned",
    hands="hands.provider-managed",
    continuation="continuation.amp-native",
    loop="loop.provider-owned",
    topology="topology.provider-managed",
)
CODEX_A2_LOCAL = _runtime_descriptor(
    "codex.a2.local",
    EmbodimentArchetype.A2,
    TerritoryProfile.LOCAL,
    connection="connection.codex",
    program="program.provider-owned",
    hands="hands.collocated",
    continuation="continuation.codex-native",
    loop="loop.provider-owned",
    topology="topology.durable-collocated",
)
CODEX_A3_GONDOLIN = _runtime_descriptor(
    "codex.a3.gondolin",
    EmbodimentArchetype.A3,
    TerritoryProfile.GONDOLIN,
    connection="connection.codex",
    program="program.provider-owned",
    hands="hands.collocated",
    continuation="continuation.codex-native",
    loop="loop.provider-owned",
    topology="topology.ephemeral-collocated",
    additional_offers=frozenset({"topology.episode-collocated"}),
)
CLAUDE_A2_LOCAL = _runtime_descriptor(
    "claude.a2.local",
    EmbodimentArchetype.A2,
    TerritoryProfile.LOCAL,
    connection="connection.claude",
    program="program.provider-owned",
    hands="hands.collocated",
    continuation="continuation.claude-native",
    loop="loop.provider-owned",
    topology="topology.durable-collocated",
)
PI_NATIVE_A2_LOCAL = _runtime_descriptor(
    "pi.native.a2.local",
    EmbodimentArchetype.A2,
    TerritoryProfile.LOCAL,
    connection="connection.pi-compatible",
    program="program.harness-owned",
    hands="hands.collocated",
    continuation="continuation.pi-native",
    loop="loop.harness-owned",
    topology="topology.durable-collocated",
)
PI_NATIVE_A4_GONDOLIN = _runtime_descriptor(
    "pi.native.a4.gondolin",
    EmbodimentArchetype.A4,
    TerritoryProfile.GONDOLIN,
    connection="connection.pi-compatible",
    program="program.harness-owned",
    hands="hands.capability-scoped",
    continuation="continuation.pi-native",
    loop="loop.harness-owned",
    topology="topology.split",
)
PI_NATIVE_A4_E2B = _runtime_descriptor(
    "pi.native.a4.e2b",
    EmbodimentArchetype.A4,
    TerritoryProfile.E2B,
    connection="connection.pi-compatible",
    program="program.harness-owned",
    hands="hands.capability-scoped",
    continuation="continuation.pi-native",
    loop="loop.harness-owned",
    topology="topology.split",
)
PI_APPLICATION_A5_GONDOLIN = _runtime_descriptor(
    "pi.application-owned.a5.gondolin",
    EmbodimentArchetype.A5,
    TerritoryProfile.GONDOLIN,
    connection="connection.pi-compatible",
    program="program.application-owned",
    hands="hands.capability-scoped",
    continuation="continuation.application-owned",
    loop="loop.application-owned",
    topology="topology.split",
)
PI_APPLICATION_A5_E2B = _runtime_descriptor(
    "pi.application-owned.a5.e2b",
    EmbodimentArchetype.A5,
    TerritoryProfile.E2B,
    connection="connection.pi-compatible",
    program="program.application-owned",
    hands="hands.capability-scoped",
    continuation="continuation.application-owned",
    loop="loop.application-owned",
    topology="topology.split",
)
AGENT_AS_NET_A5_LOCAL = _runtime_descriptor(
    "agent-as-net.a5.local",
    EmbodimentArchetype.A5,
    TerritoryProfile.LOCAL,
    connection="connection.model-call",
    program="program.net-owned",
    hands="hands.capability-scoped",
    continuation="continuation.net-owned",
    loop="loop.net-owned",
    topology="topology.application-owned",
)


def _binding(
    family: RuntimeFamily,
    territory: TerritoryProfile,
    archetype: EmbodimentArchetype,
    descriptor: CapabilityDescriptor,
    reason: str,
) -> RuntimeTerritoryProfile:
    return RuntimeTerritoryProfile(
        family=family,
        territory=territory,
        expectation=QualificationExpectation.BINDING_TARGET,
        reason=reason,
        archetype=archetype,
        descriptor=descriptor,
    )


def _open(
    family: RuntimeFamily,
    territory: TerritoryProfile,
    expectation: QualificationExpectation,
    reason: str,
) -> RuntimeTerritoryProfile:
    return RuntimeTerritoryProfile(family, territory, expectation, reason)


RUNTIME_TERRITORY_PROFILES = (
    _binding(
        RuntimeFamily.AMP,
        TerritoryProfile.PROVIDER_MANAGED,
        EmbodimentArchetype.A1,
        AMP_A1,
        "DS9 binding Amp A1 provider-managed cell",
    ),
    _open(
        RuntimeFamily.AMP,
        TerritoryProfile.LOCAL,
        QualificationExpectation.UNQUALIFIED,
        "CV10 private evidence is not an independently leased Agenticus profile",
    ),
    _open(
        RuntimeFamily.AMP,
        TerritoryProfile.DOCKER,
        QualificationExpectation.UNQUALIFIED,
        "CV10 private evidence is not an independently leased Agenticus profile",
    ),
    _open(
        RuntimeFamily.AMP,
        TerritoryProfile.GONDOLIN,
        QualificationExpectation.UNQUALIFIED,
        "CV10 cell is credential-blocked and A1 has no external Hands claim",
    ),
    _open(
        RuntimeFamily.AMP,
        TerritoryProfile.E2B,
        QualificationExpectation.UNQUALIFIED,
        "CV10 private evidence is not an independently leased Agenticus profile",
    ),
    _open(
        RuntimeFamily.CODEX,
        TerritoryProfile.PROVIDER_MANAGED,
        QualificationExpectation.UNQUALIFIED,
        "no provider-managed Codex profile is qualified",
    ),
    _binding(
        RuntimeFamily.CODEX, TerritoryProfile.LOCAL, EmbodimentArchetype.A2, CODEX_A2_LOCAL, "DS9 binding Codex A2 cell"
    ),
    _open(
        RuntimeFamily.CODEX,
        TerritoryProfile.DOCKER,
        QualificationExpectation.UNQUALIFIED,
        "possible A3 cell; not binding",
    ),
    _binding(
        RuntimeFamily.CODEX,
        TerritoryProfile.GONDOLIN,
        EmbodimentArchetype.A3,
        CODEX_A3_GONDOLIN,
        "DS9 binding Codex A3 cell grounded by ES-049",
    ),
    _open(
        RuntimeFamily.CODEX, TerritoryProfile.E2B, QualificationExpectation.UNQUALIFIED, "possible A3 cell; not binding"
    ),
    _open(
        RuntimeFamily.CLAUDE,
        TerritoryProfile.PROVIDER_MANAGED,
        QualificationExpectation.UNQUALIFIED,
        "no provider-managed Claude profile is qualified",
    ),
    _binding(
        RuntimeFamily.CLAUDE,
        TerritoryProfile.LOCAL,
        EmbodimentArchetype.A2,
        CLAUDE_A2_LOCAL,
        "DS9 binding Claude A2 cell",
    ),
    _open(
        RuntimeFamily.CLAUDE,
        TerritoryProfile.DOCKER,
        QualificationExpectation.UNQUALIFIED,
        "A3 needs provider qualification",
    ),
    _open(
        RuntimeFamily.CLAUDE,
        TerritoryProfile.GONDOLIN,
        QualificationExpectation.UNQUALIFIED,
        "A3 needs provider qualification",
    ),
    _open(
        RuntimeFamily.CLAUDE,
        TerritoryProfile.E2B,
        QualificationExpectation.UNQUALIFIED,
        "A3 needs provider qualification",
    ),
    _open(
        RuntimeFamily.PI_NATIVE,
        TerritoryProfile.PROVIDER_MANAGED,
        QualificationExpectation.UNQUALIFIED,
        "no provider-managed Pi native profile is qualified",
    ),
    _binding(
        RuntimeFamily.PI_NATIVE,
        TerritoryProfile.LOCAL,
        EmbodimentArchetype.A2,
        PI_NATIVE_A2_LOCAL,
        "DS9 binding Pi A2 cell",
    ),
    _open(
        RuntimeFamily.PI_NATIVE,
        TerritoryProfile.DOCKER,
        QualificationExpectation.UNQUALIFIED,
        "possible A4 Hands; not binding",
    ),
    _binding(
        RuntimeFamily.PI_NATIVE,
        TerritoryProfile.GONDOLIN,
        EmbodimentArchetype.A4,
        PI_NATIVE_A4_GONDOLIN,
        "DS9 binding Pi A4 Gondolin Hands cell",
    ),
    _binding(
        RuntimeFamily.PI_NATIVE,
        TerritoryProfile.E2B,
        EmbodimentArchetype.A4,
        PI_NATIVE_A4_E2B,
        "DS9 binding Pi A4 E2B Hands cell",
    ),
    _open(
        RuntimeFamily.PI_APPLICATION_OWNED,
        TerritoryProfile.PROVIDER_MANAGED,
        QualificationExpectation.UNSUPPORTED,
        "application-owned progression requires host-owned Hands",
    ),
    _open(
        RuntimeFamily.PI_APPLICATION_OWNED,
        TerritoryProfile.LOCAL,
        QualificationExpectation.UNQUALIFIED,
        "possible A5 Hands; DS9 binds the ES-049 replacement pair",
    ),
    _open(
        RuntimeFamily.PI_APPLICATION_OWNED,
        TerritoryProfile.DOCKER,
        QualificationExpectation.UNQUALIFIED,
        "possible A5 Hands; DS9 binds the ES-049 replacement pair",
    ),
    _binding(
        RuntimeFamily.PI_APPLICATION_OWNED,
        TerritoryProfile.GONDOLIN,
        EmbodimentArchetype.A5,
        PI_APPLICATION_A5_GONDOLIN,
        "DS9 binding Pi A5 Gondolin Hands cell",
    ),
    _binding(
        RuntimeFamily.PI_APPLICATION_OWNED,
        TerritoryProfile.E2B,
        EmbodimentArchetype.A5,
        PI_APPLICATION_A5_E2B,
        "DS9 binding Pi A5 E2B Hands cell",
    ),
    _open(
        RuntimeFamily.AGENT_AS_NET,
        TerritoryProfile.PROVIDER_MANAGED,
        QualificationExpectation.UNSUPPORTED,
        "Net-owned progression requires an Agenticus Hands attachment",
    ),
    _binding(
        RuntimeFamily.AGENT_AS_NET,
        TerritoryProfile.LOCAL,
        EmbodimentArchetype.A5,
        AGENT_AS_NET_A5_LOCAL,
        "DS10 binding future Net-owned A5 profile",
    ),
    _open(
        RuntimeFamily.AGENT_AS_NET,
        TerritoryProfile.DOCKER,
        QualificationExpectation.UNQUALIFIED,
        "future DS10 pressure",
    ),
    _open(
        RuntimeFamily.AGENT_AS_NET,
        TerritoryProfile.GONDOLIN,
        QualificationExpectation.UNQUALIFIED,
        "future DS10 pressure",
    ),
    _open(
        RuntimeFamily.AGENT_AS_NET, TerritoryProfile.E2B, QualificationExpectation.UNQUALIFIED, "future DS10 pressure"
    ),
)

RUNTIME_PROFILES = tuple(cell.descriptor for cell in RUNTIME_TERRITORY_PROFILES if cell.descriptor is not None)

# CV16 binds these generic Hands territory lifecycles independently of which
# DS9/DS10 runtime profile consumes them. This avoids manufacturing arbitrary
# Docker runtime cells merely to make the wider Hands obligation visible.
CV16_HANDS_TERRITORY_TARGETS = frozenset(
    {TerritoryProfile.LOCAL, TerritoryProfile.DOCKER, TerritoryProfile.GONDOLIN, TerritoryProfile.E2B}
)
