"""Experiment-local import path, following the retained Hamsterdan AX29 precedent.

Prepends only this experiment directory so its tests import sibling modules;
the repository's root conftest and package layout are untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
