"""
Behavioral tests for the CEL adapter, standalone of enabledness and runtime.

``compile_filter`` owns two contract edges: a syntactically invalid expression
is a declared mismatch that fails at compile and never evaluates, and a token
whose data has no fields to expose (not a mapping) raises at evaluation — the
raise is the contract; enabledness owns the not-admitted-plus-diagnostic
reading of it. ``compile_completion`` owns the same compile-time edge plus one
more declared mismatch — a free variable naming no place — and evaluates each
place as a list of ``{color, data}`` token maps (Navigator ruling); evaluation
errors on a concrete marking propagate for the runtime to read as not holding.
``compile_guard`` shares both declared-mismatch edges scoped to the supplied
places — the declaring transition's consume/read inputs — and evaluates each
place as the binding's selected tokens from that place, same token-map shape
(Navigator ruling); evaluation errors on a concrete binding propagate for
enabledness to read as not satisfied.
"""

from __future__ import annotations

# Pip imports
import celpy
import pytest

# Internal imports
from petrus.impetus.binding.cel import compile_completion, compile_filter, compile_guard, free_variables
from petrus.impetus.petrinet import Binding
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.petrinet import Cel, NetPath


class TestCompileFilter:
    def test_a_compiled_filter_evaluates_bare_data_fields(self):
        implementation = compile_filter(Cel("amount >= 100"))
        assert implementation(Token("Payment", {"amount": 150})) is True
        assert implementation(Token("Payment", {"amount": 40})) is False

    def test_an_invalid_expression_fails_at_compile_and_never_evaluates(self):
        with pytest.raises(ValueError, match="invalid CEL"):
            compile_filter(Cel("amount >="))

    def test_non_mapping_data_raises_for_enabledness_to_read_as_not_admitted(self):
        # A black token carries no data fields; the adapter raises rather than
        # guessing, and enabledness reads the raise as not admitted.
        implementation = compile_filter(Cel("amount >= 100"))
        with pytest.raises(TypeError, match="not a mapping"):
            implementation(Token.black())


class TestCompileCompletion:
    PLACES = (NetPath("done"), NetPath("pending"))

    def test_a_compiled_completion_evaluates_places_as_token_struct_lists(self):
        implementation = compile_completion(
            Cel('done.exists(t, t.data.state == "ok") && size(pending) == 0'), self.PLACES
        )
        assert implementation(Marking({NetPath("done"): (Token("Result", {"state": "ok"}),)})) is True
        assert implementation(Marking({NetPath("done"): (Token("Result", {"state": "failed"}),)})) is False

    def test_every_declared_place_is_bound_even_when_the_marking_is_sparse(self):
        implementation = compile_completion(Cel("size(done) == 0 && size(pending) == 0"), self.PLACES)
        assert implementation(Marking()) is True

    def test_an_invalid_expression_fails_at_compile_and_never_evaluates(self):
        with pytest.raises(ValueError, match="invalid CEL"):
            compile_completion(Cel("size(done) =="), self.PLACES)

    def test_an_unknown_place_reference_fails_at_compile(self):
        with pytest.raises(ValueError, match="doen"):
            compile_completion(Cel("size(doen) > 0"), self.PLACES)

    def test_macro_bound_variables_are_not_free_place_references(self):
        # `t` is bound by the exists macro, `size` sits in call position:
        # neither is a place reference; `done` is the only free variable.
        compile_completion(Cel("done.exists(t, t.color == null) && size(done) >= 1"), self.PLACES)


