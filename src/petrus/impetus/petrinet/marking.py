"""
Tokens, token queues, and markings.

- ``Token`` — a colored token: exactly one color plus its structured data. The
  black token carries no color.
- ``TokenQueue`` — the tokens at one place, FIFO order, each paired with its
  recorded entry instant. The one home of queue semantics: it owns
  front-most-equal-occurrence removal, and positions index tokens and entry
  instants alike — aligned by construction, not by convention.
- ``Marking`` — the immutable distribution of tokens across places, as per-place
  FIFO queues. Every mutating operation returns a new marking. A marking is
  time-blind: it speaks the token half only, and the runtime derives its
  marking as the token-half view of its pair-queues (``entry_instants`` is the
  time half's view).

Immutability makes each a value: firing is a function ``(marking, ...) ->
marking``, and replaying recorded movements over empty queues rebuilds state.
"""

from __future__ import annotations

# Python imports
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

# Internal imports
from petrus.impetus.petrinet.schema import Color, Instant, NetPath


@dataclass(frozen=True)
class Token:
    """A colored token: one color and its data. Color ``None`` is the black token."""

    color: Color | None = None
    data: Any = None

    @classmethod
    def black(cls) -> Token:
        """The black token — control flow with no data."""
        return cls()

    @property
    def is_black(self) -> bool:
        return self.color is None

    def __repr__(self) -> str:
        if self.is_black:
            return "Token.black()"
        return f"Token({self.color!r}, {self.data!r})"


class TokenNotPresent(ValueError):
    """
    A queue operation named a token the queue does not hold — the fail-loud
    half of ``TokenQueue.remove``'s contract (a removal that silently
    under-delivers would be a footgun). Carries the ``token`` so the seams
    that delegate here can re-address the rejection in their own terms.
    """

    def __init__(self, token: Token):
        super().__init__(f"cannot remove {token!r}: token not present")
        self.token = token


class TokenQueue(Sequence):
    """
    The tokens at one place, FIFO order, each paired with its recorded entry
    instant — the pair-queue that the marking (time-blind) and the timer
    anchors (``entry_instants``) are both views of. NOT a set: duplicates are
    legal and order is significant. A value: ``deposit`` and ``remove`` return
    a new queue, the original is never mutated.

    The sequence surface is the token half (``queue[0]``, iteration, ``len``);
    ``instants`` is the position-aligned time half. Positions index both —
    contractual: enabledness selects by queue position, and a selection's
    positions must index the entry instants.
    """

    __slots__ = ("_tokens", "_instants")

    def __init__(self, pairs: Iterable[tuple[Token, Instant]] = ()):
        pairs = tuple(pairs)
        self._tokens: tuple[Token, ...] = tuple(token for token, _ in pairs)
        self._instants: tuple[Instant, ...] = tuple(instant for _, instant in pairs)

    @classmethod
    def time_blind(cls, tokens: Iterable[Token]) -> TokenQueue:
        """A queue over the token half alone — every entry instant ``None``, unrecorded (never the epoch): the spelling for time-free queue work, the ``Marking``'s."""
        return cls((token, None) for token in tokens)

    @property
    def tokens(self) -> tuple[Token, ...]:
        """The token half, front to back — what the marking view reads."""
        return self._tokens

    @property
    def instants(self) -> tuple[Instant, ...]:
        """The entry-instant half, position-aligned with ``tokens`` — what the time view reads; the ``Delay`` anchors."""
        return self._instants

    def deposit(self, token: Token, instant: Instant) -> TokenQueue:
        """A new queue with ``token`` appended to the back, entered at ``instant``."""
        return TokenQueue(zip(self._tokens + (token,), self._instants + (instant,)))

    def remove(self, tokens: Iterable[Token]) -> TokenQueue:
        """
        A new queue with each of ``tokens`` removed, in request order — each
        matching its front-most EQUAL occurrence on the token half (tokens
        are values; the instant leaves with its token), so the rest keeps its
        queue order. Raises ``TokenNotPresent`` (a ``ValueError``) if a token
        is not present, leaving no partial removal observable.
        """
        remaining_tokens = list(self._tokens)
        remaining_instants = list(self._instants)
        for token in tokens:
            try:
                position = remaining_tokens.index(token)  # front-most equal occurrence
            except ValueError:
                raise TokenNotPresent(token) from None
            del remaining_tokens[position], remaining_instants[position]
        return TokenQueue(zip(remaining_tokens, remaining_instants))

    def admitted_by(self, admits: Callable[[Token], bool], limit: int | None = None) -> tuple[int, ...]:
        """
        The queue positions of the tokens ``admits`` accepts, front-to-back —
        all of them, or the first ``limit`` where the caller needs no more
        (the head selection, the inhibit gate). Positions rather than tokens:
        a selection's positions also index the entry instants — the alignment
        contract. The admission judgment itself (inscription narrowed by
        filter) is enabledness's, handed in already bound to its arc: the
        queue owns the scan, never the rule. Eager — the positions are an
        owned value, never a pipeline. ``limit`` must be positive: a caller
        who needs none should not scan, and a zero that silently meant
        "all of them" would over-deliver [convention 3].
        """
        if limit is not None and limit < 1:
            raise ValueError(f"admitted_by requires a positive limit (or None for all), got {limit!r}")
        positions: list[int] = []
        for position, token in enumerate(self._tokens):
            if admits(token):
                positions.append(position)
                if len(positions) == limit:
                    break
        return tuple(positions)

    def __getitem__(self, position):
        if isinstance(position, slice):
            return TokenQueue(zip(self._tokens[position], self._instants[position]))
        return self._tokens[position]

    def __len__(self) -> int:
        return len(self._tokens)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TokenQueue) and self._tokens == other._tokens and self._instants == other._instants

    __hash__ = None  # queues compare by value but are not used as keys (token data may be unhashable)

    def __repr__(self) -> str:
        body = ", ".join(f"({token!r}, {instant!r})" for token, instant in zip(self._tokens, self._instants))
        return f"TokenQueue([{body}])"


class Marking:
    """
    Immutable distribution of tokens across places: ``NetPath -> tuple[Token, ...]``.

    Sparse (empty places are absent). ``consume`` and ``deposit`` return a new
    marking; the original is never mutated.

    Example::

        m = Marking.from_counts({NetPath("a"): 1})
        m2 = m.consume(NetPath("a"), (Token.black(),))
        m3 = m2.deposit(NetPath("b"), Token.black())
    """

    def __init__(self, queues: dict[NetPath, tuple[Token, ...]] | None = None):
        self._queues: dict[NetPath, tuple[Token, ...]] = {
            path: tuple(queue) for path, queue in (queues or {}).items() if queue
        }

    @classmethod
    def from_counts(cls, counts: dict[NetPath, int]) -> Marking:
        """Build a marking of black tokens from ``{place: count}``."""
        return cls({path: (Token.black(),) * count for path, count in counts.items()})

    def place(self, path: NetPath) -> tuple[Token, ...]:
        """The FIFO queue at a place (empty tuple if absent)."""
        return self._queues.get(path, ())

    def consume(self, path: NetPath, tokens: Sequence[Token]) -> Marking:
        """
        Return a new marking with ``tokens`` removed from a place's queue.

        Selection is enabledness's job; consume removes exactly the tokens the
        binding selected — colored selection may pick them mid-queue. Removal
        is ``TokenQueue``'s rule, delegated time-blind: each requested token
        removes its front-most equal occurrence (tokens are values), so the
        rest keeps its queue order. Raises ``ValueError`` if a token is not
        present — a consume that silently under-delivers would be a footgun;
        the binding guarantees presence before firing. The dict bookkeeping —
        sparseness included — stays the marking's.
        """
        try:
            remaining = TokenQueue.time_blind(self.place(path)).remove(tokens)
        except TokenNotPresent as error:
            raise ValueError(f"cannot consume {error.token!r} from {path}: token not present") from None
        queues = dict(self._queues)
        if remaining:
            queues[path] = remaining.tokens
        else:
            queues.pop(path, None)
        return Marking(queues)

    def deposit(self, path: NetPath, token: Token) -> Marking:
        """Return a new marking with ``token`` appended to a place's queue."""
        queues = dict(self._queues)
        queues[path] = self.place(path) + (token,)
        return Marking(queues)

    def counts(self) -> dict[NetPath, int]:
        """Token count per non-empty place."""
        return {path: len(queue) for path, queue in self._queues.items()}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Marking) and self._queues == other._queues

    __hash__ = None  # markings compare by value but are not used as keys

    def __bool__(self) -> bool:
        return bool(self._queues)

    def __iter__(self):
        """Yield ``(place, queue)`` for each non-empty place."""
        return iter(self._queues.items())

    def __repr__(self) -> str:
        body = ", ".join(f"{path}: {len(queue)}" for path, queue in self._queues.items())
        return f"Marking({{{body}}})"
