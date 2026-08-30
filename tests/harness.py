"""Replay support for the Impetus-native golden trace corpus."""

from __future__ import annotations

import json
from pathlib import Path

from petrus.impetus.history import replay_marking
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.instance import Instance
from petrus.impetus.net_definition import NetDefinitionV3, compile_net_definition
from petrus.impetus.petrinet import Binding, Marking, NetPath, Token

TRACES = Path(__file__).resolve().parent.parent / "spec" / "traces"


def _token(value: dict) -> Token:
    return Token(value["color"], value["data"])


def _marking(value: list[dict]) -> Marking:
    return Marking({NetPath(entry["place"]): tuple(_token(token) for token in entry["tokens"]) for entry in value})


def _selection(value: tuple[NetPath, tuple[Token, ...]]) -> dict:
    place, tokens = value
    return {"place": str(place), "tokens": [_encoded_token(token) for token in tokens]}


def _encoded_token(value: Token) -> dict:
    return {"color": value.color, "data": value.data}


def _binding(value: Binding) -> dict:
    return {
        "transition": str(value.transition),
        "consumed": [_selection(selection) for selection in value.consumed],
        "read": [_selection(selection) for selection in value.read],
        "delivered": [_encoded_token(token) for token in value.delivered],
    }


def _outcome(value) -> dict:
    return {
        "occurrence": value.occurrence,
        "transition": str(value.transition),
        "consumed": [_encoded_token(token) for token in value.consumed],
        "produced": [{"place": str(place), "token": _encoded_token(token)} for place, token in value.produced],
    }


def _amount_gte_100(value: Binding) -> bool:
    return value.peeked[0].data["amount"] >= 100


def _amount_lt_100(value: Binding) -> bool:
    return value.peeked[0].data["amount"] < 100


def _settle(value: Binding, outputs):
    del outputs
    [payment] = value.tokens
    return {
        NetPath("approved"): (Token("ApprovalNotice", {"approved": True}),),
        NetPath("ledger"): (Token("LedgerEntry", {"amount": payment.data["amount"]}),),
    }


GUARDS = {"amount_gte_100": _amount_gte_100, "amount_lt_100": _amount_lt_100}
HANDLERS = {"settle": _settle}
BINDING_SPECS = {
    "amount_gte_100": {
        "kind": "guard",
        "semantics": "the first peeked Payment token's data.amount is greater than or equal to 100",
    },
    "amount_lt_100": {
        "kind": "guard",
        "semantics": "the first peeked Payment token's data.amount is less than 100",
    },
    "settle": {
        "kind": "handler",
        "semantics": (
            "for the consumed Payment, emit ApprovalNotice {approved: true} to approved and "
            "LedgerEntry {amount: Payment.data.amount} to ledger"
        ),
    },
}


def load_fixture(name: str) -> dict:
    return json.loads((TRACES / f"{name}.json").read_text())


def fixture_names() -> list[str]:
    manifest = json.loads((TRACES / "manifest.json").read_text())
    return [entry["name"] for entry in manifest["fixtures"]]


def replay(fixture: dict) -> Instance:
    """Execute every recorded action and compare candidates, outcomes, marking, status, and canonical History."""
    assert fixture["format"] == "petrus-impetus-golden-trace"
    assert fixture["version"] == 2
    net = compile_net_definition(NetDefinitionV3.model_validate(fixture["net"], strict=True))
    declarations = set(fixture["bindings"])
    declared = {
        declaration
        for transition in net.transitions.values()
        for declaration in (*transition.guards, *((transition.handler,) if transition.handler else ()))
        if isinstance(declaration, str)
    }
    assert declarations == declared
    assert fixture["bindings"] == {name: BINDING_SPECS[name] for name in sorted(declared)}
    instance = Instance(
        net,
        _marking(fixture["initialMarking"]),
        guards={name: GUARDS[name] for name in declarations if name in GUARDS},
        handlers={name: HANDLERS[name] for name in declarations if name in HANDLERS},
        instance_id=f"golden-{fixture['name'].replace('_', '-')}",
    )
    for expected in fixture["walk"]:
        assert [_binding(value) for value in instance.candidates()] == expected["candidatesBefore"]
        action = expected["action"]
        if action["kind"] == "step":
            outcome = instance.step(at=action["at"])
        elif action["kind"] == "deliver":
            accepted = instance.accept_delivery(
                action["source"],
                tuple(_token(value) for value in action["tokens"]),
                at=action["at"],
                identity=action["identity"],
            )
            outcome = instance.complete_delivery(accepted, at=action["at"])
        elif action["kind"] == "seal":
            instance.seal(action["source"], at=action["at"])
            outcome = None
        else:  # pragma: no cover - fixture schema is closed by generation
            raise AssertionError(action)
        assert (_outcome(outcome) if outcome is not None else None) == expected["outcome"]
        assert instance.marking == _marking(expected["markingAfter"])
        assert instance.status.value == expected["statusAfter"]
    assert instance.marking == _marking(fixture["final"]["marking"])
    assert instance.status.value == fixture["final"]["status"]
    assert [encode_record(record) for record in instance.history] == fixture["history"]
    assert replay_marking(decode_record(record) for record in fixture["history"]) == instance.marking
    return instance
