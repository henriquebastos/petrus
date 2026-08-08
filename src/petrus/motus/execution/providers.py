"""Supported Local, Docker, and E2B execution-territory providers."""

from petrus.motus._execution.providers import (
    DockerEnvironment as _DockerEnvironment,
)
from petrus.motus._execution.providers import (
    E2bEnvironment as _E2bEnvironment,
)
from petrus.motus._execution.providers import (
    LocalProcessEnvironment as _LocalProcessEnvironment,
)


class LocalProcessEnvironment(_LocalProcessEnvironment):
    """Host-local process-group territory with adapter-local lookup."""


class DockerEnvironment(_DockerEnvironment):
    """Docker container territory with provider-recreatable lookup."""


class E2bEnvironment(_E2bEnvironment):
    """E2B VM territory; the optional SDK loads only when the provider is used."""


__all__ = ["DockerEnvironment", "E2bEnvironment", "LocalProcessEnvironment"]
