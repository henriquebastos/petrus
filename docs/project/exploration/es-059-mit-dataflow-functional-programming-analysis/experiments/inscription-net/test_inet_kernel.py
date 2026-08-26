"""What the kernel refuses, and when.

Every refusal here happens while the authored value is being built — before any
lowering, before any Engine, before any History file exists. The two that matter
most are the structural-cover checks: they are what turns experiment B's
*authoring obligation* (prove your guards are exclusive and exhaustive, or ship a
silent wrong outcome) into a compiler property.
"""

from dataclasses import dataclass

import pytest

from petrus.motus.activity import activity

from inet_kernel import (
    CompositionError,
    await_,
    branch,
    choice,
    effect,
    flow,
    fork,
    join,
    latch,
    lifecycle,
    otherwise,
)
from inet_lowering import EVALUATIONS
from inet_tokens import (
    CONVERTER,
    CIObserved,
    EvidenceWatermark,
    HeadFact,
    HeadObserved,
    PublicationClaim,
    RerunRung,
)

PORTS: dict[type, str] = {
    CIObserved: "events.ci",
    HeadFact: "readiness.head",
    EvidenceWatermark: "readiness.watermark",
}


def _head():
    return await_("head", HeadObserved, seeds=fork("open", HeadObserved.as_head_fact, HeadObserved.unseen_watermark))


def _flow(*branches, latches=(), ports=None):
    ci = await_("ci", CIObserved)
    return flow(
        "toy",
        lifecycle=lifecycle("branch"),
        ports=PORTS if ports is None else ports,
        latches=latches,
        joins=(join(ci, reads=(HeadFact,), folds=(EvidenceWatermark,)),),
        nodes=(_head(), ci >> choice("decide", *branches)),
    )


def test_a_flow_builds_with_no_motion_and_no_pure_evaluation():
    """Constructing the authored value calls no domain function and writes nothing."""
    EVALUATIONS.clear()
    authored = _flow(branch("clean", when=CIObserved.is_clean), otherwise("rest"))

    assert EVALUATIONS == {}
    assert authored.name == "toy"
    assert [step.id for step in authored.choices[0].branches] == ["clean", "rest"]


def test_a_predicate_that_does_not_return_bool_is_refused_at_its_source():
    def label(self: CIObserved) -> str:  # noqa: ARG001 - the point is the return type
        return "clean"

    with pytest.raises(CompositionError) as failure:
        branch("clean", when=label)

    assert "must return bool" in str(failure.value)
    assert "test_inet_kernel.py:" in str(failure.value)


def test_an_unannotated_parameter_is_refused_because_arc_matching_is_nominal():
    def broken(self) -> bool:  # noqa: ANN001 - deliberately unannotated
        return True

    with pytest.raises(CompositionError) as failure:
        branch("broken", when=broken)

    assert "unbound method must annotate self" in str(failure.value)


def test_a_predicate_reading_a_latch_color_is_refused():
    """A latch is structure. A generated NOT term must be evaluable in every branch's binding."""
    rung = latch("ladder.rerun", RerunRung)

    def reads_the_latch(self: CIObserved, rung: RerunRung) -> bool:  # noqa: ARG001
        return True

    with pytest.raises(CompositionError) as failure:
        _flow(
            branch("odd", when=reads_the_latch, takes=(rung,)),
            branch("even", when=reads_the_latch, without=(rung,)),
            otherwise("rest"),
            latches=(rung,),
        )

    assert "a latch is structure, not a predicate term" in str(failure.value)


def test_duplicate_branch_ids_name_both_authoring_sites():
    first = branch("same", when=CIObserved.is_clean)
    second = branch("same", when=CIObserved.is_classified_failure)

    with pytest.raises(CompositionError) as failure:
        choice("decide", first, second, otherwise("rest"))

    message = str(failure.value)
    assert "duplicate branch id [same]" in message
    assert str(first.source) in message and str(second.source) in message
    assert first.source != second.source


def test_a_choice_without_a_trailing_otherwise_is_refused():
    with pytest.raises(CompositionError) as failure:
        choice(
            "decide", branch("clean", when=CIObserved.is_clean), branch("fail", when=CIObserved.is_classified_failure)
        )

    assert "exactly one otherwise(...) branch, last" in str(failure.value)


def test_an_otherwise_carrying_a_structural_precondition_is_refused():
    with pytest.raises(TypeError):
        otherwise("rest", takes=(latch("ladder.rerun", RerunRung),))  # type: ignore[call-arg]


