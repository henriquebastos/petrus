"""Generate the deterministic, Impetus-native golden trace corpus.

The fixtures are language-neutral JSON assembled by driving the public Impetus
Net, Instance, canonical Net-definition, and History codec APIs.  No Petrus
oracle checkout or private source is required.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path

from petrus.impetus.history.codec import encode_record
from petrus.impetus.instance import Instance
from petrus.impetus.net_definition import compile_net_definition, project_net_definition
from petrus.impetus.petrinet import Arc, ArcMode, Binding, Marking, Net, NetPath, Place, Token, Transition

FORMAT = "petrus-impetus-golden-trace"
VERSION = 2
GENERATION_COMMAND = "UV_FROZEN=1 uv run python scripts/gen-golden-traces.py spec/traces"


def token(color: str | None = None, data: object = None) -> Token:
    return Token(color, data)


def marking(entries: dict[str, tuple[Token, ...]]) -> Marking:
    return Marking({NetPath(place): tokens for place, tokens in entries.items()})


def arc(source: str, target: str, *args, **kwargs) -> Arc:
    return Arc(NetPath(source), NetPath(target), *args, **kwargs)


def place(path: str, color: str | None = None) -> Place:
    return Place(NetPath(path), color)


def transition(path: str, **kwargs) -> Transition:
    return Transition(NetPath(path), **kwargs)


def encoded_token(value: Token) -> dict[str, object]:
    return {"color": value.color, "data": value.data}


def encoded_selection(selection: tuple[NetPath, tuple[Token, ...]]) -> dict[str, object]:
    place, tokens = selection
    return {"place": str(place), "tokens": [encoded_token(value) for value in tokens]}


def encoded_binding(value: Binding) -> dict[str, object]:
    return {
        "transition": str(value.transition),
        "consumed": [encoded_selection(selection) for selection in value.consumed],
        "read": [encoded_selection(selection) for selection in value.read],
        "delivered": [encoded_token(item) for item in value.delivered],
    }


def encoded_marking(value: Marking) -> list[dict[str, object]]:
    return [
        {"place": str(place), "tokens": [encoded_token(item) for item in tokens]}
        for place, tokens in sorted(value, key=lambda entry: str(entry[0]))
    ]


def encoded_outcome(value) -> dict[str, object]:
    return {
        "occurrence": value.occurrence,
        "transition": str(value.transition),
        "consumed": [encoded_token(item) for item in value.consumed],
        "produced": [{"place": str(place), "token": encoded_token(item)} for place, item in value.produced],
    }


def amount_gte_100(value: Binding) -> bool:
    return value.peeked[0].data["amount"] >= 100


def amount_lt_100(value: Binding) -> bool:
    return value.peeked[0].data["amount"] < 100


def settle(value: Binding, outputs) -> dict[NetPath, tuple[Token, ...]]:
    del outputs
    [payment] = value.tokens
    return {
        NetPath("approved"): (token("ApprovalNotice", {"approved": True}),),
        NetPath("ledger"): (token("LedgerEntry", {"amount": payment.data["amount"]}),),
    }


GUARDS = {"amount_gte_100": amount_gte_100, "amount_lt_100": amount_lt_100}
HANDLERS = {"settle": settle}
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


def passthrough_chain() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place(name) for name in ("start", "middle", "done")],
        transitions=[transition("advance"), transition("finish")],
        arcs=[arc("start", "advance"), arc("advance", "middle"), arc("middle", "finish"), arc("finish", "done")],
        name="passthrough-chain",
    )
    return (
        net,
        marking({"start": (Token.black(),)}),
        [{"kind": "step", "at": 1}, {"kind": "step", "at": 2}],
        ("A black control token traverses two default passthrough transitions."),
    )


def fifo_queue() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place("queue", "Item"), place("taken", "Item")],
        transitions=[transition("take")],
        arcs=[arc("queue", "take"), arc("take", "taken")],
        name="fifo-queue",
    )
    items = tuple(token("Item", {"seq": value}) for value in (1, 2, 3))
    return (
        net,
        marking({"queue": items}),
        [{"kind": "step", "at": value} for value in (1, 2, 3)],
        ("Three equal-color values leave one place in FIFO order."),
    )


def inhibitor_arc() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place(name) for name in ("ready", "blocked", "drained", "done")],
        transitions=[transition("drain"), transition("proceed")],
        arcs=[
            arc("blocked", "drain"),
            arc("drain", "drained"),
            arc("ready", "proceed"),
            arc("blocked", "proceed", ArcMode.INHIBIT),
            arc("proceed", "done"),
        ],
        name="inhibitor-arc",
    )
    return (
        net,
        marking({"ready": (Token.black(),), "blocked": (Token.black(),)}),
        [
            {"kind": "step", "at": 1},
            {"kind": "step", "at": 2},
        ],
        "An inhibitor blocks proceed until drain removes the blocking token.",
    )


def conflict_selection() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place(name) for name in ("shared", "a_won", "b_won")],
        transitions=[transition("choose_a"), transition("choose_b")],
        arcs=[
            arc("shared", "choose_a"),
            arc("choose_a", "a_won"),
            arc("shared", "choose_b"),
            arc("choose_b", "b_won"),
        ],
        name="conflict-selection",
    )
    return (
        net,
        marking({"shared": (Token.black(),)}),
        [{"kind": "step", "at": 1}],
        ("Two candidates conflict over one token; conservative selection chooses the first stable binding."),
    )


def per_arc_passthrough() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place("input", "X"), place("config", "Config"), place("left", "X"), place("right", "X")],
        transitions=[transition("fanout")],
        arcs=[
            arc("input", "fanout", weight=2),
            arc("config", "fanout", ArcMode.READ),
            arc("fanout", "left"),
            arc("fanout", "right"),
        ],
        name="per-arc-passthrough",
    )
    initial = marking(
        {
            "input": (token("X", {"n": 1}), token("X", {"n": 2})),
            "config": (token("Config", {"mode": "strict"}),),
        }
    )
    return (
        net,
        initial,
        [{"kind": "step", "at": 1}],
        (
            "A weight-two consume forwards each X independently through each admitting output arc; "
            "the read Config remains in place and contributes no output."
        ),
    )


def guard_enumeration() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place("pending", "Payment"), place("accepted", "Payment"), place("rejected", "Payment")],
        transitions=[
            transition("accept", guards=("amount_gte_100",)),
            transition("reject", guards=("amount_lt_100",)),
        ],
        arcs=[
            arc("pending", "accept"),
            arc("accept", "accepted"),
            arc("pending", "reject"),
            arc("reject", "rejected"),
        ],
        name="guard-enumeration",
    )
    initial = marking(
        {
            "pending": (
                token("Payment", {"amount": 150, "currency": "USD"}),
                token("Payment", {"amount": 40, "currency": "USD"}),
            )
        }
    )
    return (
        net,
        initial,
        [{"kind": "step", "at": 1}, {"kind": "step", "at": 2}],
        (
            "Guards evaluate every binding: reject skips the failing FIFO head and remains enabled for the deeper Payment."
        ),
    )


def source_delivery() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place("events", "RawEvent")],
        transitions=[transition("webhook")],
        arcs=[arc("webhook", "events")],
        name="source-delivery",
    )
    actions = [
        {
            "kind": "deliver",
            "source": "webhook",
            "tokens": [encoded_token(token("RawEvent", {"event_id": "evt-7", "status": "accepted"}))],
            "identity": "provider-event-7",
            "at": 1,
        },
        {"kind": "seal", "source": "webhook", "at": 2},
    ]
    return (
        net,
        Marking(),
        actions,
        ("An identified external delivery fires a scheduler-excluded source and is recorded before projection."),
    )


def heterogeneous_fanout() -> tuple[Net, Marking, list[dict[str, object]], str]:
    net = Net(
        places=[place("pending", "Payment"), place("approved", "ApprovalNotice"), place("ledger", "LedgerEntry")],
        transitions=[transition("settle", handler="settle")],
        arcs=[
            arc("pending", "settle"),
            arc("settle", "approved"),
            arc("settle", "ledger"),
        ],
        name="heterogeneous-fanout",
    )
    return (
        net,
        marking({"pending": (token("Payment", {"amount": 150}),)}),
        [{"kind": "step", "at": 1}],
        ("One handler firing emits different single-color values to two independently typed output arcs."),
    )


SCENARIOS: tuple[Callable[[], tuple[Net, Marking, list[dict[str, object]], str]], ...] = (
    passthrough_chain,
    fifo_queue,
    inhibitor_arc,
    conflict_selection,
    per_arc_passthrough,
    guard_enumeration,
    source_delivery,
    heterogeneous_fanout,
)


def decode_token(value: dict[str, object]) -> Token:
    return token(value["color"], value["data"])


def generate(scenario: Callable[[], tuple[Net, Marking, list[dict[str, object]], str]]) -> dict[str, object]:
    net, initial, actions, description = scenario()
    definition = project_net_definition(net)
    net = compile_net_definition(definition)
    initial = Marking(dict(sorted(initial, key=lambda entry: str(entry[0]))))
    declarations = {
        declaration
        for transition in net.transitions.values()
        for declaration in (*transition.guards, *((transition.handler,) if transition.handler else ()))
        if isinstance(declaration, str)
    }
    fixture: dict[str, object] = {
        "format": FORMAT,
        "version": VERSION,
        "name": scenario.__name__,
        "description": description,
        "net": definition.model_dump(mode="json"),
        "bindings": {name: BINDING_SPECS[name] for name in sorted(declarations)},
        "initialMarking": encoded_marking(initial),
    }
    instance = Instance(
        net,
        initial,
        guards={name: GUARDS[name] for name in declarations if name in GUARDS},
        handlers={name: HANDLERS[name] for name in declarations if name in HANDLERS},
        instance_id=f"golden-{scenario.__name__.replace('_', '-')}",
    )
    walk = []
    for action in actions:
        step: dict[str, object] = {"candidatesBefore": [encoded_binding(value) for value in instance.candidates()]}
        if action["kind"] == "step":
            outcome = instance.step(at=action["at"])
        elif action["kind"] == "deliver":
            accepted = instance.accept_delivery(
                action["source"],
                tuple(decode_token(value) for value in action["tokens"]),
                at=action["at"],
                identity=action["identity"],
            )
            outcome = instance.complete_delivery(accepted, at=action["at"])
        elif action["kind"] == "seal":
            instance.seal(action["source"], at=action["at"])
            outcome = None
        else:  # pragma: no cover - scenarios are closed above
            raise AssertionError(action)
        step |= {
            "action": action,
            "outcome": encoded_outcome(outcome) if outcome is not None else None,
            "markingAfter": encoded_marking(instance.marking),
            "statusAfter": instance.status.value,
        }
        walk.append(step)
    fixture |= {
        "walk": walk,
        "history": [encode_record(record) for record in instance.history],
        "final": {"marking": encoded_marking(instance.marking), "status": instance.status.value},
    }
    return fixture


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} OUTPUT_DIRECTORY")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for scenario in SCENARIOS:
        fixture = generate(scenario)
        text = json.dumps(fixture, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
        path = output / f"{fixture['name']}.json"
        path.write_text(text)
        entries.append(
            {
                "file": path.name,
                "name": fixture["name"],
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "walkSteps": len(fixture["walk"]),
            }
        )
        print(f"wrote {path.name} ({len(fixture['walk'])} steps)")
    manifest = {
        "format": "petrus-impetus-golden-trace-manifest",
        "version": VERSION,
        "generator": "scripts/gen-golden-traces.py",
        "generationCommand": GENERATION_COMMAND,
        "fixtures": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    )
    print(f"manifest: {len(entries)} Impetus-native fixtures")


if __name__ == "__main__":
    main()
