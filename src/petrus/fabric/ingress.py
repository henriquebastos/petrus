"""Kernel ingress bridge for Fabric deliveries."""

from __future__ import annotations

# Python imports
from dataclasses import dataclass, field
from typing import Protocol

# Internal imports
from petrus.fabric.model import Envelope, Receipt
from petrus.impetus.instance import FiringOutcome
from petrus.impetus.petrinet import Token
from petrus.impetus.instance import PriorAcknowledgement

FABRIC_ENVELOPE = "FabricEnvelope"


class DeliveryDoor(Protocol):
    def deliver(
        self, source: str, tokens: tuple[Token, ...], *, identity: str
    ) -> FiringOutcome | PriorAcknowledgement: ...


class InboxClient(Protocol):
    def pending(self, limit: int = 100) -> tuple[Envelope, ...]: ...

    def acknowledge(self, sender: str, delivery_id: str, occurrence: int) -> Receipt: ...


@dataclass(frozen=True)
class FabricInbox:
    client: InboxClient
    delivery_door: DeliveryDoor = field(repr=False)

    def drain(self, limit: int = 100) -> tuple[Receipt, ...]:
        receipts = []
        for envelope in self.client.pending(limit):
            result = self.delivery_door.deliver(
                envelope.source,
                (Token(FABRIC_ENVELOPE, envelope.to_data()),),
                identity=envelope.ingress_identity,
            )
            if not isinstance(result, (FiringOutcome, PriorAcknowledgement)):
                raise TypeError("delivery door must return FiringOutcome or PriorAcknowledgement")
            receipts.append(self.client.acknowledge(envelope.sender, envelope.delivery_id, result.occurrence))
        return tuple(receipts)