def test_an_incomplete_structural_cover_is_refused_before_lowering():
    """The contrast with experiment B.

    Two branches share one predicate and are separated only by a latch. B's
    equivalent — a non-exhaustive rung set — compiled, validated, ran, and
    silently stranded the observation. Here the gap is named at authoring time,
    with the exact latch state nothing answers.
    """
    rung = latch("ladder.rerun", RerunRung)

    with pytest.raises(CompositionError) as failure:
        choice(
            "decide",
            branch("spend", when=CIObserved.is_classified_failure, takes=(rung,)),
            otherwise("rest"),
        )

    message = str(failure.value)
    assert "ladder.rerun=absent" in message
    assert "would strand its observation" in message


def test_overlapping_structural_patterns_in_one_predicate_group_are_refused():
    """Two branches of one predicate group that can both be enabled are a conflict, refused."""
    rung = latch("ladder.rerun", RerunRung)

    with pytest.raises(CompositionError) as failure:
        choice(
            "decide",
            branch("first", when=CIObserved.is_classified_failure, takes=(rung,)),
            branch("second", when=CIObserved.is_classified_failure, takes=(rung,)),
            branch("third", when=CIObserved.is_classified_failure, without=(rung,)),
            otherwise("rest"),
        )

    assert "their latch patterns overlap" in str(failure.value)


def test_a_complete_structural_cover_is_admitted():
    claim = latch("publication.admitted", PublicationClaim)
    admitted = choice(
        "decide",
        branch("open", when=CIObserved.is_clean, without=(claim,), fills=(claim,)),
        branch("closed", when=CIObserved.is_clean, takes=(claim,), fills=(claim,)),
        otherwise("rest"),
    )

    assert [step.id for step in admitted.branches] == ["open", "closed", "rest"]
    # Structurally exclusive branches never negate each other's predicate.
    assert admitted.chain(1) == ()


def test_a_fold_that_is_not_a_folded_port_of_the_join_is_refused():
    def wrong(self: CIObserved) -> HeadFact:
        return HeadFact(self.head, 1, "L1")

    with pytest.raises(CompositionError) as failure:
        _flow(branch("clean", when=CIObserved.is_clean, folds=(wrong,)), otherwise("rest"))

    assert "is not a folded port of the join" in str(failure.value)


def test_an_emission_the_ports_table_does_not_name_is_refused():
    @dataclass(frozen=True)
    class Unlisted:
        head: str

    def emit(self: CIObserved) -> Unlisted:
        return Unlisted(self.head)

    with pytest.raises(CompositionError) as failure:
        _flow(branch("clean", when=CIObserved.is_clean, emits=(emit,)), otherwise("rest"))

    assert "the flow's ports table does not name" in str(failure.value)


def test_an_activity_request_without_a_stable_operation_field_is_refused():
    @dataclass(frozen=True)
    class Unstable:
        head: str

    @dataclass(frozen=True)
    class Answered:
        head: str

    @activity(converter=CONVERTER, name="unstable")
    def run(request: Unstable) -> Answered:  # pragma: no cover - never executed
        raise NotImplementedError

    def request(self: CIObserved) -> Unstable:
        return Unstable(self.head)

    with pytest.raises(CompositionError) as failure:
        effect("unstable", run, request=request)

    assert "has no stable 'operation' field" in str(failure.value)


def test_two_distinct_classes_sharing_one_nominal_name_are_refused():
    @dataclass(frozen=True)
    class HeadFact:  # shadows the real token type on purpose
        head: str

    with pytest.raises(CompositionError) as failure:
        _flow(
            branch("clean", when=CIObserved.is_clean),
            otherwise("rest"),
            ports={**PORTS, HeadFact: "shadow.head"},
        )

    assert "share the nominal name 'HeadFact'" in str(failure.value)


def test_a_latch_color_must_be_a_thin_token():
    with pytest.raises(CompositionError) as failure:
        latch("ladder.rerun", CIObserved)

    assert "field-free thin token type" in str(failure.value)


def test_a_port_the_flow_names_but_nothing_produces_is_refused_at_lowering():
    from inet_lowering import compile_flow
    from inet_tokens import Published

    authored = _flow(
        branch("clean", when=CIObserved.is_clean),
        otherwise("rest"),
        ports={**PORTS, Published: "terminal.published"},
    )

    with pytest.raises(CompositionError) as failure:
        compile_flow(authored)

    assert "nothing produces it" in str(failure.value)


def test_a_seed_projection_must_read_only_the_delivered_event():
    def wrong(self: CIObserved) -> HeadFact:
        return HeadFact(self.head, 1, "L1")

    with pytest.raises(CompositionError) as failure:
        await_("head", HeadObserved, seeds=fork("open", wrong))

    assert "must read only HeadObserved" in str(failure.value)
