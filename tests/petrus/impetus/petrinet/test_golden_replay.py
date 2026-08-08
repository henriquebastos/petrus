"""
Golden-trace replay for the Petrus-coincident fixtures.

These fixtures record Petrus oracle behavior that the ratified Impetus semantics
reproduce exactly — a single token per firing through a single output arc, with
no merge. They are the regression anchor for cross-implementation agreement. The
Impetus contract itself — including the ``arc_weights`` and ``read_arc``
divergences, where per-token forwarding departs from the oracle's merge — is
carried by the Impetus-native tests, not by oracle replay. See
``spec/traces/README.md``.

``passthrough_chain`` keeps its own narrated file (``test_passthrough_chain``) as
the slice-1 walking-skeleton acceptance; it shares this file's replay driver.
"""

from __future__ import annotations

# Python imports
import pytest

# Test imports
from tests.harness import load_fixture, replay

# The Petrus-coincident fixtures that replay. `passthrough_chain` keeps its own
# narrated file (`test_passthrough_chain`). `guard_branch` left this list when
# multi-binding enumeration landed (debt 2026-07-09T2110Z paid): the oracle
# evaluates guards over the FIFO head selection only, so its recorded enabled
# sets under-report the ratified per-binding skip — the Impetus-native
# `test_guard_branch.py` carries that net's contract, walk included.
COINCIDENT = ["fifo_queue", "inhibitor_arc", "conflict_selection"]


@pytest.mark.parametrize("name", COINCIDENT)
def test_coincident_fixture_replays(name: str):
    replay(load_fixture(name))
