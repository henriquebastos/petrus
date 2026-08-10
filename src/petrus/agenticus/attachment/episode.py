"""Episode Attachment: a distinct Agenticus lifecycle over bound territory.

An :class:`EpisodeAttachment` binds one exact DS3 ``EpisodeId``, one immutable
DS5 ``ResolutionSnapshot`` with selected Hands and Territory descriptors, one
current :class:`~petrus.agenticus.attachment.binding.AttachmentBinding`, an
Agenticus attachment identity with a positive epoch, a finite deadline,
cancellation, and per-epoch capability grants. It is not a Thread, workspace,
territory, Agent Home, provider session, transcript, or History, and it never
settles the DS3 Thread or Episode lifecycle itself — it only exposes evidence
the host consumes.

Hands calls and attachment transition share one barrier: settlement closes
admission under the barrier, drains current calls, discards every stage,
exports one bounded archive, and only then consumes binding settlement.
A successor is a distinct Episode Attachment and may be constructed only after
cleanup is independently verified; unverified cleanup leaves fail-closed
uncertain custody that blocks completion and succession until a retry verifies.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol

from petrus.agenticus.attachment.binding import (
    AttachmentBinding,
    AttachmentCoordinates,
    BindingSettlement,
    MotusAttachmentBinding,
)
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import AttachmentFence
from petrus.agenticus.hands.gateway import CallFence, HandsAdapter, HandsGateway, ResultAdmission, TargetCurrency
from petrus.agenticus.hands.grants import GrantLedger
from petrus.agenticus.thread.identity import EpisodeId
from petrus.motus.execution.archive import MAX_WORKSPACE_ARCHIVE_BYTES
from petrus.motus.execution import LeaseIdentity

_MAX_IDENTITY_BYTES = 256


class EpisodeAttachmentError(RuntimeError):
    """An attachment lifecycle operation violated its ordered contract."""


class UncertainCustodyError(EpisodeAttachmentError):
    """Cleanup is unverified; custody is uncertain and progress is blocked."""


class ConnectionAdmissionSource(Protocol):
    """The DS2 admission seam: a fenced custody reference, never key material."""

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> object: ...


class CustodyResultAdmission:
    """Result admission through one exact DS2 attachment fence.

    A stale, revoked, or removed connection fence makes admission return
    ``False``, which the gateway renders as the safe ``authority`` category.
    """

    def __init__(self, custody: ConnectionAdmissionSource, fence: AttachmentFence) -> None:
        if not isinstance(fence, AttachmentFence):
            raise TypeError("custody admission fence must be AttachmentFence")
        self._custody = custody
        self._fence = fence

    def admit(self, call_id: str) -> bool:
        try:
            self._custody.admit_result(self._fence, operation_id=call_id)
        except Exception:
            return False
        return True


@dataclass(frozen=True)
class AttachmentSettlement:
    """Evidence of one ordered epoch settlement for the host to consume."""

    attachment_id: str
    epoch: int
    stages_discarded: int
    archive: bytes = field(repr=False)
    archive_digest: str
    settlement: BindingSettlement

    def __post_init__(self) -> None:
        if type(self.epoch) is not int or self.epoch <= 0:
            raise ValueError("settlement epoch must be a positive integer")
        if type(self.stages_discarded) is not int or self.stages_discarded < 0:
            raise ValueError("settlement stages_discarded must be a non-negative integer")
        if not isinstance(self.archive, bytes):
            raise TypeError("settlement archive must be bytes")
        if self.archive_digest != hashlib.sha256(self.archive).hexdigest():
            raise ValueError("settlement archive digest must match the exported archive")
        if not isinstance(self.settlement, BindingSettlement):
            raise TypeError("settlement evidence must be BindingSettlement")


@dataclass(frozen=True)
class AttachmentRelease:
    """Evidence that one closed Attachment transferred an exact lease to its host."""

    attachment_id: str
    epoch: int
    stages_discarded: int
    archive: bytes = field(repr=False)
    archive_digest: str
    territory: LeaseIdentity

    def __post_init__(self) -> None:
        if type(self.epoch) is not int or self.epoch <= 0:
            raise ValueError("release epoch must be a positive integer")
        if type(self.stages_discarded) is not int or self.stages_discarded < 0:
            raise ValueError("release stages_discarded must be a non-negative integer")
        if not isinstance(self.archive, bytes):
            raise TypeError("release archive must be bytes")
        if self.archive_digest != hashlib.sha256(self.archive).hexdigest():
            raise ValueError("release archive digest must match the exported archive")
        if not isinstance(self.territory, LeaseIdentity):
            raise TypeError("release territory must be an exact LeaseIdentity")


class _ReleaseAdmission(Protocol):
    def _accept_release(
        self,
        binding: MotusAttachmentBinding,
        coordinates: AttachmentCoordinates,
        stages_discarded: int,
        archive: bytes,
    ) -> LeaseIdentity: ...


class _EpochFence:
    """The call fence for one exact attachment epoch; stale epochs read closed."""

    def __init__(self, attachment: EpisodeAttachment, epoch: int) -> None:
        self._attachment = attachment
        self._epoch = epoch

    def snapshot(self) -> CallFence:
        return self._attachment._fence_snapshot(self._epoch)


class EpisodeAttachment:
    """One Agenticus Episode bound to one attachment identity and territory.

    A verified settled attachment may construct a distinct successor Episode
    attachment at the next epoch. The old attachment remains settled and no
    grant, gateway, cancellation state, or territory crosses that boundary.
    """

    def __init__(
        self,
        *,
        episode_id: EpisodeId,
        snapshot: ResolutionSnapshot,
        binding: AttachmentBinding,
        attachment_id: str,
        deadline: float,
        attachment_epoch: int = 1,
        admission: ResultAdmission | None = None,
        target: TargetCurrency | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(episode_id, EpisodeId):
            raise TypeError("episode attachment requires an exact EpisodeId")
        if not isinstance(snapshot, ResolutionSnapshot):
            raise TypeError("episode attachment requires an immutable ResolutionSnapshot")
        hands = snapshot.descriptor(DescriptorKind.HANDS)
        territory = snapshot.descriptor(DescriptorKind.TERRITORY)
        if hands is None or territory is None:
            raise ValueError("resolution snapshot must select Hands and Territory descriptors")
        if (
            not isinstance(attachment_id, str)
            or not attachment_id
            or attachment_id != attachment_id.strip()
            or len(attachment_id.encode()) > _MAX_IDENTITY_BYTES
            or any(ord(character) < 32 for character in attachment_id)
        ):
            raise ValueError("attachment_id must be a bounded non-empty identity string")
        if isinstance(deadline, bool) or not isinstance(deadline, int | float) or not math.isfinite(deadline):
            raise ValueError("episode attachment deadline must be a finite number")
        if type(attachment_epoch) is not int or attachment_epoch <= 0:
            raise ValueError("episode attachment epoch must be a positive integer")
        if not isinstance(binding.binding_kind, str) or not binding.binding_kind:
            raise TypeError("episode attachment binding must implement the binding protocol")
        if any(not callable(getattr(binding, method, None)) for method in ("cancel", "export_archive", "settle")):
            raise TypeError("episode attachment binding must implement the binding protocol")
        try:
            BindingSettlement(binding.binding_kind, "unverified", False)
        except (TypeError, ValueError) as error:
            raise TypeError("episode attachment binding kind must satisfy the binding protocol") from error
        self._episode_id = episode_id
        self._snapshot = snapshot
        self._hands_descriptor = hands
        self._territory_descriptor = territory
        self._binding = binding
        self._attachment_id = attachment_id
        self._deadline = float(deadline)
        self._admission = admission
        self._target = target
        self._clock = clock
        self._barrier = RLock()
        self._epoch = attachment_epoch
        self._ledger = GrantLedger(attachment_id, attachment_epoch)
        self._gateways: list[HandsGateway] = []
        self._open = True
        self._aborted = False
        self._cancelled = False
        self._settlement: AttachmentSettlement | None = None
        self._release: AttachmentRelease | None = None
        self._uncertain = False
        self._settling = False

    @property
    def episode_id(self) -> EpisodeId:
        return self._episode_id

    @property
    def snapshot(self) -> ResolutionSnapshot:
        return self._snapshot

    @property
    def hands_descriptor(self) -> CapabilityDescriptor:
        return self._hands_descriptor

    @property
    def territory_descriptor(self) -> CapabilityDescriptor:
        return self._territory_descriptor

    @property
    def attachment_id(self) -> str:
        return self._attachment_id

    @property
    def epoch(self) -> int:
        with self._barrier:
            return self._epoch

    @property
    def binding(self) -> AttachmentBinding:
        with self._barrier:
            return self._binding

    @property
    def barrier(self) -> RLock:
        """The one barrier Hands calls and attachment transition share."""

        return self._barrier

    @property
    def deadline(self) -> float:
        return self._deadline

    @property
    def custody_uncertain(self) -> bool:
        with self._barrier:
            return self._uncertain

    @property
    def settled(self) -> bool:
        """Whether the current epoch has independently verified settlement."""

        with self._barrier:
            return self._settlement is not None and self._settlement.settlement.verified

    @property
    def last_settlement(self) -> AttachmentSettlement | None:
        with self._barrier:
            return self._settlement

    def coordinates(self) -> AttachmentCoordinates:
        """The current DS7-consumable Episode/attachment coordinates."""

        with self._barrier:
            return AttachmentCoordinates(
                episode_id=self._episode_id.value,
                attachment_id=self._attachment_id,
                attachment_epoch=self._epoch,
            )

    def grants(self) -> GrantLedger:
        """The current epoch's grant ledger; grants never survive replacement."""

        with self._barrier:
            return self._ledger

    def gateway(self, adapter: HandsAdapter, *, max_evidence: int = 256) -> HandsGateway:
        """Open one Hands gateway bound to the current epoch and shared barrier."""

        with self._barrier:
            if self._uncertain:
                raise UncertainCustodyError("uncertain custody blocks new gateways")
            if not self._open:
                raise EpisodeAttachmentError("attachment admission is closed")
            gateway = HandsGateway(
                episode_id=self._episode_id.value,
                adapter=adapter,
                grants=self._ledger,
                fence=_EpochFence(self, self._epoch),
                barrier=self._barrier,
                admission=self._admission,
                target=self._target,
                clock=self._clock,
                max_evidence=max_evidence,
            )
            self._gateways.append(gateway)
            return gateway

    def cancel(self, reason: str) -> None:
        """Abort current calls fail-closed and cancel the bound territory."""

        with self._barrier:
            if self._settling:
                raise EpisodeAttachmentError("attachment settlement is already in progress")
            if self._settlement is not None or not self._open:
                raise EpisodeAttachmentError("attachment is already settled")
            if self._cancelled:
                return
            self._aborted = True
            try:
                self._binding.cancel(reason)
            except Exception:
                raise EpisodeAttachmentError("attachment cancellation failed") from None
            self._cancelled = True

    def settle(self, *, drain_timeout: float = 30.0) -> AttachmentSettlement:
        """Run the ordered transition for the current epoch and consume evidence.

        Order: close admission, drain current calls, discard every stage,
        export one bounded workspace archive, destroy the bound territory, and
        consume its settlement. An unverified settlement leaves fail-closed
        uncertain custody; it does not raise, because the evidence itself is
        what the host must consume.
        """

        with self._barrier:
            if self._uncertain:
                raise UncertainCustodyError("retry settlement instead of settling again")
            if self._settlement is not None or self._release is not None:
                raise EpisodeAttachmentError("attachment epoch is already settled")
            if self._settling:
                raise EpisodeAttachmentError("attachment settlement is already in progress")
            self._settling = True
            self._open = False
            gateways = tuple(self._gateways)
        try:
            for gateway in gateways:
                if not gateway.drain(drain_timeout):
                    raise EpisodeAttachmentError("current calls did not drain before settlement")
            stages = sum(gateway.cleanup_stages() for gateway in gateways)
            archive = self._binding.export_archive()
            if not isinstance(archive, bytes):
                raise TypeError("attachment binding archive must be bytes")
            if len(archive) > MAX_WORKSPACE_ARCHIVE_BYTES:
                raise EpisodeAttachmentError("attachment archive exceeds the public Motus workspace archive bound")
            try:
                settlement = self._binding.settle()
                if not isinstance(settlement, BindingSettlement):
                    raise TypeError("attachment binding settle must return BindingSettlement")
                settlement = BindingSettlement(
                    settlement.binding_kind,
                    settlement.disposition,
                    settlement.verified,
                )
            except Exception:
                settlement = BindingSettlement(
                    self._binding.binding_kind,
                    "unverified",
                    False,
                    "binding settlement failed",
                )
                record = self._record_settlement(stages, archive, settlement)
                with self._barrier:
                    self._ledger.close()
                    self._settlement = record
                    self._uncertain = True
                raise EpisodeAttachmentError("attachment binding settlement failed") from None
            record = self._record_settlement(stages, archive, settlement)
            with self._barrier:
                self._ledger.close()
                self._settlement = record
                self._uncertain = not settlement.verified
            return record
        finally:
            with self._barrier:
                self._settling = False

    def _release_to(  # noqa: C901 - release ordering and fail-closed transition stay in one barrier owner
        self, admission: _ReleaseAdmission, *, drain_timeout: float = 30.0
    ) -> AttachmentRelease:
        """Close this Attachment and transfer its exact Motus lease to durable host custody."""

        if not callable(getattr(admission, "_accept_release", None)):
            raise TypeError("attachment release requires host custody admission")
        with self._barrier:
            if self._uncertain:
                raise UncertainCustodyError("uncertain custody blocks attachment release")
            if self._settlement is not None or self._release is not None or not self._open:
                raise EpisodeAttachmentError("attachment is already settled or released")
            if self._settling:
                raise EpisodeAttachmentError("attachment settlement is already in progress")
            if not isinstance(self._binding, MotusAttachmentBinding):
                raise EpisodeAttachmentError("retained custody currently requires an exact Motus binding")
            self._settling = True
            self._open = False
            gateways = tuple(self._gateways)
            binding = self._binding
            coordinates = self.coordinates()
        try:
            if not binding._quiesce(drain_timeout):  # noqa: SLF001 - host release owns this private binding transition
                raise EpisodeAttachmentError("runtime operations did not drain before release")
            for gateway in gateways:
                if not gateway.drain(drain_timeout):
                    raise EpisodeAttachmentError("current calls did not drain before release")
            stages = sum(gateway.cleanup_stages() for gateway in gateways)
            archive = binding.export_archive()
            if not isinstance(archive, bytes):
                raise TypeError("attachment binding archive must be bytes")
            if len(archive) > MAX_WORKSPACE_ARCHIVE_BYTES:
                raise EpisodeAttachmentError("attachment archive exceeds the public Motus workspace archive bound")
            territory = admission._accept_release(binding, coordinates, stages, archive)
            if territory != binding.lease_identity:
                raise EpisodeAttachmentError("host custody accepted a different territory identity")
            record = AttachmentRelease(
                self._attachment_id,
                self._epoch,
                stages,
                archive,
                hashlib.sha256(archive).hexdigest(),
                territory,
            )
            with self._barrier:
                self._ledger.close()
                self._release = record
            return record
        except Exception:
            with self._barrier:
                self._ledger.close()
                self._uncertain = True
            raise EpisodeAttachmentError("attachment release to host custody failed") from None
        finally:
            with self._barrier:
                self._settling = False

    def retry_settlement(self) -> AttachmentSettlement:
        """Retry only the destroy/consume step of an uncertain settlement."""

        with self._barrier:
            record = self._settlement
            if record is None or not self._uncertain:
                raise EpisodeAttachmentError("retry requires a prior unverified settlement")
            if self._settling:
                raise EpisodeAttachmentError("attachment settlement is already in progress")
            self._settling = True
        try:
            try:
                settlement = self._binding.settle()
                if not isinstance(settlement, BindingSettlement):
                    raise TypeError("attachment binding settle must return BindingSettlement")
                settlement = BindingSettlement(
                    settlement.binding_kind,
                    settlement.disposition,
                    settlement.verified,
                )
            except Exception:
                settlement = BindingSettlement(
                    self._binding.binding_kind,
                    "unverified",
                    False,
                    "binding settlement failed",
                )
                updated = self._record_settlement(record.stages_discarded, record.archive, settlement)
                with self._barrier:
                    self._settlement = updated
                    self._uncertain = True
                raise EpisodeAttachmentError("attachment binding settlement failed") from None
            updated = self._record_settlement(record.stages_discarded, record.archive, settlement)
            with self._barrier:
                self._settlement = updated
                self._uncertain = not settlement.verified
            return updated
        finally:
            with self._barrier:
                self._settling = False

    def successor(
        self,
        *,
        episode_id: EpisodeId,
        snapshot: ResolutionSnapshot,
        binding: AttachmentBinding,
        attachment_id: str,
        deadline: float,
        admission: ResultAdmission | None = None,
        target: TargetCurrency | None = None,
    ) -> EpisodeAttachment:
        """Construct a new Episode attachment after this one settles.

        Thread lineage cannot be proven here: the DS3 host owns the assertion
        that both distinct Episodes belong to the same Thread.
        """

        with self._barrier:
            if self._uncertain:
                raise UncertainCustodyError("unverified cleanup blocks attachment succession")
            record = self._settlement
            if self._open or record is None or not record.settlement.verified:
                raise EpisodeAttachmentError("succession requires verified settlement of the prior attachment")
            if not isinstance(episode_id, EpisodeId) or episode_id == self._episode_id:
                raise EpisodeAttachmentError("successor requires a different EpisodeId")
            if attachment_id == self._attachment_id:
                raise EpisodeAttachmentError("successor requires a different attachment_id")
            epoch = self._epoch + 1
        return EpisodeAttachment(
            episode_id=episode_id,
            snapshot=snapshot,
            binding=binding,
            attachment_id=attachment_id,
            attachment_epoch=epoch,
            deadline=deadline,
            admission=admission,
            target=target,
            clock=self._clock,
        )

    def _fence_snapshot(self, epoch: int) -> CallFence:
        with self._barrier:
            current = self._epoch == epoch and self._open and not self._uncertain
            return CallFence(open=current, aborted=self._aborted, deadline=self._deadline)

    def _record_settlement(
        self,
        stages_discarded: int,
        archive: bytes,
        settlement: BindingSettlement,
    ) -> AttachmentSettlement:
        return AttachmentSettlement(
            attachment_id=self._attachment_id,
            epoch=self._epoch,
            stages_discarded=stages_discarded,
            archive=archive,
            archive_digest=hashlib.sha256(archive).hexdigest(),
            settlement=settlement,
        )


__all__ = [
    "AttachmentSettlement",
    "ConnectionAdmissionSource",
    "CustodyResultAdmission",
    "EpisodeAttachment",
    "EpisodeAttachmentError",
    "UncertainCustodyError",
]
