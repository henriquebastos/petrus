"""Production Petrus-style Python net authoring behavior."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import petrus.impetus.dsl as impetus_dsl
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import (
    ANONYMOUS,
    Arc,
    ArcMode,
    Binding,
    Cel,
    Delay,
    Marking,
    NetPath,
    Place,
    Token,
    Transition,
)
from petrus.impetus.dsl import (
    ArcSpec,
    BuiltNet,
    ConnectionSpec,
    NetBuilder,
    NetSpec,
    NodeSpec,
    PlaceSpec,
    ScopeSpec,
    TransitionSpec,
    arc,
    direct,
    petri_guard,
    petri_handler,
    typed_guard,
)


@dataclass(frozen=True)
class Order:
    amount: int


@dataclass(frozen=True)
class Config:
    limit: int


@dataclass(frozen=True)
class Receipt:
    total: int


def test_path_proxies_return_stable_authored_spec_types():
    net = NetSpec("orders")

    assert isinstance(net.p.pending, PlaceSpec)
    assert isinstance(net.t.process, TransitionSpec)
    assert isinstance(net.p.pending, NodeSpec)
    assert net.p.pending is net.p.pending
    assert net.s.review.p.pending is net.s.review.p.pending
    assert abs(net.s.review.p.pending) == NetPath("review.pending")
    assert not hasattr(net.s.review.p.pending, "path")


def test_net_spec_name_is_optional_but_an_empty_name_is_rejected():
    unnamed = NetSpec()
    unnamed.p.pending >> unnamed.t.process

    assert unnamed.name is None
    assert unnamed.build().net.name is None
    with pytest.raises(ValueError, match="non-empty string or None"):
        NetSpec("")


def test_apply_named_child_is_an_ordinary_scope_that_can_receive_a_stamp():
    flat = NetSpec("flat")
    assert isinstance(flat.s.apply, ScopeSpec)
    flat.s.apply.p.pending >> flat.s.apply.t.process
    assert NetPath("apply.process") in flat.build().net.transitions

    child = NetSpec("child")
    child.p.pending >> child.t.process
    composed = NetSpec("composed")
    composed.s.apply.stamp(child)
    assert NetPath("apply.process") in composed.build().net.transitions


@pytest.mark.parametrize("segment", ["p", "t", "s", "stamp"])
def test_item_navigation_authors_python_reserved_scope_segments(segment):
    net = NetSpec("reserved-scopes")
    scope = net.s[segment]
    scope.p.pending >> scope.t.process

    built = net.build()

    assert NetPath(f"{segment}.pending") in built.net.places
    assert NetPath(f"{segment}.process") in built.net.transitions


@pytest.mark.parametrize("segment", ["", "nested.scope"])
def test_item_navigation_requires_exactly_one_non_empty_scope_segment(segment):
    with pytest.raises(ValueError, match="one non-empty path segment"):
        NetSpec().s[segment]


def test_item_navigation_rejects_non_string_scope_segments():
    with pytest.raises(TypeError, match="scope segment must be a string"):
        NetSpec().s[1]


def test_only_right_shift_builds_default_and_explicit_connections():
    net = NetSpec("orders")
    pending = net.place(net.p.pending, color=Order)
    receipt = net.place(net.p.receipt, color=Receipt)
    process = net.transition(net.t.process, handler="process")

    pending >> process >> receipt
    pending >> arc.read(weight=2, color=Order, filter="current") >> process
    built = net.build()

    assert built.net.places == {
        abs(pending): Place(abs(pending), "Order"),
        abs(receipt): Place(abs(receipt), "Receipt"),
    }
    assert built.net.transitions == {abs(process): Transition(abs(process), handler="process")}
    assert built.net.arcs == (
        Arc(abs(pending), abs(process), color="Order"),
        Arc(abs(process), abs(receipt), color="Receipt"),
        Arc(abs(pending), abs(process), ArcMode.READ, 2, "Order", "current"),
    )


def test_arc_and_connection_specs_preserve_authored_order_and_multiplicity():
    net = NetSpec("multiplicity")
    inscription = arc(color=Order)

    (net.p.left, net.p.right) >> inscription >> (net.t.first, net.t.second)
    net.p.left >> inscription >> net.t.first

    assert isinstance(inscription, ArcSpec)
    assert all(isinstance(connection, ConnectionSpec) for connection in net.connections)
    assert [(str(abs(item.source)), str(abs(item.target))) for item in net.connections] == [
        ("left", "first"),
        ("left", "second"),
        ("right", "first"),
        ("right", "second"),
        ("left", "first"),
    ]


def test_arc_factory_names_modes_and_does_not_accept_mode_as_a_parameter():
    assert arc().mode is ArcMode.CONSUME
    assert arc.read().mode is ArcMode.READ
    assert arc.inhibit().mode is ArcMode.INHIBIT

    with pytest.raises(TypeError):
        arc(ArcMode.READ)
    with pytest.raises(TypeError):
        arc(mode=ArcMode.READ)


def test_build_snapshots_are_independent_and_implementation_maps_are_immutable():
    net = NetSpec("snapshots")
    net.p.pending >> net.t.first
    first = net.build()
    net.t.first >> net.p.done
    second = net.build()

    assert isinstance(first, BuiltNet)
    assert len(first.net.arcs) == 1
    assert len(second.net.arcs) == 2
    with pytest.raises(TypeError):
        first.handlers[object()] = lambda: None


def test_cross_specification_failure_is_atomic():
    left = NetSpec("left")
    right = NetSpec("right")

    with pytest.raises(ValueError, match="different net specifications"):
        (left.p.one, right.p.two) >> left.t.join

    assert left.connections == ()
    assert right.connections == ()


def test_identical_configuration_is_idempotent_and_override_is_explicit():
    net = NetSpec("configuration")
    transition = net.t.process(handler="first", guards=("ready",), timers=(Delay(3),))
    net.p.pending(Order) >> transition

    assert transition(handler="first", guards=("ready",), timers=(Delay(3),)) is transition
    with pytest.raises(ValueError, match=r"transition\.override\(\.\.\.\)"):
        transition(handler="second")

    assert transition.override(handler="second") is transition
    declaration = net.build().net.transitions[abs(transition)]
    assert declaration.handler == "second"
    assert declaration.guards == ("ready",)
    assert declaration.timers == (Delay(3),)


def test_conflicting_place_color_fails_without_mutation():
    net = NetSpec("places")
    place = net.p.pending(Order)

    with pytest.raises(ValueError, match="already configured with color 'Order'"):
        place(Receipt)

    assert place.color == "Order"


def test_place_override_changes_or_clears_color_and_requires_a_base():
    net = NetSpec("place-overrides")
    place = net.p.pending(Order)
    before = net.build()

    assert place.override(color=Receipt) is place
    changed = net.build()
    place.override(color=None)
    cleared = net.build()

    assert before.net.places[abs(place)].color == "Order"
    assert changed.net.places[abs(place)].color == "Receipt"
    assert cleared.net.places[abs(place)].color is None
    with pytest.raises(ValueError, match="no explicit or inherited configuration"):
        net.p.undeclared.override(color=Order)


def test_transition_override_preserves_omitted_fields_and_explicitly_clears_values():
    net = NetSpec("transition-overrides")
    transition = net.t.process(handler="process", guards=("ready",), timers=(Delay(3),))
    net.p.pending(Order) >> transition

    transition.override(handler=None)
    declaration = net.build().net.transitions[abs(transition)]
    assert declaration.handler is None
    assert declaration.guards == ("ready",)
    assert declaration.timers == (Delay(3),)

    transition.override(guards=(), timers=())
    declaration = net.build().net.transitions[abs(transition)]
    assert declaration.handler is None
    assert declaration.guards == ()
    assert declaration.timers == ()


def test_transition_override_requires_a_base_and_at_least_one_field():
    net = NetSpec("invalid-overrides")

    with pytest.raises(ValueError, match="no explicit or inherited configuration"):
        net.t.undeclared.override(handler="process")

    transition = net.t.process(handler="process")
    with pytest.raises(TypeError, match="requires at least one"):
        transition.override()


def test_transition_override_is_atomic_when_a_supplied_field_is_invalid():
    net = NetSpec("atomic-overrides")
    transition = net.t.process(handler="process", guards=("ready",))
    net.p.pending(Order) >> transition

    with pytest.raises(TypeError, match="node specification cannot be used as a guard"):
        transition.override(handler="changed", guards=net.t.other)

    declaration = net.build().net.transitions[abs(transition)]
    assert declaration.handler == "process"
    assert declaration.guards == ("ready",)


def test_callable_specs_configure_stable_identity_reused_by_bare_references():
    net = NetSpec("callable-specs")
    transition = net.t.publish
    published = net.p.published(Receipt)
    audited = net.p.audited(Receipt)

    assert transition(handler="publish") is transition
    assert net.t.publish is transition
    assert net.p.published is published

    transition >> published
    transition >> audited
    built = net.build()

    assert built.net.transitions == {abs(transition): Transition(abs(transition), handler="publish")}
    assert built.net.arcs == (
        Arc(abs(transition), abs(published), color="Receipt"),
        Arc(abs(transition), abs(audited), color="Receipt"),
    )


def test_configuration_after_topology_applies_at_build_without_mutating_prior_snapshot():
    net = NetSpec("late-configuration")
    transition = net.t.publish
    transition >> net.p.published(Receipt)
    before = net.build()

    transition(handler="publish")
    transition >> net.p.audit(Receipt)
    after = net.build()

    assert before.net.transitions[abs(transition)].handler is None
    assert after.net.transitions[abs(transition)].handler == "publish"
    assert len(before.net.arcs) == 1
    assert len(after.net.arcs) == 2


def test_callable_node_specs_are_rejected_as_handler_and_guard_values():
    net = NetSpec("node-behavior")

    with pytest.raises(TypeError, match="node specification cannot be used as a handler"):
        net.t.publish(handler=net.t.other)
    with pytest.raises(TypeError, match="node specification cannot be used as a guard"):
        net.t.publish(guards=net.t.other)


def test_canonical_net_remains_the_semantic_validation_boundary():
    net = NetSpec("invalid")
    net.p.left >> net.p.right

    with pytest.raises(ValueError, match="connect a place and a transition"):
        net.build()


def test_python_comparison_operator_is_not_supported():
    net = NetSpec("operators")

    with pytest.raises(TypeError):
        net.p.left > net.t.right


def test_color_adapter_rejects_non_type_objects():
    net = NetSpec("colors")

    with pytest.raises(TypeError, match="nominal string, Python type, or None"):
        net.place(net.p.pending, color=Order(3))


def test_direct_and_callable_guard_lower_after_place_colors_and_execute_by_declaration_uri():
    @direct
    def process(order: Order) -> Receipt:
        """Turn an order into its receipt."""
        return Receipt(order.amount + 1)

    def positive(order: Order) -> bool:
        """Accept positive orders."""
        return order.amount > 0

    net = NetSpec("typed")
    pending = net.place(net.p.pending, color=Order)
    receipt = net.place(net.p.receipt, color=Receipt)
    transition = net.transition(net.t.process, handler=process, guards=positive)
    pending >> transition >> receipt

    built = net.build()
    instance = Instance(
        built.net,
        Marking({abs(pending): (Token("Order", {"amount": 4}),)}),
        handlers=built.handlers,
        guards=built.guards,
    )
    instance.run()

    assert built.net.transitions[abs(transition)].handler == ANONYMOUS
    assert built.net.transitions[abs(transition)].guards == (ANONYMOUS,)
    assert built.net.transitions[abs(transition)].handler.display_name == "process"
    assert built.net.transitions[abs(transition)].guards[0].display_name == "positive"
    assert process.implementation.__name__ == "process"
    assert process.implementation.__doc__ == "Turn an order into its receipt."
    assert set(built.handlers) == {built.net.handler_uri(abs(transition))}
    assert set(built.guards) == set(built.net.guard_uris(abs(transition)))
    assert instance.marking == Marking({abs(receipt): (Token("Receipt", {"total": 5}),)})


def test_typed_guard_uses_a_custom_converter_for_every_selected_input_and_stays_anonymous():
    decoded = []

    class RecordingConverter:
        def decode(self, value, annotation):
            decoded.append((value, annotation))
            if annotation is Order:
                return Order(int(value["amount"]))
            if annotation is Config:
                return Config(int(value["limit"]))
            raise AssertionError(f"unexpected annotation {annotation!r}")

        def encode(self, value, annotation):
            raise AssertionError("guards do not encode payloads")

    @typed_guard(converter=RecordingConverter())
    def within_limit(order: Order, config: Config) -> bool:
        return order.amount <= config.limit

    net = NetSpec("custom-guard")
    pending = net.place(net.p.pending, color=Order)
    configuration = net.place(net.p.configuration, color=Config)
    transition = net.transition(net.t.review, guards=within_limit)
    pending >> transition
    configuration >> arc.read() >> transition
    built = net.build()
    binding = Binding(
        abs(transition),
        ((abs(pending), (Token("Order", {"amount": "4"}),)),),
        ((abs(configuration), (Token("Config", {"limit": "5"}),)),),
    )

    [guard] = built.guards.values()
    declaration = built.net.transitions[abs(transition)].guards[0]

    assert guard(binding) is True
    assert decoded == [
        ({"amount": "4"}, Order),
        ({"limit": "5"}, Config),
    ]
    assert declaration == ANONYMOUS
    assert declaration.display_name == "within_limit"
    assert [str(uri) for uri in built.guards] == ["transition:/review#guard:$0"]
    assert "typed_guard" in impetus_dsl.__all__


def test_typed_guard_factory_preserves_the_exact_bool_result_contract():
    def truthy(order: Order) -> bool:
        return "yes"

    specification = typed_guard(truthy)
    net = NetSpec("exact-bool")
    pending = net.place(net.p.pending, color=Order)
    transition = net.transition(net.t.review, guards=specification)
    pending >> transition
    built = net.build()
    binding = Binding(
        abs(transition),
        ((abs(pending), (Token("Order", {"amount": 4}),)),),
        (),
    )

    [guard] = built.guards.values()
    with pytest.raises(ValueError, match="must return bool, got str"):
        guard(binding)


def test_scalar_and_mixed_guard_forms_preserve_authored_order_and_absolute_positions():
    net = NetSpec("guards")
    transition = net.t.review
    inline = Cel("true")

    def positive(order: Order) -> bool:
        return order.amount > 0

    net.transition(transition, guards=("named", positive, inline, positive))
    net.place(net.p.pending, color=Order) >> transition
    built = net.build()

    assert built.net.transitions[abs(transition)].guards == ("named", ANONYMOUS, inline, ANONYMOUS)
    assert [str(uri) for uri in built.net.guard_uris(abs(transition))] == [
        "transition:/review#guard:named",
        "transition:/review#guard:$1",
        "transition:/review#guard:$2",
        "transition:/review#guard:$3",
    ]
    assert set(built.guards) == {
        built.net.guard_uris(abs(transition))[1],
        built.net.guard_uris(abs(transition))[3],
    }

    scalar = NetSpec("scalar")
    scalar.transition(scalar.t.review, guards="named")
    scalar.p.pending >> scalar.t.review
    assert scalar.build().net.transitions[NetPath("review")].guards == ("named",)


@pytest.mark.parametrize("guards", [["named"], iter(("named",))])
def test_guards_reject_mutable_iterables_and_generators(guards):
    net = NetSpec("invalid-guards")

    with pytest.raises(TypeError, match="guards must"):
        net.transition(net.t.review, guards=guards)


def test_handler_rejects_raw_callable_without_direct_or_advanced_flavor():
    net = NetSpec("invalid-handler")

    with pytest.raises(TypeError, match="handler callables require"):
        net.transition(net.t.process, handler=lambda binding, outputs: {})


def test_petri_aware_specs_use_owner_identity_not_callable_name():
    handler = lambda binding, outputs: {}  # noqa: E731 - lambda identity is the case under test
    guard = lambda binding: True  # noqa: E731 - lambda identity is the case under test
    net = NetSpec("identity")
    transition = net.transition(net.t.process, handler=petri_handler(handler), guards=petri_guard(guard))
    net.p.pending >> transition
    built = net.build()

    assert built.handlers == {built.net.handler_uri(abs(transition)): handler}
    assert built.guards == {built.net.guard_uris(abs(transition))[0]: guard}
    assert "<lambda>" not in str(next(iter(built.handlers)))
    assert "<lambda>" not in str(next(iter(built.guards)))


def test_same_callable_spec_reused_across_transitions_keeps_two_declarations():
    implementation = lambda binding: True  # noqa: E731 - one anonymous callable is deliberately reused
    specification = petri_guard(implementation)
    net = NetSpec("reuse")
    net.transition(net.t.left, guards=specification)
    net.transition(net.t.right, guards=specification)
    net.p.pending >> (net.t.left, net.t.right)
    built = net.build()

    assert len(built.guards) == 2
    assert set(built.guards.values()) == {implementation}


def test_build_snapshots_keep_the_callable_association_selected_at_build_time():
    first_handler = lambda binding, outputs: {}  # noqa: E731 - associations, not names, are under test
    second_handler = lambda binding, outputs: {}  # noqa: E731 - associations, not names, are under test
    net = NetSpec("callable-snapshots")
    transition = net.transition(net.t.process, handler=petri_handler(first_handler))
    net.p.pending >> transition
    first = net.build()

    transition.override(handler=petri_handler(second_handler))
    second = net.build()

    assert next(iter(first.handlers.values())) is first_handler
    assert next(iter(second.handlers.values())) is second_handler


def test_scope_stamp_rebases_reusable_definition_at_each_destination():
    handler = lambda binding, outputs: {}  # noqa: E731 - callable association identity is under test
    guard = lambda binding: True  # noqa: E731 - callable association identity is under test
    lens = NetSpec("review-lens")
    (
        lens.p.work(Order)
        >> lens.t.review(
            handler=petri_handler(handler),
            guards=petri_guard(guard),
        )
        >> lens.p.done
    )

    root = NetSpec("reviews")
    correctness = root.s.review.s.correctness.stamp(lens)
    risk = root.s.review.s.risk.stamp(lens)
    correctness.p.done(Receipt)
    risk.p.done(Receipt)
    correctness.t.review.override(handler="correctness")

    assert abs(lens.t.review) == NetPath("review")
    assert abs(correctness.t.review) == NetPath("review.correctness.review")
    built = NetBuilder(root).build()

    assert set(built.net.places) == {
        NetPath("review.correctness.work"),
        NetPath("review.correctness.done"),
        NetPath("review.risk.work"),
        NetPath("review.risk.done"),
    }
    assert built.net.transitions[NetPath("review.correctness.review")].handler == "correctness"
    assert built.net.transitions[NetPath("review.risk.review")].handler == ANONYMOUS
    assert set(built.handlers) == {built.net.handler_uri(NetPath("review.risk.review"))}
    assert set(built.guards) == set(built.net.guard_uris(NetPath("review.correctness.review"))) | set(
        built.net.guard_uris(NetPath("review.risk.review"))
    )


def test_flat_parent_authoring_and_stamped_child_authoring_compose_together():
    child = NetSpec("child")
    child.p.pending >> child.t.finish >> child.p.done
    root = NetSpec("root")
    review = root.s.review
    review.p.context >> review.t.publish
    stamped = review.s.correctness.stamp(child)
    stamped.p.done >> review.t.publish

    built = root.build()

    assert NetPath("review.context") in built.net.places
    assert NetPath("review.publish") in built.net.transitions
    assert NetPath("review.correctness.finish") in built.net.transitions
    assert built.net.arcs[-1] == Arc(NetPath("review.correctness.done"), NetPath("review.publish"))


def test_stamped_specification_remains_live_between_immutable_build_snapshots():
    child = NetSpec("child")
    child.p.pending >> child.t.process >> child.p.done
    root = NetSpec("root")
    root.s.worker.stamp(child)
    first = root.build()

    child.t.process >> child.p.audit
    second = root.build()

    assert NetPath("worker.audit") not in first.net.places
    assert NetPath("worker.audit") in second.net.places
    assert len(first.net.arcs) == 2
    assert len(second.net.arcs) == 3


def test_restamping_a_scope_replaces_the_base_and_clears_destination_overrides():
    first = NetSpec("first")
    first.p.pending >> first.t.process(handler="first") >> first.p.done
    second = NetSpec("second")
    second.p.ready >> second.t.process(handler="second") >> second.p.complete
    root = NetSpec("root")
    worker = root.s.worker.stamp(first)
    worker.t.process.override(handler="specialized")

    worker.stamp(second)
    built = root.build()

    assert set(built.net.places) == {NetPath("worker.ready"), NetPath("worker.complete")}
    assert built.net.transitions[NetPath("worker.process")].handler == "second"


def test_stamp_refuses_to_erase_direct_content_without_mutating_the_scope():
    child = NetSpec("child")
    child.p.pending >> child.t.process
    root = NetSpec("root")
    root.s.worker.p.local

    with pytest.raises(
        ValueError,
        match="cannot stamp child at worker: destination already owns place worker.local",
    ):
        root.s.worker.stamp(child)

    assert set(root.build().net.places) == {NetPath("worker.local")}


def test_stamp_diagnostics_identify_enclosing_stamp_and_requested_missing_node():
    child = NetSpec("child")
    child.p.pending >> child.t.process
    replacement = NetSpec()
    root = NetSpec("root")
    worker = root.s.worker.stamp(child)

    with pytest.raises(
        ValueError,
        match="cannot stamp <anonymous> at worker.nested: scope belongs to child stamped at worker",
    ):
        worker.s.nested.stamp(replacement)
    with pytest.raises(
        ValueError,
        match="stamp of child at worker has no transition missing requested as worker.missing",
    ):
        worker.t.missing.override(handler="missing")


def test_root_stamp_and_missing_connection_diagnostics_name_the_composition_location():
    child = NetSpec("child")
    child.p.pending >> child.t.process
    root = NetSpec("root")

    with pytest.raises(
        ValueError,
        match="cannot stamp child at <root>: reusable definitions require a non-root scope",
    ):
        root.s.stamp(child)

    worker = root.s.worker.stamp(child)
    worker.p.missing >> root.t.publish
    with pytest.raises(
        ValueError,
        match="net specification root at <root> connection references missing place worker.missing",
    ):
        root.build()


def test_nested_stamps_flatten_and_stamp_cycles_fail_explicitly():
    inner = NetSpec("inner")
    inner.p.pending >> inner.t.process >> inner.p.done
    outer = NetSpec("outer")
    outer.s.child.stamp(inner)
    root = NetSpec("root")
    root.s.parent.stamp(outer)

    assert NetPath("parent.child.process") in root.build().net.transitions

    first = NetSpec("first")
    second = NetSpec("second")
    first.s.second.stamp(second)
    second.s.first.stamp(first)
    with pytest.raises(
        ValueError,
        match=("stamp cycle: first at <root> -> second at second -> first at second.first"),
    ):
        first.build()


def test_copy_snapshots_a_composed_specification_without_retaining_source_links():
    child = NetSpec("child")
    child.p.pending >> child.t.process >> child.p.done
    root = NetSpec("root")
    root.s.worker.stamp(child)
    copied = root.copy()

    child.t.process >> child.p.audit

    assert NetPath("worker.audit") not in copied.build().net.places
    assert NetPath("worker.audit") in root.build().net.places


def test_stamped_specification_cannot_contribute_root_completion():
    child = NetSpec("child", completion="complete")
    child.p.pending >> child.t.process
    root = NetSpec("root")
    root.s.worker.stamp(child)

    with pytest.raises(
        ValueError,
        match="stamped net specification child at worker cannot declare root completion",
    ):
        root.build()
