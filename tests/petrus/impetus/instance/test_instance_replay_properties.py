"""Bounded generative checks that live Instance state stays replayable and resumable."""

from __future__ import annotations

# Pip imports
from hypothesis import given, note, settings, strategies as st

# Internal imports
from petrus.impetus.history import replay_marking
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Marking, Net, NetPath, Place, Token, Transition

PLACES = tuple(NetPath(f"p{index}") for index in range(3))
TRANSITIONS = tuple(NetPath(f"t{index}") for index in range(2))
SOURCE = NetPath("source")
TOKENS = (Token.black(), Token("A", 0), Token("A", 1), Token("B", 0))


@st.composite
def _scenario_specs(draw):
    ordinary = []
    for _ in TRANSITIONS:
        consumed = draw(st.integers(0, 2))
        consume_weight = draw(st.integers(1, 2))
        produced = draw(st.integers(0, 2))
        gate_mode = draw(st.sampled_from((None, ArcMode.READ, ArcMode.INHIBIT)))
        gate = draw(st.sampled_from(tuple(index for index in range(3) if index != consumed)))
        gate_weight = draw(st.integers(1, 2))
        ordinary.append((consumed, consume_weight, produced, gate_mode, gate, gate_weight))
    source_output = draw(st.integers(0, 2))
    initial = draw(st.tuples(*(st.lists(st.sampled_from(TOKENS), max_size=3).map(tuple) for _ in PLACES)))
    actions = draw(st.integers(0, 20))
    return tuple(ordinary), source_output, initial, actions


def _net(ordinary, source_output):
    arcs = [Arc(SOURCE, PLACES[source_output])]
    for transition, (consumed, consume_weight, produced, gate_mode, gate, gate_weight) in zip(TRANSITIONS, ordinary):
        arcs.extend((Arc(PLACES[consumed], transition, weight=consume_weight), Arc(transition, PLACES[produced])))
        if gate_mode is not None:
            arcs.append(Arc(PLACES[gate], transition, mode=gate_mode, weight=gate_weight))
    return Net(
        places=[Place(place) for place in PLACES],
        transitions=[*(Transition(transition) for transition in TRANSITIONS), Transition(SOURCE)],
        arcs=arcs,
    )


def _assert_replay_and_resume(instance, net):
    assert instance.marking == replay_marking(instance.history)
    cloned = InMemoryHistoryStore()
    cloned.extend(list(instance.history.records))
    resumed = Instance.resume(net, cloned)
    assert resumed.marking == instance.marking
    assert resumed.watermark == instance.watermark
    assert resumed.candidates() == instance.candidates()
    assert tuple(occurrence.id for occurrence in resumed.in_flight) == tuple(
        occurrence.id for occurrence in instance.in_flight
    )


@settings(max_examples=300, derandomize=True, deadline=None)
@given(spec=_scenario_specs(), data=st.data())
def test_legal_instance_actions_remain_replayable_and_resumable(spec, data):
    ordinary, source_output, initial, action_count = spec
    note(f"ordinary={ordinary}, source_output={source_output}, initial={initial}, actions={action_count}")
    net = _net(ordinary, source_output)
    marking = Marking({place: tokens for place, tokens in zip(PLACES, initial)})
    instance = Instance(net, marking, instance_id="property-instance")
    _assert_replay_and_resume(instance, net)

    for action_number in range(action_count):
        legal = ["deliver"]
        candidates = instance.candidates()
        if candidates:
            legal.extend(("step", "begin"))
        if instance.in_flight:
            legal.append("complete")
        action = data.draw(st.sampled_from(legal), label=f"action[{action_number}]")
        note(f"action[{action_number}]={action}")
        if action == "deliver":
            accepted = instance.accept_delivery(
                SOURCE,
                data.draw(st.sampled_from(TOKENS), label=f"delivery[{action_number}]"),
                identity=f"delivery-{action_number}",
            )
            instance.complete_delivery(accepted)
        elif action == "step":
            instance.step()
        elif action == "begin":
            candidate = data.draw(st.sampled_from(candidates), label=f"candidate[{action_number}]")
            instance.begin(candidate)
        else:
            occurrence = data.draw(st.sampled_from(instance.in_flight), label=f"occurrence[{action_number}]")
            output = ordinary[TRANSITIONS.index(occurrence.binding.transition)][2]
            instance.complete(occurrence, {PLACES[output]: occurrence.binding.tokens})
        _assert_replay_and_resume(instance, net)
