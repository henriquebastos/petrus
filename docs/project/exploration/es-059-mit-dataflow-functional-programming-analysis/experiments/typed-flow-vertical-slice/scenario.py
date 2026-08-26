"""The authored readiness flow: pure domain functions, typed Activities, and the flow value.

Simplifications the experiment plan requires naming in source:

- Full Hamsterdan V5 does not publish on CI success alone — review, findings,
  approval, requested changes, unresolved threads, mergeability, strict base,
  mutation state, and fault state also gate publication. This fixture records
  those gates as pre-satisfied assumptions rather than reproducing their loops.
- Rerun, repair, and publication are fake typed Activities backed by an
  in-memory idempotency ledger (see ``harness.py``); they contact nothing.
- Provider moved/faulted/deferred classifications are omitted; infrastructure
  failure is never converted into a business outcome.
- One readiness state baton exists per lifecycle generation; scope reset
  discards it and the successor scoped head observation seeds the next one.
- ``generation`` is V5's lifecycle incarnation; ``lineage`` separately owns
  rerun/repair budget. They are never collapsed.
- A failure without a fingerprint is absorbed as ``Ignored``: the fixture's
  ladder is keyed by ``(lineage, fingerprint)`` and an unclassified failure
  has no rung to spend.
- Exactly one head observation is delivered per lifecycle generation — host
  discipline, not topology. ``ingress.head`` produces into ``readiness.state``
  unguarded (a source transition cannot carry guards or input arcs in current
  Petrus), so a second head in one generation would seed a second state baton.
  V5 answers branch movement with a scope reset, which this fixture models.
- ``HeadObserved.relation`` is carried as an honest ingress fact but no code
  in this slice branches on it: incarnation classification (confirmed vs
  unrelated) and therefore lineage continuity are the head producer's
  responsibility, exactly as V5's ``life`` loop supplies them.
- An ``Ignored`` decision is durably visible only as a state-reproducing
  firing with no command token; its ``reason`` never enters History.
"""

from dataclasses import replace

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import Token
from petrus.motus.activity import activity

from algebra import (
    Decision,
    Machine,
    await_event,
    drop,
    effect,
    lifecycle,
    low_level,
    machine,
    on,
    terminal,
)
from domain import (
    CIObserved,
    DomainConverter,
    Evidence,
    HeadObserved,
    HumanNeeded,
    Ignored,
    Ladder,
    PublishAcknowledged,
    Published,
    PublishRequested,
    ReadinessState,
    RepairLanded,
    RepairRequested,
    RerunAccepted,
    RerunRequested,
)
from lowering import FragmentContext, FragmentPorts

# --- ordinary helper calculations --------------------------------------------
# These are called from the pure decisions below and MUST remain ordinary code:
# they create no transitions and no History rows (the lowering tests pin the
# exact topology, so a helper that grew a node would fail there).


def publish_operation(head: str, generation: int) -> str:
    return f"publish:{head}:g{generation}"


def rerun_operation(lineage: str, fingerprint: str) -> str:
    return f"rerun:{lineage}:{fingerprint}"


def repair_operation(lineage: str, fingerprint: str) -> str:
    return f"repair:{lineage}:{fingerprint}"


def evidence_key(evidence: Evidence) -> tuple[int, int]:
    """CI evidence identity ordering: lexicographic ``(run_id, attempt)``."""
    return (evidence.run_id, evidence.attempt)


def is_newer(candidate: Evidence, watermark: Evidence | None) -> bool:
    return watermark is None or evidence_key(candidate) > evidence_key(watermark)


def retry_key(lineage: str, fingerprint: str) -> tuple[str, str]:
    """Rerun/repair budget is keyed by ``(lineage, fingerprint)``, never fingerprint alone."""
    return (lineage, fingerprint)


# --- pure domain functions ----------------------------------------------------


def admit_head(event: HeadObserved) -> ReadinessState:
    """Seed the successor generation from an explicit head/lineage fact."""
    return ReadinessState(
        head=event.head,
        generation=event.generation,
        lineage=event.lineage,
        ladder=Ladder(
            lineage=event.lineage,
            fingerprint=None,
            rerun_used=False,
            repair_used=False,
            watermark=None,
        ),
        publication_operation=None,
    )


