"""Host Catalog registration, compatibility, and Episode snapshot behavior."""

from __future__ import annotations

from itertools import permutations

import pytest
from hypothesis import given, settings, strategies as st

from petrus.agenticus.catalog.descriptor import (
    CapabilityDescriptor,
    CompatibilityRequirement,
    DescriptorIdentity,
    DescriptorKind,
)
from petrus.agenticus.catalog.resolution import (
    AmbiguousRegistrationError,
    AmbiguousSelectionError,
    Catalog,
    CompatibilityIssueCode,
    DuplicateRegistrationError,
    DuplicateSelectionError,
    ResolutionRequest,
    ResolutionSnapshot,
    SelectionError,
    UnknownRegistrationError,
)
from petrus.agenticus.runtime.profiles import RUNTIME_PROFILES, TerritoryProfile


def _descriptor(
    kind: DescriptorKind,
    name: str,
    *,
    version: int = 1,
    offers: frozenset[str] = frozenset(),
    requires: tuple[CompatibilityRequirement, ...] = (),
) -> CapabilityDescriptor:
    return CapabilityDescriptor(DescriptorIdentity(kind, name, version), offers, requires)


def _catalog(*descriptors: CapabilityDescriptor, enabled: bool = True) -> Catalog:
    catalog = Catalog()
    for descriptor in descriptors:
        catalog.register(descriptor)
        if enabled:
            catalog.enable(descriptor.identity)
    return catalog


def _components_for(runtime: CapabilityDescriptor) -> tuple[CapabilityDescriptor, ...]:
    components = [runtime]
    for requirement in runtime.requires:
        name = requirement.name or f"test.{runtime.identity.name}.{requirement.kind.value}"
        components.append(_descriptor(requirement.kind, name, offers=requirement.capabilities))
    return tuple(components)


def _issue_pairs(result) -> set[tuple[str, str]]:
    return {(issue.code, issue.subject) for issue in result.issues}


def test_registration_is_disabled_by_default_and_enablement_is_exact() -> None:
    runtime = _descriptor(DescriptorKind.RUNTIME, "runtime")
    catalog = Catalog()

    catalog.register(runtime)

    assert catalog.inspect() == (catalog.inspect()[0],)
    assert catalog.inspect()[0].descriptor is runtime
    assert catalog.inspect()[0].enabled is False
    assert catalog.resolve(ResolutionRequest((runtime.identity,))).incompatibilities[0].issues[0].code == "not-enabled"
    with pytest.raises(UnknownRegistrationError):
        catalog.enable(DescriptorIdentity(DescriptorKind.RUNTIME, "other", 1))

    catalog.enable(runtime.identity)
    assert catalog.resolve(ResolutionRequest((runtime.identity,))).compatible is True


def test_duplicate_and_conflicting_registration_envelopes_are_refused_without_mutation() -> None:
    descriptor = _descriptor(DescriptorKind.RUNTIME, "runtime", offers=frozenset({"one"}))
    conflict = _descriptor(DescriptorKind.RUNTIME, "runtime", offers=frozenset({"two"}))
    catalog = Catalog()
    catalog.register(descriptor)
    revision = catalog.revision

    with pytest.raises(DuplicateRegistrationError):
        catalog.register(descriptor)
    with pytest.raises(AmbiguousRegistrationError):
        catalog.register(conflict)

    assert catalog.revision == revision
    assert catalog.inspect()[0].descriptor is descriptor


@pytest.mark.parametrize(
    "requirements",
    (
        (
            CompatibilityRequirement(DescriptorKind.CONNECTION, "one", 1, frozenset()),
            CompatibilityRequirement(DescriptorKind.CONNECTION, "two", 1, frozenset()),
        ),
        (
            CompatibilityRequirement(DescriptorKind.CONNECTION, None, 1, frozenset()),
            CompatibilityRequirement(DescriptorKind.CONNECTION, None, 2, frozenset()),
        ),
    ),
)
def test_registration_refuses_same_kind_requirements_one_selection_cannot_satisfy(requirements) -> None:
    catalog = Catalog()

    with pytest.raises(AmbiguousRegistrationError):
        catalog.register(_descriptor(DescriptorKind.RUNTIME, "runtime", requires=requirements))

    assert catalog.revision == 0
    assert catalog.inspect() == ()


def test_compatible_same_kind_requirements_share_one_exact_selection() -> None:
    requirements = (
        CompatibilityRequirement(DescriptorKind.CONNECTION, None, 1, frozenset({"provider.codex"})),
        CompatibilityRequirement(DescriptorKind.CONNECTION, "account", 1, frozenset({"authority.ready"})),
    )
    runtime = _descriptor(DescriptorKind.RUNTIME, "runtime", requires=requirements)
    account = _descriptor(
        DescriptorKind.CONNECTION,
        "account",
        offers=frozenset({"provider.codex", "authority.ready"}),
    )

    resolution = _catalog(runtime, account).resolve(ResolutionRequest((runtime.identity, account.identity)))

    assert resolution.compatible is True


