"""Narrated walking-skeleton replay of the Impetus-native passthrough trace."""

from __future__ import annotations

# Internal imports
from petrus.impetus.instance import Status

# Test imports
from tests.harness import load_fixture, replay


def test_passthrough_chain_replays():
    instance = replay(load_fixture("passthrough_chain"))
    assert instance.status is Status.TERMINATED
