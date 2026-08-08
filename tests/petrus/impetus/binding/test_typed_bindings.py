"""Production typed transformation and predicate binding contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from petrus.impetus.binding import derive_typed_guard, derive_typed_transform
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Binding, Marking, Net, NetPath, Place, Token, Transition


@dataclass(frozen=True)
class Order:
    amount: int


@dataclass(frozen=True)
class Config:
    fee: int


@dataclass(frozen=True)
class Receipt:
    total: int


PENDING, CONFIG, APPLY, RESULT = map(NetPath, ("pending", "config", "apply", "result"))


def apply_fee(order: Order, config: Config) -> Receipt:
    return Receipt(order.amount + config.fee)


def within_limit(order: Order, config: Config) -> bool:
    return order.amount <= config.fee


def transform_net(*, input_weight: int = 1, result_color: str = "Receipt") -> Net:
    return Net(
        places=[Place(PENDING, "Order"), Place(CONFIG, "Config"), Place(RESULT, result_color)],
        transitions=[Transition(APPLY, handler="apply_fee")],
        arcs=[
            Arc(CONFIG, APPLY, ArcMode.READ),
            Arc(PENDING, APPLY, weight=input_weight),
            Arc(APPLY, RESULT),
        ],
    )


def test_typed_transform_decodes_read_and_consumed_inputs_and_routes_dataclass_result():
    net = transform_net()
    handler = derive_typed_transform(net, APPLY, apply_fee)
    instance = Instance(
        net,
        Marking(
            {
                PENDING: (Token("Order", {"amount": 40}),),
                CONFIG: (Token("Config", {"fee": 2}),),
            }
        ),
        handlers={"apply_fee": handler},
    )

    instance.run()

    assert instance.marking == Marking(
        {
            CONFIG: (Token("Config", {"fee": 2}),),
            RESULT: (Token("Receipt", {"total": 42}),),
        }
    )


def test_typed_guard_decodes_the_same_effective_input_contract():
    net = transform_net()
    guard = derive_typed_guard(net, APPLY, within_limit)
    binding = Binding(
        APPLY,
        ((PENDING, (Token("Order", {"amount": 40}),)),),
        ((CONFIG, (Token("Config", {"fee": 50}),)),),
    )

    assert guard(binding) is True


def test_typed_guard_requires_an_exact_bool_at_runtime():
    def truthy(order: Order, config: Config) -> bool:
        return "yes"

    guard = derive_typed_guard(transform_net(), APPLY, truthy)
    binding = Binding(
        APPLY,
        ((PENDING, (Token("Order", {"amount": 40}),)),),
        ((CONFIG, (Token("Config", {"fee": 50}),)),),
    )

    with pytest.raises(ValueError, match="must return bool, got str"):
        guard(binding)


def test_typed_binding_reads_effective_colors_compiled_from_places():
    net = transform_net()

    assert all(arc.color is not None for arc in net.arcs)
    assert derive_typed_transform(net, APPLY, apply_fee)


def test_typed_binding_rejects_source_transitions():
    source = NetPath("source")
    net = Net(
        places=[Place(RESULT, "Receipt")],
        transitions=[Transition(source, handler="source")],
        arcs=[Arc(source, RESULT)],
    )

    with pytest.raises(ValueError, match="source transitions are not supported"):
        derive_typed_transform(net, source, apply_fee)


def test_typed_binding_rejects_weighted_inputs():
    with pytest.raises(ValueError, match="weight 2.*collection parameters are not supported"):
        derive_typed_transform(transform_net(input_weight=2), APPLY, apply_fee)


def test_typed_binding_rejects_same_color_input_ambiguity():
    other = NetPath("other")
    net = Net(
        places=[Place(PENDING, "Order"), Place(other, "Order"), Place(RESULT, "Receipt")],
        transitions=[Transition(APPLY, handler="apply_fee")],
        arcs=[Arc(PENDING, APPLY), Arc(other, APPLY), Arc(APPLY, RESULT)],
    )

    def one_order(order: Order) -> Receipt:
        return Receipt(order.amount)

    with pytest.raises(ValueError, match="requires exactly one matching input arc, found 2"):
        derive_typed_transform(net, APPLY, one_order)


def test_typed_binding_rejects_unmatched_input_arcs():
    def order_only(order: Order) -> Receipt:
        return Receipt(order.amount)

    with pytest.raises(ValueError, match="input arc config matches no parameter"):
        derive_typed_transform(transform_net(), APPLY, order_only)


def test_typed_transform_rejects_output_color_mismatch():
    with pytest.raises(ValueError, match="has color Other, expected Receipt"):
        derive_typed_transform(transform_net(result_color="Other"), APPLY, apply_fee)


@pytest.mark.parametrize(
    "function",
    [
        lambda order: Receipt(order.amount),
        lambda *orders: Receipt(orders[0].amount),
    ],
)
def test_typed_binding_rejects_missing_or_variadic_parameter_contracts(function):
    with pytest.raises(TypeError, match="requires a type|must be named"):
        derive_typed_transform(transform_net(), APPLY, function)


def test_typed_transform_rejects_non_dataclass_return_annotation():
    def mapping_result(order: Order, config: Config) -> dict:
        return {"total": order.amount + config.fee}

    with pytest.raises(ValueError, match="return annotation.*must be a concrete dataclass type"):
        derive_typed_transform(transform_net(), APPLY, mapping_result)
