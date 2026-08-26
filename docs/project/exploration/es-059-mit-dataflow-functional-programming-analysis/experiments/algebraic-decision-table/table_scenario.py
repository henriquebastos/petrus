"""The readiness flow re-authored as an ordered, first-match-wins case table.

Everything except the CI decision is imported unmodified from the v1 slice's
``scenario.py``: ``admit_head``, ``accept_publish``, the three typed fake
Activities, the ``publication_gate`` descent fragment, and the ordinary
helper calculations (operation ids, evidence ordering, retry keys). v1's
``route_ci`` — one ~60-line pure function whose branch structure the algebra
could not see — is replaced here by eight authored ``case(...)`` rungs plus
one ``normalize`` pre-step.

Every simplification v1 named in source still holds unchanged (pre-satisfied
publication gates, fake Activities, one baton per generation, `generation` vs
`lineage`, `HeadObserved.relation` as producer-supplied data). Two are new to
this spelling and are named here because the report depends on them:

- **``normalize`` is where sequential logic survives.** ``refresh_ladder``
  resets the rung budget when the ``(lineage, fingerprint)`` key changes. It
  deliberately does **not** advance the watermark, because the ``stale`` case
  below must still be able to compare the arriving evidence against the
  watermark it is normalized alongside. One state flows through the whole
  table: normalize first, then ``when``, then ``fold``/``emit``.
- **Later rungs lean on earlier ones.** ``rerun_available`` does not re-check
  "is this a classified failure?"; the ``published`` and ``unclassified``
  rungs above it already absorbed everything else. That is the ordered
  table's economy, and it is invisible to the type checker — hence
  ``classified()`` below, whose raise is unreachable through the table.
"""

from __future__ import annotations

from dataclasses import replace

from algebra import Machine, await_event, effect, lifecycle, low_level, terminal
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
from table_algebra import case, machine, on, otherwise

# --- ordinary helper calculations ---------------------------------------------
# Imported from v1 unchanged (publish/rerun/repair operation ids, evidence
# ordering, retry keys) plus this one narrowing helper. None of them creates a
# transition or a History row.


def classified(event: CIObserved) -> str:
    """The failure fingerprint, narrowed to ``str``.

    Unreachable through the authored table: the ``unclassified`` rung absorbs
    every failure without a fingerprint before any rung below it runs. The
    ordered table knows that; the type checker does not.
    """
    if event.fingerprint is None:  # pragma: no cover - the table absorbs these first
        raise ValueError("a classified rung ran on an unclassified failure")
    return event.fingerprint


# --- the shared pre-step ------------------------------------------------------


def refresh_ladder(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Give a new ``(lineage, fingerprint)`` key a fresh rung budget.

    Runs once, before the table, on every CI observation. It never advances
    the watermark — that stays a per-rung commit — so ``not_newer`` below
    still sees the watermark the observation must beat.
    """
    if event.head != state.head or not is_newer(event.evidence, state.ladder.watermark):
        return state
    if event.conclusion != "failure" or event.fingerprint is None:
        return state
    ladder = state.ladder
    if ladder.fingerprint is None or retry_key(state.lineage, event.fingerprint) != retry_key(
        ladder.lineage, ladder.fingerprint
    ):
        return replace(state, ladder=Ladder(state.lineage, event.fingerprint, False, False, ladder.watermark))
    return state


# --- classifiers: (state, event) -> bool --------------------------------------


def other_head(state: ReadinessState, event: CIObserved) -> bool:
    """Evidence for a head this generation is not tracking."""
    return event.head != state.head


def not_newer(state: ReadinessState, event: CIObserved) -> bool:
    """Evidence at or behind the watermark: a duplicate or a late arrival."""
    return not is_newer(event.evidence, state.ladder.watermark)


def first_clean(state: ReadinessState, event: CIObserved) -> bool:
    """Clean current CI with no publication yet authorized in this generation."""
    return event.conclusion == "success" and state.publication_operation is None


def already_published(state: ReadinessState, event: CIObserved) -> bool:
    """Clean current CI after publication was already requested."""
    del state
    return event.conclusion == "success"


def unclassified_failure(state: ReadinessState, event: CIObserved) -> bool:
    """A failure with no fingerprint has no ladder rung to spend."""
    del state
    return event.fingerprint is None


def rerun_available(state: ReadinessState, event: CIObserved) -> bool:
    """The rerun rung of this ``(lineage, fingerprint)`` budget is unspent."""
    del event
    return not state.ladder.rerun_used


def repair_available(state: ReadinessState, event: CIObserved) -> bool:
    """The repair rung of this ``(lineage, fingerprint)`` budget is unspent."""
    del event
    return not state.ladder.repair_used


# --- commits: (state, event) -> state -----------------------------------------


def keep(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Commit nothing: the observation is durably absorbed without effect."""
    del event
    return state


def advance(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Advance the evidence watermark to this observation."""
    return replace(state, ladder=replace(state.ladder, watermark=event.evidence))


def note_publication(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Advance the watermark and latch the publication operation id."""
    return replace(advance(state, event), publication_operation=publish_operation(state.head, state.generation))


def spend_rerun(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Advance the watermark and spend the rerun rung."""
    advanced = advance(state, event)
    return replace(advanced, ladder=replace(advanced.ladder, rerun_used=True))


def spend_repair(state: ReadinessState, event: CIObserved) -> ReadinessState:
    """Advance the watermark and spend the repair rung."""
    advanced = advance(state, event)
    return replace(advanced, ladder=replace(advanced.ladder, repair_used=True))


# --- emissions: (state, event) -> one routed outcome color --------------------


def request_publication(state: ReadinessState, event: CIObserved) -> PublishRequested:
    del event
    return PublishRequested(publish_operation(state.head, state.generation), state.head, state.generation)


def request_rerun(state: ReadinessState, event: CIObserved) -> RerunRequested:
    fingerprint = classified(event)
    return RerunRequested(
        rerun_operation(state.lineage, fingerprint), state.head, state.lineage, fingerprint, event.evidence
    )


def request_repair(state: ReadinessState, event: CIObserved) -> RepairRequested:
    fingerprint = classified(event)
    return RepairRequested(
        repair_operation(state.lineage, fingerprint), state.head, state.lineage, fingerprint, event.evidence
    )


def surface_human_needed(state: ReadinessState, event: CIObserved) -> HumanNeeded:
    return HumanNeeded(state.head, state.lineage, classified(event))


# --- the authored flow ---------------------------------------------------------


def readiness_flow() -> Machine[ReadinessState]:
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .match(
                "route_ci",
                normalize=refresh_ladder,
                cases=(
                    case("foreign", when=other_head, fold=keep).drop(),
                    case("stale", when=not_newer, fold=keep).drop(),
                    case("publish", when=first_clean, fold=note_publication).emit(request_publication),
                    case("published", when=already_published, fold=advance).drop(),
                    case("unclassified", when=unclassified_failure, fold=advance).drop(),
                    case("rerun", when=rerun_available, fold=spend_rerun).emit(request_rerun),
                    case("repair", when=repair_available, fold=spend_repair).emit(request_repair),
                    case("human", when=otherwise, fold=advance).emit(surface_human_needed),
                ),
            )
            .choose(
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
