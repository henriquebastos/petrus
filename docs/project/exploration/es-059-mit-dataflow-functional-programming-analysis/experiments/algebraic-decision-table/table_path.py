"""Put the v1 slice on ``sys.path`` for direct (non-pytest) script execution.

Importing this module is the standalone equivalent of ``conftest.py``: it
makes the committed ``typed-flow-vertical-slice`` modules importable so
``table_run.py`` works as a plain script. It mutates only ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / "typed-flow-vertical-slice"

for _path in (str(V1), str(HERE)):  # inserted in reverse so HERE ends up first
    if _path not in sys.path:
        sys.path.insert(0, _path)
