"""History-independent Petri firing movement transforms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from petrus.impetus.petrinet.enabledness import Binding
from petrus.impetus.petrinet.marking import Marking, Token, TokenNotPresent, TokenQueue
from petrus.impetus.petrinet.schema import Net, NetPath


@dataclass(frozen=True)
class ConsumedTokens:
    """One consume arc's ordered token movement."""

    place: NetPath
    tokens: tuple[Token, ...]


@dataclass(frozen=True)
class ReadTokens:
    """One read arc's ordered, marking-preserving observation."""

    place: NetPath
    tokens: tuple[Token, ...]


@dataclass(frozen=True)
class ProducedTokens:
    """The ordered tokens deposited at one resolved output place."""

    place: NetPath
    tokens: tuple[Token, ...]


type BeginEffect = ConsumedTokens | ReadTokens


def begin_firing(marking: Marking, binding: Binding) -> tuple[tuple[BeginEffect, ...], Marking]:
    """Apply consumes before validating non-removing reads; return arc-ordered effects and the resulting marking."""
    effects: list[BeginEffect] = []
    for place, tokens in binding.consumed:
        marking = marking.consume(place, tokens)
        effects.append(ConsumedTokens(place, tokens))
    for place, tokens in binding.read:
        try:
            TokenQueue.time_blind(marking.place(place)).remove(tokens)
        except TokenNotPresent as error:
            raise ValueError(f"cannot read {error.token!r} from {place}: token not present") from None
        effects.append(ReadTokens(place, tokens))
    return tuple(effects), marking


def complete_firing(
    net: Net,
    marking: Marking,
    transition: NetPath,
    projected_tokens: Mapping[NetPath | str, Sequence[Token]],
) -> tuple[tuple[ProducedTokens, ...], Marking]:
    """Route projected tokens through output arcs, coalescing aliases in destination first-seen order."""
    outputs = net.outputs(transition)
    emitted: dict[NetPath, tuple[Token, ...]] = {}
    for destination, tokens in projected_tokens.items():
        place = NetPath(destination)
        emitted[place] = emitted.get(place, ()) + tuple(tokens)

    effects: list[ProducedTokens] = []
    for place, tokens in emitted.items():
        deposited = tuple(
            token for token in tokens if any(arc.target == place and arc.admits(token) for arc in outputs)
        )
        if not deposited:
            continue
        for token in deposited:
            marking = marking.deposit(place, token)
        effects.append(ProducedTokens(place, deposited))
    return tuple(effects), marking
