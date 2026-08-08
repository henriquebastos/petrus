"""Supported Gondolin execution-territory provider."""

from petrus.motus._execution.gondolin import GondolinEnvironment as _GondolinEnvironment


class GondolinEnvironment(_GondolinEnvironment):
    """Gondolin microVM territory backed by one authenticated sidecar per lease."""


__all__ = ["GondolinEnvironment"]
