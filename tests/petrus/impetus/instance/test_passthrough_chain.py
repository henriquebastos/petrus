"""
Slice 1 acceptance test: replay the ``passthrough_chain`` golden trace.

The walking skeleton's outer loop — the thinnest end-to-end tracer through the
whole kernel: build the net, seed the marking, step to quiescence, and rebuild
the marking from recorded movements alone. Kept as a dedicated, narrated entry
point; the step-by-step replay contract it asserts is shared with the other
Petrus-coincident fixtures through ``harness.replay`` (see
``test_golden_replay``).
"""

from __future__ import annotations

# Internal imports
from petrus.impetus.instance import Status

# Test imports
from tests.harness import load_fixture, replay


def test_passthrough_chain_replays():
    instance = replay(load_fixture("passthrough_chain"))
    # The skeleton runs to termination: no completion condition declared, so a
    # quiescent instance collapses to the neutral TERMINATED status.
    assert instance.status is Status.TERMINATED
