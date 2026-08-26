"""Experiment-local import path for the algebraic decision-table slice.

This experiment reuses the committed typed-flow vertical slice read-only, so
both directories go on ``sys.path``: this one first (its modules are all
``table_*`` prefixed and never shadow a v1 name), then the v1 slice, whose
``domain``, ``algebra``, ``lowering``, ``source_map``, ``harness``,
``explain``, and ``scenario`` modules are imported unmodified.

The repository's root conftest and package layout are untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_V1 = _HERE.parent / "typed-flow-vertical-slice"

for _path in (str(_V1), str(_HERE)):  # inserted in reverse so _HERE ends up first
    if _path not in sys.path:
        sys.path.insert(0, _path)
