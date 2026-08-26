"""Experiment-local import path for the guarded-decision-net variant (v2).

Prepends this experiment directory **and** the v1 ``typed-flow-vertical-slice``
directory so v2 modules import their own ``guarded_*`` siblings and reuse v1's
``domain``/``harness``/``source_map``/``explain``/``scenario`` modules read-only.
No v1 file is modified and the repository's root conftest is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_V1 = _HERE.parent / "typed-flow-vertical-slice"

for _directory in (str(_V1), str(_HERE)):
    if _directory not in sys.path:
        sys.path.insert(0, _directory)
