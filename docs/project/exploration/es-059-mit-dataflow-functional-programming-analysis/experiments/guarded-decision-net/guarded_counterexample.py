"""Two deliberately broken toy branches: overlapping rungs, and a gap.

These exist to be wrong. They are the executable form of the experiment's
central finding: once a decision is spread across independently guarded
transitions, **mutual exclusivity and exhaustiveness become authoring
obligations that neither the algebra nor Petrus can check**.

``overlapping_flow`` has two rungs whose predicates are both true for a
fingerprinted failure. ``incomplete_flow`` has one rung that answers only
failures, so a clean observation matches no rung at all. Neither mistake is
refused at composition time, at lowering time, or at ``NetSpec.build()``:
both compile to a valid, strictly round-tripping canonical Net v3.
"""

from __future__ import annotations

from dataclasses import dataclass

from algebra import await_event, lifecycle, terminal
from domain import CIObserved, HeadObserved, ReadinessState
from guarded_algebra import guarded_machine, on, rung
from scenario import admit_head

BRANCH = "overlap.route_ci"
ALPHA = "overlap.route_ci.alpha.fire"
BETA = "overlap.route_ci.beta.fire"


@dataclass(frozen=True)
class AlphaSeen:
    head: str


@dataclass(frozen=True)
class BetaSeen:
    head: str


def keep_state(state: ReadinessState, event: CIObserved) -> ReadinessState:
    del event
    return state


def any_failure(state: ReadinessState, event: CIObserved) -> bool:
    """Deliberately overlaps ``fingerprinted_failure``."""
    del state
    return event.conclusion == "failure"


def fingerprinted_failure(state: ReadinessState, event: CIObserved) -> bool:
    """Deliberately overlaps ``any_failure``."""
    del state
    return event.conclusion == "failure" and event.fingerprint is not None


def see_alpha(state: ReadinessState, event: CIObserved) -> AlphaSeen:
    del event
    return AlphaSeen(state.head)


def see_beta(state: ReadinessState, event: CIObserved) -> BetaSeen:
    del event
    return BetaSeen(state.head)


def overlapping_flow():
    """Two rungs, both true for a fingerprinted failure: a conflict, not a case table."""
    return guarded_machine(
        "overlap",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .branch(
                "route_ci",
                rungs=(
                    rung("alpha", when=any_failure, fold=keep_state).emit(see_alpha),
                    rung("beta", when=fingerprinted_failure, fold=keep_state).emit(see_beta),
                ),
            )
            .route({AlphaSeen: terminal("alpha_seen"), BetaSeen: terminal("beta_seen")}),
        ),
    )


def incomplete_flow():
    """One rung answering only failures: a clean observation matches nothing."""
    return guarded_machine(
        "overlap",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .branch("route_ci", rungs=(rung("alpha", when=any_failure, fold=keep_state).emit(see_alpha),))
            .route({AlphaSeen: terminal("alpha_seen")}),
        ),
    )


__all__ = [
    "ALPHA",
    "BETA",
    "BRANCH",
    "AlphaSeen",
    "BetaSeen",
    "any_failure",
    "fingerprinted_failure",
    "incomplete_flow",
    "keep_state",
    "overlapping_flow",
    "see_alpha",
    "see_beta",
]
