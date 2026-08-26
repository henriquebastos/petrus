"""The authored inscription net: three Activities, three latches, one ordered choice.

Read this file top to bottom and you have read the whole readiness rule. There is
no place, transition, arc, guard, token, binding, marking, or handler URI in it —
those are all derived by ``inet_lowering.py`` from the dataflow relationships
below and from the pure methods on the tokens in ``inet_tokens.py``.

Simplifications this fixture must name in source (the plan requires it):

- Full Hamsterdan V5 does not publish on CI success alone. Review, findings,
  approval, requested changes, unresolved threads, mergeability, strict base,
  mutation state, and fault state also gate publication; this fixture records
  them as pre-satisfied assumptions rather than reproducing their loops.
- Rerun, repair, and publication are fake typed Activities behind an in-memory
  idempotency ledger (see ``inet_harness.py``). They contact nothing.
- Provider moved/faulted/deferred classifications are omitted; infrastructure
  failure never becomes a business outcome.
- One readiness generation owns one head, one watermark, and one ladder budget.
  Scope reset discards all of them and the successor scoped head observation
  opens the next generation's structure — which is where the fresh budget comes
  from, structurally and for free.
- ``generation`` is V5's lifecycle incarnation; ``lineage`` separately owns
  rerun/repair budget. They are never collapsed.
- ``HeadObserved.relation`` is carried as an honest ingress fact that no code in
  this slice branches on: incarnation classification, and therefore lineage
  continuity, is the head producer's responsibility exactly as V5's ``life`` loop
  supplies it.
- Exactly one head observation is delivered per lifecycle generation — host
  discipline, not topology. A source transition can carry no guard and no input
  arc in current Petrus, so a second head in one generation would open a second
  set of structural state.
- **The ``(lineage, fingerprint)`` budget key is not modelled.** v1 re-armed the
  ladder when a failure's fingerprint changed. A latch is a black token whose
  whole content is its location, so it cannot be keyed by data; re-arming would
  need a compiler-generated refill transition conditioned on a token comparison.
  That is the sharpest point where data refused to become structure, and it is
  recorded in the report rather than contorted into the net. Within one
  generation the fixture and V5's scope-reset discipline never change the
  fingerprint, and a generation boundary re-arms both rungs structurally.
"""

from petrus.impetus.petrinet.schema import Cel
from petrus.motus.activity import activity

from inet_kernel import Flow, await_, branch, choice, effect, flow, fork, join, latch, lifecycle, otherwise
from inet_lowering import CEL_FILTERS
from inet_tokens import (
    CONVERTER,
    CIObserved,
    EvidenceWatermark,
    HeadFact,
    HeadObserved,
    HumanNeeded,
    PublicationClaim,
    Published,
    PublishRequest,
    RepairLanded,
    RepairRequest,
    RepairRung,
    RerunAccepted,
    RerunRequest,
    RerunRung,
)

# --- typed fake Activities -----------------------------------------------------
# Declarations only: these bodies never run. The harness's Dispatch binds each
# name to a ledger-backed fake; these definitions supply the typed
# request/result contract the compiler fuses into a branch's firing.


@activity(converter=CONVERTER)
def publish(request: PublishRequest) -> Published:
    raise NotImplementedError("fake Activities execute only through the harness Dispatch")


@activity(converter=CONVERTER)
def rerun(request: RerunRequest) -> RerunAccepted:
    raise NotImplementedError("fake Activities execute only through the harness Dispatch")


@activity(converter=CONVERTER)
def repair(request: RepairRequest) -> RepairLanded:
    raise NotImplementedError("fake Activities execute only through the harness Dispatch")


# --- structural state ----------------------------------------------------------
# Three latches. "What state am I in" is "where the tokens are": an unspent rung
# is a token at its place, a spent rung is an empty place, and emptiness is
# testable only by an inhibitor arc — never by a guard.

RERUN = latch("ladder.rerun", RerunRung)
REPAIR = latch("ladder.repair", RepairRung)
PUBLICATION = latch("publication.admitted", PublicationClaim)

# --- the place naming table ----------------------------------------------------
# Not a combinator: one color is one place, and this says where each one lives.

PORTS: dict[type, str] = {
    CIObserved: "events.ci",
    HeadFact: "readiness.head",
    EvidenceWatermark: "readiness.watermark",
    Published: "terminal.published",
    HumanNeeded: "terminal.human_needed",
    RerunAccepted: "facts.rerun_accepted",
    RepairLanded: "facts.repair_landed",
}

# --- the CEL probe -------------------------------------------------------------
# A Python-bound guard projects into canonical Net v3 as an anonymous
# declaration; a ``Cel`` arc filter projects as its expression, so it is the one
# authored predicate whose *meaning* survives into the interchange bytes. Only
# ``is_clean`` reaches: see the report for what the CEL vocabulary refused.

CEL_FILTERS[CIObserved.is_clean] = Cel('conclusion == "success"')


def readiness_flow() -> Flow:
    head = await_(
        "head",
        HeadObserved,
        seeds=fork(
            "open_generation",
            HeadObserved.as_head_fact,
            HeadObserved.unseen_watermark,
            fills=(RERUN, REPAIR),
        ),
    )
    ci = await_("ci", CIObserved)
    observation = join(ci, reads=(HeadFact,), folds=(EvidenceWatermark,))

    return flow(
        "readiness",
        lifecycle=lifecycle("branch"),
        ports=PORTS,
        latches=(RERUN, REPAIR, PUBLICATION),
        joins=(observation,),
        nodes=(
            head,
            ci
            >> choice(
                "decide",
                branch("foreign", when=CIObserved.is_for_another_head),
                branch("stale", when=CIObserved.is_not_newer_than),
                branch(
                    "publish",
                    when=CIObserved.is_clean,
                    without=(PUBLICATION,),
                    fills=(PUBLICATION,),
                    folds=(CIObserved.watermark,),
                    effect=effect("publish", publish, request=CIObserved.publish_request),
                ),
                branch(
                    "republished",
                    when=CIObserved.is_clean,
                    takes=(PUBLICATION,),
                    fills=(PUBLICATION,),
                    folds=(CIObserved.watermark,),
                ),
                branch(
                    "rerun",
                    when=CIObserved.is_classified_failure,
                    takes=(RERUN,),
                    folds=(CIObserved.watermark,),
                    effect=effect("rerun", rerun, request=CIObserved.rerun_request),
                ),
                branch(
                    "repair",
                    when=CIObserved.is_classified_failure,
                    takes=(REPAIR,),
                    without=(RERUN,),
                    folds=(CIObserved.watermark,),
                    effect=effect("repair", repair, request=CIObserved.repair_request),
                ),
                branch(
                    "human",
                    when=CIObserved.is_classified_failure,
                    without=(RERUN, REPAIR),
                    folds=(CIObserved.watermark,),
                    emits=(CIObserved.human_needed,),
                ),
                otherwise("unclassified", folds=(CIObserved.watermark,)),
            ),
        ),
    )
