"""Rich readiness tokens: frozen JSON-faithful data whose pure methods are the guard vocabulary.

The thesis of this experiment is ``impure = transition, pure = inscription``.
Everything a decision needs to *ask* lives here as a method on the token that
owns the question, so the compiler can lift a method reference straight into a
generated guard (``derive_typed_guard`` matches typed parameters to arcs, and an
unbound method is simply a function whose first parameter is ``self``).

Three rules keep the methods liftable:

1. every parameter — including ``self`` — carries a concrete frozen dataclass
   annotation, because arc-color matching is nominal;
2. token *data* stays JSON-faithful and nested values get explicit
   ``to_data``/``from_data`` decoders (the DSL's default
   ``DataclassPayloadConverter`` does not reconstruct nested dataclasses, and a
   guard given the wrong converter fails at enabledness time, not at derivation
   time — experiment B pinned that); and
3. methods are pure views over frozen data. They never allocate identity, read a
   clock, or consult anything outside their arguments.

``RerunRung``, ``RepairRung``, and ``PublicationClaim`` are *thin* tokens: they
carry no fields at all. Their whole content is **where they are** — the
state-as-marking extreme. A rung is spent when its place is empty, and emptiness
is testable only by ``arc.inhibit``, never by a guard.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Literal, cast

# --- structural (thin) tokens --------------------------------------------------
# No fields, by design: presence at a place is the entire state.


@dataclass(frozen=True)
class RerunRung:
    """The unspent rerun rung. Present at ``ladder.rerun`` until a rerun is requested."""


@dataclass(frozen=True)
class RepairRung:
    """The unspent repair rung. Present at ``ladder.repair`` until a repair is requested."""


@dataclass(frozen=True)
class PublicationClaim:
    """The generation's publication latch. Absent until one publication is admitted."""


# --- data tokens ---------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceId:
    """CI evidence identity. Ordering is lexicographic ``(run_id, attempt)``."""

    run_id: int
    attempt: int

    def key(self: EvidenceId) -> tuple[int, int]:
        return (self.run_id, self.attempt)


UNSEEN = EvidenceId(0, 0)
"""The sentinel identity of a generation that has seen no CI evidence yet.

Real evidence identities start at run 1, so a zero watermark is strictly older
than everything. Naming it lets ``readiness.watermark`` always hold exactly one
token, which is what keeps every decision branch's arc shape uniform.
"""


@dataclass(frozen=True)
class HeadObserved:
    """One identified head observation delivered under an exact lifecycle scope."""

    head: str
    relation: Literal["new", "confirmed", "superseded"]
    generation: int
    lineage: str

    def as_head_fact(self: HeadObserved) -> HeadFact:
        return HeadFact(self.head, self.generation, self.lineage)

    def unseen_watermark(self: HeadObserved) -> EvidenceWatermark:
        return EvidenceWatermark(UNSEEN)


@dataclass(frozen=True)
class HeadFact:
    """The generation's head identity. Read by every decision, changed by none."""

    head: str
    generation: int
    lineage: str


@dataclass(frozen=True)
class EvidenceWatermark:
    """The newest CI evidence identity this generation has admitted."""

    seen: EvidenceId


@dataclass(frozen=True)
class CIObserved:
    """One immutable CI observation, and every question the ladder asks about it."""

    head: str
    evidence: EvidenceId
    conclusion: Literal["success", "failure"]
    fingerprint: str | None = None

    # -- predicates (lifted into generated guards) -----------------------------

    def is_for_another_head(self: CIObserved, head: HeadFact) -> bool:
        """Cross-token question: evidence about a head this generation does not own."""
        return self.head != head.head

    def is_not_newer_than(self: CIObserved, watermark: EvidenceWatermark) -> bool:
        """Cross-token question: evidence at or behind the admitted watermark.

        This is the clearest place where data refused to become structure. Strict
        ``(run_id, attempt)`` ordering is a comparison between two token values;
        no marking, read arc, or inhibitor can express it.
        """
        return self.evidence.key() <= watermark.seen.key()

    def is_clean(self: CIObserved) -> bool:
        return self.conclusion == "success"

    def is_classified_failure(self: CIObserved) -> bool:
        """A failure the ladder can spend a rung on: it carries a fingerprint."""
        return self.conclusion == "failure" and self.fingerprint is not None

    # -- folds and emissions (lifted into generated projections) ----------------

    def watermark(self: CIObserved) -> EvidenceWatermark:
        """The advanced watermark this observation establishes."""
        return EvidenceWatermark(self.evidence)

    def publish_request(self: CIObserved, head: HeadFact) -> PublishRequest:
        return PublishRequest(f"publish:{head.head}:g{head.generation}", head.head, head.generation)

    def rerun_request(self: CIObserved, head: HeadFact) -> RerunRequest:
        fingerprint = self.classified()
        return RerunRequest(f"rerun:{head.lineage}:{fingerprint}", head.head, head.lineage, fingerprint, self.evidence)

    def repair_request(self: CIObserved, head: HeadFact) -> RepairRequest:
        fingerprint = self.classified()
        return RepairRequest(
            f"repair:{head.lineage}:{fingerprint}", head.head, head.lineage, fingerprint, self.evidence
        )

    def human_needed(self: CIObserved, head: HeadFact) -> HumanNeeded:
        return HumanNeeded(head.head, head.lineage, self.classified())

    # -- ordinary helper calculation (never a node, never a History row) --------

    def classified(self: CIObserved) -> str:
        """Narrow ``str | None`` to ``str``.

        Unreachable through the authored choice: every branch that calls this is
        guarded by ``is_classified_failure``. The type checker cannot see the
        ordered chain, exactly as experiment A recorded for its own narrowing.
        """
        if self.fingerprint is None:  # pragma: no cover - refused by the generated guard chain
            raise ValueError(f"{self!r} has no fingerprint; only a classified failure spends a rung")
        return self.fingerprint


