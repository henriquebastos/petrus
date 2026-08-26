"""Immutable rung source values and pre-motion composition refusals."""

import dataclasses

import pytest

from petrus.motus.activity import activity

from algebra import CompositionError, await_event, effect, lifecycle, terminal
from domain import (
    CIObserved,
    DomainConverter,
    HeadObserved,
    HumanNeeded,
    Ladder,
    ReadinessState,
    RepairLanded,
    RepairRequested,
    RerunAccepted,
    RerunRequested,
)
from guarded_algebra import Branch, Rung, guarded_machine, on, rung


def _admit_head(event: HeadObserved) -> ReadinessState:
    return ReadinessState(
        head=event.head,
        generation=event.generation,
        lineage=event.lineage,
        ladder=Ladder(event.lineage, None, False, False, None),
        publication_operation=None,
    )


def _keep(state: ReadinessState, event: CIObserved) -> ReadinessState:
    del event
    return state


def _failed(state: ReadinessState, event: CIObserved) -> bool:
    del state
    return event.conclusion == "failure"


def _clean(state: ReadinessState, event: CIObserved) -> bool:
    del state
    return event.conclusion == "success"


def _request_rerun(state: ReadinessState, event: CIObserved) -> RerunRequested:
    raise NotImplementedError("pure fixture; never executed by these tests")


def _surface_human(state: ReadinessState, event: CIObserved) -> HumanNeeded:
    raise NotImplementedError("pure fixture; never executed by these tests")


@activity(converter=DomainConverter())
def _rerun(request: RerunRequested) -> RerunAccepted:
    raise NotImplementedError("fixture Activity; construction must never execute it")


@activity(converter=DomainConverter())
def _repair(request: RepairRequested) -> RepairLanded:
    raise NotImplementedError("fixture Activity; construction must never execute it")


def _flow():
    return guarded_machine(
        "mini",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", _admit_head),
            on(await_event("ci", CIObserved))
            .branch(
                "route",
                rungs=(
                    rung("ignore", when=_clean, fold=_keep).drop(),
                    rung("rerun", when=_failed, fold=_keep).emit(_request_rerun),
                ),
            )
            .route({RerunRequested: effect("rerun", _rerun)}),
        ),
    )


def test_rung_values_are_immutable_and_construction_performs_no_motion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    flow = _flow()

    # The fixture Activity and emission raise if executed, so equal repeated
    # construction is also evidence that authoring runs no Activity, no
    # predicate, no fold, no Engine, and no History write.
    assert flow == _flow()
    assert list(tmp_path.iterdir()) == []
    [branch] = [step for step in flow.handlers[1].steps if isinstance(step, Branch)]
    assert isinstance(branch.rungs[0], Rung)
    with pytest.raises(dataclasses.FrozenInstanceError):
        branch.rungs[0].id = "renamed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        branch.routes = ()


def test_a_rung_predicate_must_return_bool_for_the_current_typed_guard_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def maybe(state: ReadinessState, event: CIObserved) -> str:
        raise NotImplementedError

    with pytest.raises(CompositionError, match=r"rung \[loose\] when must return bool"):
        rung("loose", when=maybe, fold=_keep)
    assert list(tmp_path.iterdir()) == []  # refused before any History file exists


def test_a_rung_fold_must_reproduce_the_state_baton():
    def wrong(state: ReadinessState, event: CIObserved) -> HumanNeeded:
        raise NotImplementedError

    with pytest.raises(CompositionError, match=r"rung \[bad\] fold returns HumanNeeded"):
        rung("bad", when=_failed, fold=wrong)