def route_ci(
    state: ReadinessState,
    event: CIObserved,
) -> Decision[
    ReadinessState,
    PublishRequested | RerunRequested | RepairRequested | HumanNeeded | Ignored,
]:
    """Update the state baton and choose exactly one domain outcome."""
    if event.head != state.head:
        return Decision(state, Ignored("evidence for another head"))
    if not is_newer(event.evidence, state.ladder.watermark):
        return Decision(state, Ignored("evidence is not newer than the watermark"))

    if event.conclusion == "success":
        advanced = replace(state, ladder=replace(state.ladder, watermark=event.evidence))
        if state.publication_operation is not None:
            return Decision(advanced, Ignored("publication already requested"))
        operation = publish_operation(state.head, state.generation)
        return Decision(
            replace(advanced, publication_operation=operation),
            PublishRequested(operation, state.head, state.generation),
        )

    if event.fingerprint is None:
        advanced = replace(state, ladder=replace(state.ladder, watermark=event.evidence))
        return Decision(advanced, Ignored("failure without a fingerprint has no ladder rung"))

    fingerprint = event.fingerprint
    ladder = state.ladder
    if ladder.fingerprint is None or retry_key(state.lineage, fingerprint) != retry_key(
        ladder.lineage, ladder.fingerprint
    ):
        ladder = Ladder(state.lineage, fingerprint, False, False, event.evidence)
    else:
        ladder = replace(ladder, watermark=event.evidence)

    if not ladder.rerun_used:
        return Decision(
            replace(state, ladder=replace(ladder, rerun_used=True)),
            RerunRequested(
                rerun_operation(state.lineage, fingerprint),
                state.head,
                state.lineage,
                fingerprint,
                event.evidence,
            ),
        )
    if not ladder.repair_used:
        return Decision(
            replace(state, ladder=replace(ladder, repair_used=True)),
            RepairRequested(
                repair_operation(state.lineage, fingerprint),
                state.head,
                state.lineage,
                fingerprint,
                event.evidence,
            ),
        )
    return Decision(
        replace(state, ladder=ladder),
        HumanNeeded(state.head, state.lineage, fingerprint),
    )


def accept_publish(
    state: ReadinessState,
    event: PublishAcknowledged,
) -> tuple[ReadinessState, Published]:
    """Record publication only after the effect terminal is accepted."""
    return (
        replace(state, publication_operation=event.operation),
        Published(event.head, event.generation, event.operation),
    )


# --- typed fake Activities -----------------------------------------------------
# Declarations only: the bodies below never run. The harness's Dispatch binds
# each name to a ledger-backed fake; these definitions supply the typed
# request/result contract the compiler derives arcs and handlers from.


@activity(converter=DomainConverter())
def rerun(request: RerunRequested) -> RerunAccepted:
    raise NotImplementedError("fake Activities execute only through the harness Dispatch")


@activity(converter=DomainConverter())
def repair(request: RepairRequested) -> RepairLanded:
    raise NotImplementedError("fake Activities execute only through the harness Dispatch")


@activity(converter=DomainConverter())
def publish(request: PublishRequested) -> PublishAcknowledged:
    raise NotImplementedError("fake Activities execute only through the harness Dispatch")


# --- deliberate low-level descent ---------------------------------------------


def publication_gate(gate: FragmentContext) -> FragmentPorts:
    """One-at-a-time publication admission; the inhibitor is why this descends.

    ``pending`` inhibits authorization while a publication is in flight and
    ``done`` latches the generation closed after acceptance, so even a
    misbehaving upstream cannot admit two publications concurrently or
    serially within one generation. The typed algebra has no vocabulary for
    absence, which is exactly what the inhibitor arc expresses.
    """
    pending = gate.place("pending", role="publication in-flight latch")
    done = gate.place("done", role="publication completed latch")
    work = gate.place("work", color=gate.input_type, role="authorized publication work")
    ack = gate.place("ack", color=gate.returns, role="publication effect terminal")

    def authorize_publication(binding, outputs):
        del outputs
        [(_, (request,))] = binding.consumed
        return {work: (request,), pending: (Token.black(),)}

    def accept_acknowledgement(binding, outputs):
        del outputs
        (_, _pending), (_, (acknowledged,)) = binding.consumed
        return {gate.output: (acknowledged,), done: (Token.black(),)}

    authorize = gate.transition(
        "authorize",
        petri_handler(authorize_publication),
        role="admit one publication while none is pending or done",
    )
    execute = gate.activity_transition("execute", publish, role="publication effect request/observe")
    accept = gate.transition(
        "accept",
        petri_handler(accept_acknowledgement),
        role="accept effect terminal, release pending, latch done",
    )

    gate.consume(gate.input, authorize)
    gate.inhibit(pending, authorize)
    gate.inhibit(done, authorize)
    gate.produce(authorize, work)
    gate.produce(authorize, pending)
    gate.consume(work, execute)
    gate.produce(execute, ack)
    gate.consume(pending, accept)
    gate.consume(ack, accept)
    gate.produce(accept, gate.output)
    gate.produce(accept, done)

    return FragmentPorts(input=gate.input, output=gate.output)


# --- the authored flow ---------------------------------------------------------


def readiness_flow() -> Machine[ReadinessState]:
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .decide("route_ci", route_ci)
            .choose(
                {
                    PublishRequested: low_level(
                        "publish_once",
                        publication_gate,
                        returns=PublishAcknowledged,
                    ),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                    Ignored: drop(),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )
