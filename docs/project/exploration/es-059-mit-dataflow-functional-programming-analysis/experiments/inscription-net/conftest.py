"""Experiment-local import path for the inscription-net variant.

Prepends this experiment directory **and** the v1 ``typed-flow-vertical-slice``
directory: every ``inet_*`` module imports its own siblings, and the source-map
sidecar and explained-History projection are reused from v1 read-only
(``algebra.SourceRef``/``CompositionError``, the whole ``source_map`` module, the
whole ``explain`` module, and ``harness.FakeProviderLedger``). No v1 file is
modified and the repository's root conftest is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_V1 = _HERE.parent / "typed-flow-vertical-slice"

for _directory in (str(_V1), str(_HERE)):
    if _directory not in sys.path:
        sys.path.insert(0, _directory)
