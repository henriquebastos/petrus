"""Spawn ports and the ``process.spawn`` activity implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from petrus.fabric import Endpoint
from petrus.fabric.model import _json_object, _text
from petrus.motus.activity import ActivityInvocation
from petrus.processes.model import Lineage, Provisioning, SpawnClaim, SpawnOutcome, SpawnSpec, child_identity

SPAWN_ACTIVITY = "process.spawn"


class SpawnRegistry(Protocol):
    def claim(self, spec: SpawnSpec) -> SpawnClaim: ...
    def child_of(self, parent: str, spawn_id: str) -> Lineage | None: ...
    def children_of(self, parent: str) -> tuple[Lineage, ...]: ...
    def parent_of(self, child: str) -> Lineage | None: ...


class ProcessProvisioner(Protocol):
    def ensure(self, provisioning: Provisioning) -> None: ...


@dataclass(frozen=True)
class SpawnActivity:
    registry: SpawnRegistry
    provisioner: ProcessProvisioner

    def __call__(self, invocation: ActivityInvocation, *, context) -> dict[str, object]:
        if not isinstance(invocation, ActivityInvocation) or invocation.activity != SPAWN_ACTIVITY:
            raise ValueError("SpawnActivity only implements 'process.spawn'")
        spec = SpawnSpec.from_data(invocation.input)
        expected_idempotency = spawn_idempotency(spec.parent, spec.spawn_id)
        if invocation.idempotency != expected_idempotency:
            raise ValueError("process.spawn idempotency must identify the parent and spawn_id")
        claim = self.registry.claim(spec)
        if not isinstance(claim, SpawnClaim):
            raise TypeError("spawn registry must return SpawnClaim")
        if (claim.parent, claim.spawn_id, claim.child) != (spec.parent, spec.spawn_id, spec.child):
            raise ValueError("spawn registry returned a claim for a different identity")
        capabilities = _json_object(spec.to_data()["capabilities"], "capabilities")
        endpoint = Endpoint(claim.child, spec.source, capabilities)
        provisioning = Provisioning(
            spec.parent,
            spec.spawn_id,
            claim.child,
            spec.process_kind,
            endpoint,
            spec.config,
            spec.reply_route,
        )
        ensured = self.provisioner.ensure(provisioning)
        if ensured is not None:
            raise TypeError("process provisioner ensure must return None, never a live host or credential")
        return SpawnOutcome(spec.parent, spec.spawn_id, claim.child, endpoint, claim.prior_claim).to_data()


def spawn_idempotency(parent: str, spawn_id: str) -> str:
    parent, spawn_id = _text(parent, "parent"), _text(spawn_id, "spawn_id")
    return f"process.spawn:{child_identity(parent, spawn_id)}"