def test_a_rung_guarded_over_another_event_names_both_source_locations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def head_shaped(state: ReadinessState, event: HeadObserved) -> bool:
        raise NotImplementedError

    def head_fold(state: ReadinessState, event: HeadObserved) -> ReadinessState:
        raise NotImplementedError

    foreign = rung("foreign", when=head_shaped, fold=head_fold).drop()
    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).branch("route", rungs=(foreign,))

    message = str(caught.value)
    assert "[route] is triggered by CIObserved" in message
    assert "[foreign] accepts HeadObserved" in message
    assert message.count("test_guarded_algebra.py") == 2
    assert list(tmp_path.iterdir()) == []


def test_route_refuses_an_unrouted_rung_outcome_before_lowering(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).branch(
            "route",
            rungs=(
                rung("rerun", when=_failed, fold=_keep).emit(_request_rerun),
                rung("human", when=_clean, fold=_keep).emit(_surface_human),
            ),
        ).route({RerunRequested: effect("rerun", _rerun)})

    message = str(caught.value)
    assert "[route] has no route for HumanNeeded" in message
    assert "test_guarded_algebra.py" in message  # the branch's authored source location
    assert list(tmp_path.iterdir()) == []


def test_route_refuses_a_target_no_rung_emits():
    with pytest.raises(CompositionError, match=r"\[route\] emits no outcome HumanNeeded"):
        on(await_event("ci", CIObserved)).branch(
            "route", rungs=(rung("rerun", when=_failed, fold=_keep).emit(_request_rerun),)
        ).route({RerunRequested: effect("rerun", _rerun), HumanNeeded: terminal("human_needed")})


def test_a_rung_outcome_routed_to_a_mismatched_effect_names_both_locations():
    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).branch(
            "route", rungs=(rung("rerun", when=_failed, fold=_keep).emit(_request_rerun),)
        ).route({RerunRequested: effect("repair", _repair)})

    message = str(caught.value)
    assert "produces RerunRequested" in message
    assert "[repair] accepts RepairRequested" in message
    assert message.count("test_guarded_algebra.py") == 2


def test_duplicate_rung_ids_inside_one_branch_name_both_sources():
    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).branch(
            "route",
            rungs=(
                rung("twin", when=_failed, fold=_keep).drop(),
                rung("twin", when=_clean, fold=_keep).drop(),
            ),
        )

    message = str(caught.value)
    assert "declares rung [twin] twice" in message
    assert message.count("test_guarded_algebra.py") == 2


def test_rung_ids_are_scoped_to_their_branch_but_branch_ids_are_not():
    # A rung named "rerun" and an effect named "rerun" coexist: the rung id is
    # unique within its branch scope, which is exactly how the real flow spells
    # the rerun rung and the rerun Activity.
    assert _flow() == _flow()

    with pytest.raises(CompositionError, match=r"duplicate authored id \[route\]"):
        guarded_machine(
            "mini",
            lifecycle=lifecycle("branch"),
            handlers=(
                on(await_event("head", HeadObserved)).project("admit_head", _admit_head),
                on(await_event("route", CIObserved))
                .branch("route", rungs=(rung("ignore", when=_clean, fold=_keep).drop(),))
                .route({}),
            ),
        )


def test_distinct_types_with_the_same_nominal_name_are_refused_through_a_branch():
    other = dataclasses.make_dataclass("RerunRequested", [("operation", str)], frozen=True)

    def emit_other(state: ReadinessState, event: CIObserved) -> other:  # ty: ignore[invalid-type-form]
        raise NotImplementedError

    with pytest.raises(CompositionError, match="nominal name 'RerunRequested'"):
        guarded_machine(
            "mini",
            lifecycle=lifecycle("branch"),
            handlers=(
                on(await_event("head", HeadObserved)).project("admit_head", _admit_head),
                on(await_event("ci", CIObserved))
                .branch(
                    "route",
                    rungs=(
                        rung("rerun", when=_failed, fold=_keep).emit(_request_rerun),
                        rung("other", when=_clean, fold=_keep).emit(emit_other),
                    ),
                )
                .route({RerunRequested: effect("rerun", _rerun), other: terminal("other")}),
            ),
        )
