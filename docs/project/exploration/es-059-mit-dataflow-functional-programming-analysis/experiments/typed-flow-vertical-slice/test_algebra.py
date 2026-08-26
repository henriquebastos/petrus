"""Immutable source values and pre-motion composition refusals."""

import dataclasses

import pytest

from petrus.motus.activity import activity

from algebra import (
    CompositionError,
    Decision,
    await_event,
    drop,
    effect,
    lifecycle,
    machine,
    on,
)
from domain import (
    CIObserved,
    DomainConverter,
    HeadObserved,
    HumanNeeded,
    Ignored,
    Ladder,
    ReadinessState,
    RepairLanded,
    RepairRequested,
    RerunAccepted,
    RerunRequested,
)


def _admit_head(event: HeadObserved) -> ReadinessState:
    return ReadinessState(
        head=event.head,
        generation=event.generation,
        lineage=event.lineage,
        ladder=Ladder(event.lineage, None, False, False, None),
        publication_operation=None,
    )


def _route(state: ReadinessState, event: CIObserved) -> Decision[ReadinessState, RerunRequested | Ignored]:
    raise NotImplementedError("pure fixture; never executed by these tests")


@activity(converter=DomainConverter())
def _rerun(request: RerunRequested) -> RerunAccepted:
    raise NotImplementedError("fixture Activity; construction must never execute it")


@activity(converter=DomainConverter())
def _repair(request: RepairRequested) -> RepairLanded:
    raise NotImplementedError("fixture Activity; construction must never execute it")


def _flow():
    return machine(
        "mini",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", _admit_head),
            on(await_event("ci", CIObserved))
            .decide("route", _route)
            .choose({RerunRequested: effect("rerun", _rerun), Ignored: drop()}),
        ),
    )


def test_flow_values_are_immutable_and_construction_performs_no_motion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    flow = _flow()

    # The fixture Activities raise if executed, so equal repeated construction
    # is also evidence that authoring runs no Activity, Engine, or History.
    assert flow == _flow()
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(dataclasses.FrozenInstanceError):
        flow.name = "renamed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        flow.handlers[0].steps = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        flow.handlers[0].trigger.id = "renamed"


def test_composition_refuses_mismatched_ports_at_both_source_locations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def route_failed(state: ReadinessState, event: CIObserved) -> Decision[ReadinessState, RerunRequested]:
        raise NotImplementedError

    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).decide("route_failed", route_failed).choose(
            {RerunRequested: effect("repair", _repair)}
        )

    message = str(caught.value)
    assert "produces RerunRequested" in message
    assert "accepts RepairRequested" in message
    assert "[route_failed]" in message
    assert "[repair]" in message
    assert message.count("test_algebra.py") == 2
    assert list(tmp_path.iterdir()) == []  # refused before any History file exists


def test_choose_refuses_a_missing_outcome_before_lowering(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def route(state: ReadinessState, event: CIObserved) -> Decision[ReadinessState, RerunRequested | HumanNeeded]:
        raise NotImplementedError

    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).decide("route", route).choose({RerunRequested: effect("rerun", _rerun)})

    message = str(caught.value)
    assert "[route] has no branch for HumanNeeded" in message
    assert "test_algebra.py" in message  # the decide's authored source location
    assert list(tmp_path.iterdir()) == []  # refused before any History file exists


def test_duplicate_authored_ids_name_both_sources():
    with pytest.raises(CompositionError) as caught:
        machine(
            "mini",
            lifecycle=lifecycle("branch"),
            handlers=(
                on(await_event("dup", HeadObserved)),
                on(await_event("dup", CIObserved)),
            ),
        )

    message = str(caught.value)
    assert "duplicate authored id" in message
    assert "[dup]" in message
    assert message.count("test_algebra.py") == 2

    # Two constructs sharing one source line still collide by id alone.
    with pytest.raises(CompositionError, match=r"duplicate authored id \[twin\]"):
        machine(
            "mini",
            lifecycle=lifecycle("branch"),
            handlers=(on(await_event("twin", HeadObserved)), on(await_event("twin", CIObserved))),  # one line
        )


def test_distinct_types_with_the_same_nominal_name_are_refused():
    other = dataclasses.make_dataclass("CIObserved", [("head", str)], frozen=True)

    with pytest.raises(CompositionError, match="nominal name 'CIObserved'"):
        machine(
            "mini",
            lifecycle=lifecycle("branch"),
            handlers=(
                on(await_event("a", CIObserved)),
                on(await_event("b", other)),
            ),
        )
