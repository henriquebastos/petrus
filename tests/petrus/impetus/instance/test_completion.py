"""
Impetus-native tests for the completion condition — the done judgment of status.

A net MAY declare one completion condition: a pure boolean predicate over the
marking, inline CEL or a named pure symbol, the same expression tier as filters
and guards [net-schema.md Completion condition]. It never affects enabledness
or firing — quiescence triggers status, the condition supplies the verdict:
RUNNING while not quiescent; else COMPLETED if the condition holds, else STUCK;
with no condition declared the instance collapses to the neutral TERMINATED
[firing-semantics.md Termination; DR 2026-07-08 termination-instance-status-rule].
AWAITING awaits delivery registrations (the ingress slice).

Navigator rulings (2026-07-09): an inline CEL condition sees each place as a
bare variable bound to its FIFO queue, each token a ``{color, data}`` map (a
black token is ``{color: null, data: null}``, an empty place the empty list);
a named symbol binds through the uniform ``completions={symbol: impl}``
mapping; an unresolvable place reference is a declared mismatch caught at
construction. A condition that raises over a concrete marking reads as not
holding — STUCK, surfaced as a ``CompletionEvaluationWarning``, never silently
swallowed [DR 2026-07-08 guard-filter-evaluation-errors].
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import CompletionEvaluationWarning, Instance, Status
from petrus.impetus.petrinet import Arc, Cel, Net, NetPath, Place, Transition

A, T, B = NetPath("a"), NetPath("t"), NetPath("b")


def chain(completion: str | Cel | None) -> Net:
    """a -> t -> b, with the completion condition under test."""
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T)],
        arcs=[Arc(A, T), Arc(T, B)],
        completion=completion,
    )


class TestStatusResolution:
    """Quiescence triggers status; the declared condition supplies the verdict."""

    def test_completed_when_quiescent_and_the_condition_holds(self):
        instance = Instance(chain(Cel("size(b) == 1")), Marking({A: (Token.black(),)}))
        instance.run()
        assert instance.status is Status.COMPLETED

    def test_stuck_when_quiescent_and_the_condition_does_not_hold(self):
        # The net says this is not done, nothing can ever happen again: the
        # diagnosable defect status, distinct from the healthy end.
        instance = Instance(chain(Cel("size(b) >= 2")), Marking({A: (Token.black(),)}))
        instance.run()
        assert instance.status is Status.STUCK

    def test_terminated_stays_the_neutral_collapse_without_a_declaration(self):
        # Declaring is optional; undeclared, the engine honestly cannot tell
        # done from stuck and reports the neutral fact.
        instance = Instance(chain(None), Marking({A: (Token.black(),)}))
        instance.run()
        assert instance.status is Status.TERMINATED

    def test_running_while_enabled_even_when_the_condition_already_holds(self):
        # The condition reports, it never halts: completion true with a
        # transition still enabled is RUNNING [DR termination-instance-status-rule].
        instance = Instance(chain(Cel("size(a) == 1")), Marking({A: (Token.black(),)}))
        assert instance.status is Status.RUNNING

    def test_the_condition_never_affects_enabledness_or_firing(self):
        marking = Marking({A: (Token.black(),)})
        judged, neutral = Instance(chain(Cel("size(b) == 1")), marking), Instance(chain(None), marking)
        assert judged.candidates() == neutral.candidates()
        assert [f.records for f in judged.run()] == [f.records for f in neutral.run()]

    def test_status_is_a_pure_projection_of_the_marking(self):
        # Derived, never stored: repeated reads re-evaluate the same verdict
        # and leave marking and history untouched.
        instance = Instance(chain(Cel("size(b) == 1")), Marking({A: (Token.black(),)}))
        instance.run()
        recorded = len(instance.history)
        assert [instance.status, instance.status] == [Status.COMPLETED, Status.COMPLETED]
        assert instance.marking == Marking({B: (Token.black(),)})
        assert len(instance.history) == recorded


class TestCelEnvironment:
    """An inline condition sees each place as a list of {color, data} token maps."""

    def test_place_variables_bind_token_color_and_data(self):
        net = chain(Cel('b.exists(t, t.color == "Payment" && t.data.amount >= 100)'))
        instance = Instance(net, Marking({A: (Token("Payment", {"amount": 150}),)}))
        instance.run()
        assert instance.status is Status.COMPLETED

    def test_a_black_token_reads_as_null_color_and_data(self):
        # The black token has no color to compare: null == "X" is a healthy
        # false, not an evaluation error.
        instance = Instance(chain(Cel('b.exists(t, t.color == "Payment")')), Marking({A: (Token.black(),)}))
        instance.run()
        assert instance.status is Status.STUCK

    def test_an_empty_place_binds_to_the_empty_list(self):
        # The marking is sparse; the expression environment is not — every
        # declared place resolves, so emptiness is expressible.
        instance = Instance(chain(Cel("size(a) == 0 && size(b) == 1")), Marking({A: (Token.black(),)}))
        instance.run()
        assert instance.status is Status.COMPLETED


class TestNamedCompletion:
    """A named-symbol condition binds through the uniform completions mapping."""

    def test_named_symbol_binds_and_sees_the_marking(self):
        net = chain("allSettled")
        instance = Instance(net, Marking({A: (Token.black(),)}), completions={"allSettled": lambda m: bool(m.place(B))})
        instance.run()
        assert instance.status is Status.COMPLETED

    def test_missing_implementation_fails_at_construction(self):
        # Declared completion symbols are validated against the implementation
        # mapping before the instance can run -- never at first status read.
        with pytest.raises(ValueError, match="allSettled"):
            Instance(chain("allSettled"), Marking())


class TestCompletionValidation:
    """Declared mismatches fail at construction and never evaluate."""

    def test_invalid_cel_fails_at_construction_and_never_evaluates(self):
        with pytest.raises(ValueError, match="invalid CEL"):
            Instance(chain(Cel("size(b) ==")), Marking())

    def test_unknown_place_reference_fails_at_construction(self):
        # A typo'd place is a declared mismatch, not a permanently-stuck net
        # distinguishable only via warnings (Navigator ruling).
        with pytest.raises(ValueError, match="doen"):
            Instance(chain(Cel("size(doen) > 0")), Marking())

    def test_macro_bound_variables_are_not_place_references(self):
        Instance(chain(Cel("b.exists(t, t.color == null)")), Marking())

    def test_a_non_symbol_non_cel_completion_is_rejected_at_build(self):
        # The net accepts the two declared encodings only; anything else
        # fails as a declared mismatch, not as the CEL adapter's internals.
        with pytest.raises(ValueError, match="symbol name or an inline Cel"):
            chain(lambda marking: True)


class TestCompletionEvaluationErrors:
    """A raising condition reads as not holding: STUCK, surfaced, never swallowed."""

    def test_a_raising_condition_reads_as_stuck_with_a_diagnostic(self):
        # The ruled diagnostic payload is (expression, concrete state, error):
        # the marking is what distinguishes a broken condition from a healthy
        # not-done.
        def broken(marking: Marking) -> bool:
            raise RuntimeError("boom")

        instance = Instance(chain("allSettled"), Marking({A: (Token.black(),)}), completions={"allSettled": broken})
        instance.run()
        with pytest.warns(CompletionEvaluationWarning, match=r"allSettled.*RuntimeError.*Marking"):
            assert instance.status is Status.STUCK

    def test_unencodable_token_data_reads_as_stuck_with_a_diagnostic(self):
        # Permissive default: nothing stops a handlerless net from carrying
        # data CEL cannot read; the condition errs on the concrete marking,
        # uniformly read as not holding.
        instance = Instance(chain(Cel("size(b) == 1")), Marking({A: (Token("Job", object()),)}))
        instance.run()
        with pytest.warns(CompletionEvaluationWarning):
            assert instance.status is Status.STUCK
