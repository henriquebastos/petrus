"""Host-supplied key operations for opaque Agent Connection state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class KeyOperationError(RuntimeError):
    """A host key operation failed without exposing key or plaintext material."""


@dataclass(frozen=True)
class KeyContext:
    """Nonsecret authenticated context for one encrypted state version."""

    connection_id: str
    authority_epoch: int
    state_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.connection_id, str) or not self.connection_id:
            raise ValueError("key context connection identity must not be empty")
        if type(self.authority_epoch) is not int or self.authority_epoch <= 0:
            raise ValueError("key context authority epoch must be a positive integer")
        if type(self.state_version) is not int or self.state_version <= 0:
            raise ValueError("key context state version must be a positive integer")

    def authenticated_data(self) -> bytes:
        return (
            f"petrus-agenticus-connection/v1\0{self.connection_id}\0{self.authority_epoch}\0{self.state_version}"
        ).encode()


@dataclass(frozen=True)
class KeyErasureEvidence:
    """Secret-free host evidence that a connection's decrypting key was erased."""

    connection_id: str
    erased: bool

    def __post_init__(self) -> None:
        if not self.connection_id:
            raise ValueError("key erasure connection identity must not be empty")
        if self.erased is not True:
            raise ValueError("key erasure evidence must affirm completed erasure")


class KeyOperations(Protocol):
    """Pluggable host boundary that never hands key material to Agenticus."""

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        """Encrypt and authenticate one opaque state buffer."""
        ...

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        """Return one erasable plaintext buffer after integrity verification."""
        ...

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        """Cryptographically erase authority for every retained ciphertext."""
        ...
