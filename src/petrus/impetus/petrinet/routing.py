"""Pure output-arc routing."""

from petrus.impetus.petrinet.marking import Token
from petrus.impetus.petrinet.schema import Arc, NetPath


def route(tokens: tuple[Token, ...], outputs: tuple[Arc, ...]) -> dict[NetPath, tuple[Token, ...]]:
    """
    Route each token to every output arc that admits it, preserving order and
    concatenating per target. Tokens admitted by no output are dropped.
    """
    routed: dict[NetPath, tuple[Token, ...]] = {}
    for arc in outputs:
        admitted = tuple(token for token in tokens if arc.admits(token))
        if admitted:
            routed[arc.target] = routed.get(arc.target, ()) + admitted
    return routed
