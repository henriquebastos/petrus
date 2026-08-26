"""Immutable case-table source values and the refusals the table makes possible."""

import dataclasses

import pytest

from petrus.motus.activity import activity

from algebra import CompositionError, await_event, effect, lifecycle, terminal
from domain import (
    CIObserved,
    DomainConverter,
    Evidence,
    HeadObserved,
    HumanNeeded,
    Ladder,
    ReadinessState,
    RepairLanded,
    RepairRequested,
    RerunAccepted,
    RerunRequested,
)
from table_algebra import Match, case, evaluate_match, machine, on, otherwise


def _admit_head(event: HeadObserved) -> ReadinessState:
    return ReadinessState(
        head=event.head,
        generation=event.generation,
        lineage=event.lineage,
        ladder=Ladder(event.lineage, None, False, False, None),
        publication_operation=None,
    )


def _failing(state: ReadinessState, event: CIObserved) -> bool:
    del state
    return event.conclusion == "failure"


def _clean(state: ReadinessState, event: CIObserved) -> bool:
    del state
    return event.conclusion == "success"


def _keep(state: ReadinessState, event: CIObserved) -> ReadinessState:
    del event
    return state


def _ask_rerun(state: ReadinessState, event: CIObserved) -> RerunRequested:
    return RerunRequested("rerun:x", state.head, state.lineage, "build", event.evidence)


@activity(converter=DomainConverter())
def _rerun(request: RerunRequested) -> RerunAccepted:
    raise NotImplementedError("fixture Activity; construction must never execute it")


@activity(converter=DomainConverter())
def _repair(request: RepairRequested) -> RepairLanded:
    raise NotImplementedError("fixture Activity; construction must never execute it")


def _table():
    return on(await_event("ci", CIObserved)).match(
        "route",
        cases=(
            case("rerun", when=_failing, fold=_keep).emit(_ask_rerun),
            case("rest", when=otherwise, fold=_keep).drop(),
        ),
    )


def _flow():
    return machine(
        "mini",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", _admit_head),
            _table().choose({RerunRequested: effect("rerun", _rerun)}),
        ),
    )


def test_case_table_values_are_immutable_and_construction_performs_no_motion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    flow = _flow()

    # The fixture Activities raise if executed, so equal repeated construction
    # is also evidence that authoring runs no Activity, Engine, or History.
    assert flow == _flow()
    assert list(tmp_path.iterdir()) == []
    table = next(step for step in flow.handlers[1].steps if isinstance(step, Match))
    with pytest.raises(dataclasses.FrozenInstanceError):
        table.cases[0].id = "renamed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        table.cases = ()


def test_evaluate_match_is_ordered_first_match_wins():
    """Two overlapping predicates are benign: the earlier rung claims the event."""
    table = next(
        step
        for step in on(await_event("ci", CIObserved))
        .match(
            "route",
            cases=(
                case("first", when=_failing, fold=_keep).emit(_ask_rerun),
                case("second", when=_failing, fold=_keep).drop(),
                case("rest", when=otherwise, fold=_keep).drop(),
            ),
        )
        .steps
        if isinstance(step, Match)
    )
    state = _admit_head(HeadObserved("h1", "new", 1, "L1"))

    fired, _next_state, outcome = evaluate_match(table, state, CIObserved("h1", Evidence(10, 1), "failure", "build"))
    assert fired == "first"
    assert isinstance(outcome, RerunRequested)

    fired, _next_state, outcome = evaluate_match(table, state, CIObserved("h1", Evidence(10, 1), "success"))
    assert (fired, outcome) == ("rest", None)


def test_a_truthy_non_bool_predicate_answer_is_refused_at_evaluation():
    """The -> bool annotation is construction-checked; the VALUE is enforced too.

    A classifier drifting to a truthy non-bool (e.g. returning a category
    string) must refuse loud instead of silently selecting its rung.
    """

    def drifted(state: ReadinessState, event: CIObserved) -> bool:
        return "failure"  # type: ignore[return-value] - the deliberate mistake under test

    table = next(
        step
        for step in on(await_event("ci", CIObserved))
        .match(
            "route",
            cases=(
                case("drifted", when=drifted, fold=_keep).drop(),
                case("rest", when=otherwise, fold=_keep).drop(),
            ),
        )
        .steps
        if isinstance(step, Match)
    )
    state = _admit_head(HeadObserved("h1", "new", 1, "L1"))

    with pytest.raises(ValueError, match=r"case \[drifted\] predicate must return bool, got str"):
        evaluate_match(table, state, CIObserved("h1", Evidence(10, 1), "success"))


