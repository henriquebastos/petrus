"""The authored readiness flow as a **guarded decision net** (experiment v2).

Every domain fact, Activity, low-level publication gate, helper calculation,
and fixture simplification is v1's, imported read-only from
``../typed-flow-vertical-slice/scenario.py``. Exactly one thing changes: v1's
single pure ``route_ci`` returning ``Decision[state, outcome-union]`` becomes
five **rungs**, each with its own pure predicate, its own pure fold, and its
own generated transition.

The honest physics of that change, all measurable here:

- **Mutual exclusivity became an authoring obligation.** Petrus selection has
  no case priority: two simultaneously true rung guards produce two enabled
  candidates in conflict and the selection policy — not the domain — picks.
  Nothing in the algebra or the compiler can prove exclusivity, so the
  predicates below are written mutually exclusive *by construction* over one
  shared classification (``reading``) and pinned by an executable grid test
  (``test_guarded_exclusivity.py``).
- **Sequential state-dependence became re-derivation.** v1's ``route_ci``
  advanced the watermark and normalized the rung budget once, before choosing.
  Independent rungs cannot share that intermediate, so every predicate and
  every fold re-derives it through ``reading``/``normalized_ladder``. Nine of
  the eleven pure functions below call one of those two helpers.
- **The absorbing rung became nameable.** v1's ``Ignored`` outcome produced no
  token, so canonical History showed only "the route transition fired and
  produced state" — the documented Ignored-invisibility limit (v1 report §11).
  Here the fired transition path is ``readiness.route_ci.ignore.fire``.

The fixture's semantics are unchanged: ``test_guarded_exclusivity.py`` proves
rung fold+emit reproduces v1's ``route_ci`` state and outcome over a
systematic (state × event) grid.
"""

from dataclasses import dataclass, replace

from algebra import await_event, effect, lifecycle, low_level, terminal
from domain import (
    CIObserved,
    HeadObserved,
    HumanNeeded,
    Ladder,
    PublishAcknowledged,
    PublishRequested,
    ReadinessState,
    RepairRequested,
    RerunRequested,
)
from guarded_algebra import guarded_machine, on, rung
from scenario import (
    accept_publish,
    admit_head,
    is_newer,
    publication_gate,
    publish_operation,
    repair,
    repair_operation,
    rerun,
    rerun_operation,
    retry_key,
)

# --- shared pure classification ----------------------------------------------
# The single place where the observation's sequential meaning is derived. It
# creates no transition and no History row; it is the seam that keeps five
# independent rungs consistent with each other.


def normalized_ladder(state: ReadinessState, event: CIObserved) -> Ladder:
    """The rung budget this observation is measured against.

    A failure whose ``(lineage, fingerprint)`` retry key differs from the
    ladder's starts a fresh budget; a matching one only advances the
    watermark. An observation with no fingerprint has no rung to spend, so the
    ladder is returned untouched.
    """
    fingerprint = event.fingerprint
    ladder = state.ladder
    if fingerprint is None:
        return ladder
    if ladder.fingerprint is None or retry_key(state.lineage, fingerprint) != retry_key(
        ladder.lineage, ladder.fingerprint
    ):
        return Ladder(state.lineage, fingerprint, False, False, event.evidence)
    return replace(ladder, watermark=event.evidence)


@dataclass(frozen=True)
class Reading:
    """One observation's classification, shared by every rung of the ladder."""

    fresh: bool
    clean: bool
    fingerprint: str | None
    publication_pending: bool
    ladder: Ladder


def reading(state: ReadinessState, event: CIObserved) -> Reading:
    """Classify one CI observation against the current state baton."""
    return Reading(
        fresh=event.head == state.head and is_newer(event.evidence, state.ladder.watermark),
        clean=event.conclusion == "success",
        fingerprint=event.fingerprint,
        publication_pending=state.publication_operation is not None,
        ladder=normalized_ladder(state, event),
    )


def _rung_fingerprint(event: CIObserved, rung_id: str) -> str:
    if event.fingerprint is None:  # pragma: no cover - the rung guard refuses this observation
        raise ValueError(f"rung [{rung_id}] fired on a failure with no fingerprint")
    return event.fingerprint


# --- rung predicates -----------------------------------------------------------
# Written mutually exclusive AND exhaustive over the shared reading. This is an
# authoring obligation, not a checked property: see report.md §7.


def not_actionable(state: ReadinessState, event: CIObserved) -> bool:
    """Nothing to do: stale/foreign evidence, an already-requested publication, or an unclassified failure."""
    observation = reading(state, event)
    if not observation.fresh:
        return True
    if observation.clean:
        return observation.publication_pending
    return observation.fingerprint is None


def first_clean(state: ReadinessState, event: CIObserved) -> bool:
    """Fresh clean evidence with no publication yet requested for this generation."""
    observation = reading(state, event)
    return observation.fresh and observation.clean and not observation.publication_pending


def fresh_failure(state: ReadinessState, event: CIObserved) -> bool:
    """A classified failure whose retry budget still has its rerun rung."""
    observation = reading(state, event)
    return (
        observation.fresh
        and not observation.clean
        and observation.fingerprint is not None
        and not observation.ladder.rerun_used
    )


def repeated_failure(state: ReadinessState, event: CIObserved) -> bool:
    """A classified failure after the rerun rung is spent and before repair is."""
    observation = reading(state, event)
    return (
        observation.fresh
        and not observation.clean
        and observation.fingerprint is not None
        and observation.ladder.rerun_used
        and not observation.ladder.repair_used
    )


def ladder_exhausted(state: ReadinessState, event: CIObserved) -> bool:
    """A classified failure with both rungs spent: the ladder is out of moves."""
    observation = reading(state, event)
    return (
        observation.fresh
        and not observation.clean
        and observation.fingerprint is not None
        and observation.ladder.rerun_used
        and observation.ladder.repair_used
    )


# --- rung folds ----------------------------------------------------------------


def absorb(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Advance the watermark for a fresh observation; leave a stale one alone."""
    if not reading(state, event).fresh:
        return state
    return replace(state, ladder=replace(state.ladder, watermark=event.evidence))


def note_publication(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Advance the watermark and latch the publication operation into state."""
    return replace(
        state,
        ladder=replace(state.ladder, watermark=event.evidence),
        publication_operation=publish_operation(state.head, state.generation),
    )


def spend_rerun(state: ReadinessState, event: CIObserved) -> ReadinessState:
    return replace(state, ladder=replace(normalized_ladder(state, event), rerun_used=True))


def spend_repair(state: ReadinessState, event: CIObserved) -> ReadinessState:
    return replace(state, ladder=replace(normalized_ladder(state, event), repair_used=True))


def exhaust(state: ReadinessState, event: CIObserved) -> ReadinessState:
    return replace(state, ladder=normalized_ladder(state, event))


# --- rung emissions ------------------------------------------------------------


def request_publication(state: ReadinessState, event: CIObserved) -> PublishRequested:
    del event  # the publication operation is keyed by head and generation only
    return PublishRequested(publish_operation(state.head, state.generation), state.head, state.generation)


def request_rerun(state: ReadinessState, event: CIObserved) -> RerunRequested:
    fingerprint = _rung_fingerprint(event, "rerun")
    return RerunRequested(
        rerun_operation(state.lineage, fingerprint), state.head, state.lineage, fingerprint, event.evidence
    )


def request_repair(state: ReadinessState, event: CIObserved) -> RepairRequested:
    fingerprint = _rung_fingerprint(event, "repair")
    return RepairRequested(
        repair_operation(state.lineage, fingerprint), state.head, state.lineage, fingerprint, event.evidence
    )


def surface_human_needed(state: ReadinessState, event: CIObserved) -> HumanNeeded:
    return HumanNeeded(state.head, state.lineage, _rung_fingerprint(event, "human"))


# --- the authored flow ---------------------------------------------------------


def guarded_readiness_flow():
    """One transition per ladder rung; everything else is v1's flow verbatim."""
    return guarded_machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .branch(
                "route_ci",
                rungs=(
                    rung("ignore", when=not_actionable, fold=absorb).drop(),
                    rung("publish", when=first_clean, fold=note_publication).emit(request_publication),
                    rung("rerun", when=fresh_failure, fold=spend_rerun).emit(request_rerun),
                    rung("repair", when=repeated_failure, fold=spend_repair).emit(request_repair),
                    rung("human", when=ladder_exhausted, fold=exhaust).emit(surface_human_needed),
                ),
            )
            .route(
                {
                    PublishRequested: low_level("publish_once", publication_gate, returns=PublishAcknowledged),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )


__all__ = [
    "Reading",
    "absorb",
    "exhaust",
    "first_clean",
    "fresh_failure",
    "guarded_readiness_flow",
    "ladder_exhausted",
    "normalized_ladder",
    "not_actionable",
    "note_publication",
    "reading",
    "repeated_failure",
    "request_publication",
    "request_repair",
    "request_rerun",
    "spend_repair",
    "spend_rerun",
    "surface_human_needed",
]