@dataclass(frozen=True)
class PublishRequest:
    operation: str
    head: str
    generation: int


@dataclass(frozen=True)
class RerunRequest:
    operation: str
    head: str
    lineage: str
    fingerprint: str
    evidence: EvidenceId


@dataclass(frozen=True)
class RepairRequest:
    operation: str
    head: str
    lineage: str
    fingerprint: str
    evidence: EvidenceId


@dataclass(frozen=True)
class HumanNeeded:
    head: str
    lineage: str
    fingerprint: str


@dataclass(frozen=True)
class RerunAccepted:
    operation: str
    head: str


@dataclass(frozen=True)
class RepairLanded:
    operation: str
    head: str
    repaired_head: str


@dataclass(frozen=True)
class Published:
    operation: str
    head: str
    generation: int


# --- explicit JSON-faithful encoding ------------------------------------------


def to_data(value: object) -> dict[str, object]:
    """Encode one known frozen token as a JSON-faithful mapping."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError(f"to_data encodes known token values, got {value!r}")
    return asdict(value)


def _mapping(data: object, noun: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError(f"{noun} data must be a mapping, got {data!r}")
    return cast("dict[str, object]", data)


def _evidence(data: object) -> EvidenceId:
    payload = _mapping(data, "EvidenceId")
    return EvidenceId(run_id=cast(int, payload["run_id"]), attempt=cast(int, payload["attempt"]))


_NESTED_FIELDS: dict[type, dict[str, Callable[[object], object]]] = {
    CIObserved: {"evidence": _evidence},
    EvidenceWatermark: {"seen": _evidence},
    RerunRequest: {"evidence": _evidence},
    RepairRequest: {"evidence": _evidence},
}

TOKEN_TYPES: tuple[type, ...] = (
    EvidenceId,
    RerunRung,
    RepairRung,
    PublicationClaim,
    HeadObserved,
    HeadFact,
    EvidenceWatermark,
    CIObserved,
    PublishRequest,
    RerunRequest,
    RepairRequest,
    HumanNeeded,
    RerunAccepted,
    RepairLanded,
    Published,
)


def from_data[T](annotation: type[T], data: object) -> T:
    """Reconstruct one known frozen token from its JSON-faithful mapping."""
    if annotation not in TOKEN_TYPES:
        raise TypeError(f"from_data reconstructs known token values only, got {annotation!r}")
    payload = _mapping(data, annotation.__name__)
    nested = _NESTED_FIELDS.get(annotation, {})
    arguments: dict[str, object] = {}
    for field in fields(cast("type[EvidenceId]", annotation)):
        raw = payload[field.name]
        decode = nested.get(field.name)
        arguments[field.name] = decode(raw) if callable(decode) else raw
    return annotation(**arguments)


@dataclass(frozen=True)
class TokenConverter:
    """The payload converter every generated guard, projection, and Activity gets.

    Without it the DSL default silently hands a guard a ``CIObserved`` whose
    ``evidence`` is a ``dict``, and the failure surfaces inside enabledness as a
    skipped binding rather than as a derivation error.
    """

    def decode(self, value: object, annotation: object) -> object:
        if not isinstance(annotation, type):
            raise TypeError(f"TokenConverter requires a concrete token type, got {annotation!r}")
        return from_data(annotation, value)

    def encode(self, value: object, annotation: object) -> object:
        if not isinstance(annotation, type) or not isinstance(value, annotation):
            raise ValueError(f"TokenConverter cannot encode {value!r} as {annotation!r}")
        return to_data(value)


CONVERTER = TokenConverter()