def test_request_refuses_duplicate_and_ambiguous_selections() -> None:
    runtime = DescriptorIdentity(DescriptorKind.RUNTIME, "one", 1)
    other_runtime = DescriptorIdentity(DescriptorKind.RUNTIME, "two", 1)

    with pytest.raises(DuplicateSelectionError):
        ResolutionRequest((runtime, runtime))
    with pytest.raises(AmbiguousSelectionError):
        ResolutionRequest((runtime, other_runtime))
    with pytest.raises(SelectionError, match="runtime"):
        ResolutionRequest((DescriptorIdentity(DescriptorKind.CONNECTION, "account", 1),))


def test_resolution_reports_every_typed_incompatibility_in_stable_order() -> None:
    requirements = (
        CompatibilityRequirement(DescriptorKind.CONNECTION, "expected-account", 1, frozenset({"provider.codex"})),
        CompatibilityRequirement(DescriptorKind.HANDS, None, 1, frozenset({"workspace.read", "workspace.write"})),
        CompatibilityRequirement(DescriptorKind.TERRITORY, "motus.gondolin", 1, frozenset()),
        CompatibilityRequirement(DescriptorKind.CONTINUATION, "codex.native", 1, frozenset()),
        CompatibilityRequirement(DescriptorKind.EFFECT, None, 1, frozenset({"effect.host-fenced"})),
    )
    runtime = _descriptor(DescriptorKind.RUNTIME, "codex.a3", requires=requirements)
    connection = _descriptor(DescriptorKind.CONNECTION, "wrong-account", version=2)
    hands = _descriptor(DescriptorKind.HANDS, "hands", offers=frozenset({"workspace.read"}))
    territory = _descriptor(DescriptorKind.TERRITORY, "motus.e2b")
    continuation = DescriptorIdentity(DescriptorKind.CONTINUATION, "codex.native", 1)
    catalog = _catalog(runtime, connection, hands, territory)
    catalog.disable(hands.identity)
    request = ResolutionRequest(
        (runtime.identity, connection.identity, hands.identity, territory.identity, continuation)
    )

    resolution = catalog.resolve(request)
    by_candidate = {result.candidate: result for result in resolution.results}

    assert resolution.compatible is False
    assert resolution.snapshot is None
    assert _issue_pairs(by_candidate[runtime.identity]) == {
        (CompatibilityIssueCode.NAME_MISMATCH, "expected-account"),
        (CompatibilityIssueCode.VERSION_MISMATCH, "connection@1"),
        (CompatibilityIssueCode.MISSING_CAPABILITY, "provider.codex"),
        (CompatibilityIssueCode.SELECTION_NOT_ENABLED, "hands"),
        (CompatibilityIssueCode.MISSING_CAPABILITY, "workspace.write"),
        (CompatibilityIssueCode.NAME_MISMATCH, "motus.gondolin"),
        (CompatibilityIssueCode.SELECTION_NOT_REGISTERED, "codex.native"),
        (CompatibilityIssueCode.MISSING_SELECTION, "effect"),
    }
    assert _issue_pairs(by_candidate[hands.identity]) == {(CompatibilityIssueCode.NOT_ENABLED, "hands")}
    assert _issue_pairs(by_candidate[continuation]) == {(CompatibilityIssueCode.NOT_REGISTERED, "codex.native")}
    assert tuple(by_candidate[runtime.identity].issues) == tuple(sorted(by_candidate[runtime.identity].issues))


def test_catalog_never_substitutes_enabled_provider_account_runtime_territory_or_continuation() -> None:
    requirements = (
        CompatibilityRequirement(DescriptorKind.CONNECTION, None, 1, frozenset({"provider.codex"})),
        CompatibilityRequirement(DescriptorKind.TERRITORY, "motus.gondolin", 1, frozenset()),
        CompatibilityRequirement(DescriptorKind.CONTINUATION, "codex.native", 1, frozenset()),
    )
    requested_runtime = _descriptor(DescriptorKind.RUNTIME, "codex", requires=requirements)
    substitute_runtime = _descriptor(DescriptorKind.RUNTIME, "other")
    requested_account = _descriptor(
        DescriptorKind.CONNECTION, "account-requested", offers=frozenset({"provider.other"})
    )
    substitute_account = _descriptor(
        DescriptorKind.CONNECTION, "account-compatible", offers=frozenset({"provider.codex"})
    )
    requested_territory = _descriptor(DescriptorKind.TERRITORY, "motus.e2b")
    substitute_territory = _descriptor(DescriptorKind.TERRITORY, "motus.gondolin")
    requested_continuation = _descriptor(DescriptorKind.CONTINUATION, "other.native")
    substitute_continuation = _descriptor(DescriptorKind.CONTINUATION, "codex.native")
    catalog = _catalog(
        requested_runtime,
        substitute_runtime,
        requested_account,
        substitute_account,
        requested_territory,
        substitute_territory,
        requested_continuation,
        substitute_continuation,
    )

    resolution = catalog.resolve(
        ResolutionRequest(
            (
                requested_runtime.identity,
                requested_account.identity,
                requested_territory.identity,
                requested_continuation.identity,
            )
        )
    )

    assert resolution.compatible is False
    runtime_result = next(result for result in resolution.results if result.candidate == requested_runtime.identity)
    assert _issue_pairs(runtime_result) == {
        (CompatibilityIssueCode.MISSING_CAPABILITY, "provider.codex"),
        (CompatibilityIssueCode.NAME_MISMATCH, "motus.gondolin"),
        (CompatibilityIssueCode.NAME_MISMATCH, "codex.native"),
    }