def test_duplicate_case_ids_name_both_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).match(
            "route",
            cases=(
                case("dup", when=_failing, fold=_keep).drop(),
                case("dup", when=_clean, fold=_keep).drop(),
                case("rest", when=otherwise, fold=_keep).drop(),
            ),
        )

    message = str(caught.value)
    assert "duplicate case id [dup]" in message
    assert message.count("test_table_algebra.py") == 2
    assert list(tmp_path.iterdir()) == []  # refused before any History file exists


def test_a_case_after_otherwise_is_refused_as_unreachable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).match(
            "route",
            cases=(
                case("rest", when=otherwise, fold=_keep).drop(),
                case("dead", when=_failing, fold=_keep).drop(),
            ),
        )

    message = str(caught.value)
    assert "[route.dead] is unreachable" in message
    assert "[route.rest] already matches every observation" in message
    assert message.count("test_table_algebra.py") == 2
    assert list(tmp_path.iterdir()) == []


def test_a_table_without_a_total_case_is_refused():
    with pytest.raises(CompositionError, match=r"\[route\] is not total"):
        on(await_event("ci", CIObserved)).match("route", cases=(case("only", when=_failing, fold=_keep).drop(),))


def test_two_total_cases_are_refused_by_id_and_location():
    with pytest.raises(CompositionError) as caught:
        on(await_event("ci", CIObserved)).match(
            "route",
            cases=(
                case("a", when=otherwise, fold=_keep).drop(),
                case("b", when=otherwise, fold=_keep).drop(),
            ),
        )

    message = str(caught.value)
    assert "declares 2 otherwise cases" in message
    assert "[a]" in message and "[b]" in message


def test_an_emitted_color_with_no_routing_target_is_refused_at_both_locations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CompositionError) as caught:
        _table().choose({})

    message = str(caught.value)
    assert "[route.rerun] emits RerunRequested" in message
    assert "routes no target for it" in message
    assert message.count("test_table_algebra.py") == 2  # the case and the choose
    assert list(tmp_path.iterdir()) == []


def test_a_routing_target_accepting_a_different_type_is_refused_at_both_locations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CompositionError) as caught:
        _table().choose({RerunRequested: effect("repair", _repair)})

    message = str(caught.value)
    assert "[route.rerun] emits RerunRequested" in message
    assert "[repair] accepts RepairRequested" in message
    assert message.count("test_table_algebra.py") == 2
    assert list(tmp_path.iterdir()) == []


def test_a_routed_color_no_case_emits_is_refused():
    with pytest.raises(CompositionError) as caught:
        _table().choose({RerunRequested: effect("rerun", _rerun), HumanNeeded: terminal("human_needed")})

    message = str(caught.value)
    assert "routes HumanNeeded" in message
    assert "[human_needed]" in message
    assert "no case in [route] emits it" in message


def test_when_and_fold_must_agree_on_state_and_event_types():
    def head_predicate(state: ReadinessState, event: HeadObserved) -> bool:
        del state, event
        return True

    with pytest.raises(CompositionError) as caught:
        case("mixed", when=head_predicate, fold=_keep)

    message = str(caught.value)
    assert "classifies (ReadinessState, HeadObserved)" in message
    assert "folds (ReadinessState, CIObserved)" in message


def test_the_trigger_event_type_must_match_the_table():
    with pytest.raises(CompositionError) as caught:
        on(await_event("head", HeadObserved)).match("route", cases=(case("rest", when=otherwise, fold=_keep).drop(),))

    message = str(caught.value)
    assert "[head] delivers HeadObserved" in message
    assert "[route.rest] accepts CIObserved" in message


def test_case_ids_are_match_qualified_but_match_ids_share_the_authored_namespace():
    """``case("rerun")`` and ``effect("rerun")`` coexist; two ``match("route")`` do not."""
    flow = _flow()
    assert flow.name == "mini"  # case [route.rerun] and effect [rerun] compiled together

    second = on(await_event("echo", CIObserved)).match(
        "route", cases=(case("rest", when=otherwise, fold=_keep).drop(),)
    )
    with pytest.raises(CompositionError, match=r"duplicate authored id \[route\]"):
        machine(
            "mini",
            lifecycle=lifecycle("branch"),
            handlers=(_table().choose({RerunRequested: effect("rerun", _rerun)}), second),
        )