class TestCompileGuard:
    PLACES = (NetPath("pending"), NetPath("config"))

    def binding(self, amount: int, limit: int) -> Binding:
        return Binding(
            NetPath("approve"),
            consumed=((NetPath("pending"), (Token("Payment", {"amount": amount}),)),),
            read=((NetPath("config"), (Token("Config", {"limit": limit}),)),),
        )

    def test_place_variables_bind_the_bindings_selected_tokens(self):
        # Cross-token correlation reads by place name: consumed and read
        # selections alike appear under the place they were selected from.
        implementation = compile_guard(
            Cel("pending[0].data.amount <= config[0].data.limit"), NetPath("approve"), self.PLACES
        )
        assert implementation(self.binding(amount=150, limit=200)) is True
        assert implementation(self.binding(amount=150, limit=100)) is False

    def test_a_black_token_reads_as_null_color_and_data(self):
        implementation = compile_guard(
            Cel("pending[0].color == null && pending[0].data == null"), NetPath("approve"), self.PLACES
        )
        binding = Binding(NetPath("approve"), consumed=((NetPath("pending"), (Token.black(),)),))
        assert implementation(binding) is True

    def test_a_weighted_selection_binds_as_a_list(self):
        implementation = compile_guard(Cel("pending.all(t, t.data.amount < 500)"), NetPath("approve"), self.PLACES)
        tokens = (Token("Payment", {"amount": 150}), Token("Payment", {"amount": 40}))
        binding = Binding(NetPath("approve"), consumed=((NetPath("pending"), tokens),))
        assert implementation(binding) is True

    def test_consumed_selections_precede_read_selections_from_the_same_place(self):
        # One place feeding the transition through a consume arc and a read arc
        # concatenates under one variable: consumed first, read after -- the
        # same ordering contract as Binding.peeked.
        implementation = compile_guard(
            Cel('pending[0].data.kind == "consumed" && pending[1].data.kind == "read"'), NetPath("approve"), self.PLACES
        )
        binding = Binding(
            NetPath("approve"),
            consumed=((NetPath("pending"), (Token("X", {"kind": "consumed"}),)),),
            read=((NetPath("pending"), (Token("X", {"kind": "read"}),)),),
        )
        assert implementation(binding) is True

    def test_an_invalid_expression_fails_at_compile_and_never_evaluates(self):
        with pytest.raises(ValueError, match="invalid CEL"):
            compile_guard(Cel("pending[0].data.amount >="), NetPath("approve"), self.PLACES)

    def test_a_reference_outside_the_supplied_places_fails_at_compile(self):
        # The rejection names the declaring transition, the in-scope places,
        # and the stray name — self-diagnosing, and honest that an unknown
        # name may be a typo rather than a place.
        with pytest.raises(ValueError, match=r"on transition approve .*\['config', 'pending'\]: \['elsewhere'\]"):
            compile_guard(Cel("elsewhere[0].data.amount >= 100"), NetPath("approve"), self.PLACES)

    def test_macro_bound_variables_are_not_place_references(self):
        # `t` is bound by the all macro; `pending` is the only free variable.
        compile_guard(Cel("pending.all(t, t.data.amount < 500)"), NetPath("approve"), self.PLACES)

    def test_evaluation_errors_on_a_concrete_binding_propagate(self):
        # A black token has null data; reading a field of it raises. The raise
        # is the contract; enabledness owns the not-satisfied-plus-diagnostic
        # reading of it.
        implementation = compile_guard(Cel("pending[0].data.amount >= 100"), NetPath("approve"), self.PLACES)
        binding = Binding(NetPath("approve"), consumed=((NetPath("pending"), (Token.black(),)),))
        with pytest.raises(celpy.CELEvalError):
            implementation(binding)


class TestFreeVariables:
    """The free-variable walk behind the unknown-place check, tested standalone."""

    def free(self, expression: str) -> set[str]:
        return free_variables(celpy.Environment().compile(expression))

    def test_variable_position_idents_are_free_call_position_names_are_not(self):
        assert self.free("size(done) > 0 && pending[0].color == null") == {"done", "pending"}

    def test_macro_bound_variables_are_subtracted_across_nesting(self):
        assert self.free("a.exists(t, b.exists(u, u.x == t.y)) && size(c) > 0") == {"a", "b", "c"}

    def test_a_macro_variable_shadowing_a_place_name_is_permissively_skipped(self):
        # The subtraction is global, not scope-precise: binding `done` in the
        # macro hides the genuinely free `size(done)` reference too. The miss
        # is deliberately in the permissive direction -- a valid net is never
        # falsely rejected; the unresolved variable surfaces at evaluation as
        # not-holding plus a diagnostic (Navigator ruling).
        assert self.free("pending.exists(done, done.color == null) && size(done) == 0") == {"pending"}