def test_successful_episode_snapshot_is_immutable_across_later_catalog_changes() -> None:
    runtime = RUNTIME_PROFILES[0]
    components = _components_for(runtime)
    catalog = _catalog(*components)
    request = ResolutionRequest(tuple(component.identity for component in components))

    resolution = catalog.resolve(request)
    assert resolution.snapshot is not None
    before = resolution.snapshot.to_data()
    revision = resolution.snapshot.catalog_revision

    territory = next(component for component in components if component.identity.kind is DescriptorKind.TERRITORY)
    catalog.disable(territory.identity)
    catalog.register(_descriptor(DescriptorKind.CONNECTION, "later-account", offers=frozenset({"connection.amp"})))

    assert resolution.snapshot.to_data() == before
    assert ResolutionSnapshot.from_data(before) == resolution.snapshot
    assert resolution.snapshot.catalog_revision == revision
    assert catalog.revision > revision
    assert catalog.resolve(request).compatible is False


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data | {"unexpected": True},
        lambda data: data | {"schema_version": 2},
        lambda data: data | {"catalog_revision": True},
        lambda data: data | {"descriptors": {}},
    ),
)
def test_resolution_snapshot_decoder_refuses_noncanonical_data(mutation) -> None:
    runtime = _descriptor(DescriptorKind.RUNTIME, "runtime")
    snapshot = _catalog(runtime).resolve(ResolutionRequest((runtime.identity,))).snapshot
    assert snapshot is not None

    with pytest.raises((TypeError, ValueError)):
        ResolutionSnapshot.from_data(mutation(snapshot.to_data()))


@settings(max_examples=40, deadline=None)
@given(st.permutations(tuple(range(7))), st.permutations(tuple(range(7))))
def test_registration_and_selection_order_are_deterministic(
    registration_order: list[int],
    selection_order: list[int],
) -> None:
    components = _components_for(RUNTIME_PROFILES[0])
    assert len(components) == 7
    catalog = Catalog()
    for index in registration_order:
        catalog.register(components[index])
    for index in reversed(registration_order):
        catalog.enable(components[index].identity)

    result = catalog.resolve(ResolutionRequest(tuple(components[index].identity for index in selection_order)))

    assert result.compatible is True
    assert result.snapshot is not None
    assert (
        result.snapshot.to_data()
        == _catalog(*components)
        .resolve(ResolutionRequest(tuple(component.identity for component in components)))
        .snapshot.to_data()
    )
    assert catalog.inspect() == tuple(sorted(catalog.inspect(), key=lambda entry: entry.descriptor.identity))


@pytest.mark.parametrize("runtime", RUNTIME_PROFILES, ids=lambda profile: profile.identity.name)
def test_every_planned_runtime_territory_profile_resolves_from_exact_ds1_envelopes(runtime) -> None:
    components = _components_for(runtime)

    resolution = _catalog(*components).resolve(
        ResolutionRequest(tuple(component.identity for component in reversed(components)))
    )

    assert resolution.compatible is True
    assert resolution.snapshot is not None
    assert resolution.snapshot.descriptor(DescriptorKind.RUNTIME) == runtime


@pytest.mark.parametrize("runtime", RUNTIME_PROFILES, ids=lambda profile: profile.identity.name)
def test_every_planned_profile_refuses_a_different_explicit_hands_territory(runtime) -> None:
    components = list(_components_for(runtime))
    territory_index = next(
        index for index, component in enumerate(components) if component.identity.kind is DescriptorKind.TERRITORY
    )
    requirement = next(requirement for requirement in runtime.requires if requirement.kind is DescriptorKind.TERRITORY)
    alternate = next(territory for territory in TerritoryProfile if territory.value != requirement.name)
    components[territory_index] = _descriptor(DescriptorKind.TERRITORY, alternate.value)

    resolution = _catalog(*components).resolve(ResolutionRequest(tuple(component.identity for component in components)))

    runtime_result = next(result for result in resolution.results if result.candidate == runtime.identity)
    assert _issue_pairs(runtime_result) == {(CompatibilityIssueCode.NAME_MISMATCH, requirement.name)}


def test_all_permutations_of_inspection_are_canonical_for_a_small_catalog() -> None:
    descriptors = (
        _descriptor(DescriptorKind.RUNTIME, "runtime"),
        _descriptor(DescriptorKind.CONNECTION, "connection"),
        _descriptor(DescriptorKind.TERRITORY, "territory"),
    )
    observations = set()
    for order in permutations(descriptors):
        catalog = _catalog(*order, enabled=False)
        observations.add(tuple(entry.descriptor.identity for entry in catalog.inspect()))

    assert len(observations) == 1
