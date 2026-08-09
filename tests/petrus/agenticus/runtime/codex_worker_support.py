"""Importable subprocess registry for private Codex Gondolin qualification."""

import os
import time
from pathlib import Path

from petrus.agenticus.runtime._codex_gondolin_service import _ACTIVITY, _CodexGondolinActivityClient


def activities():
    client = _CodexGondolinActivityClient()

    def activity(invocation, *, context):
        result = client(invocation, context=context)
        marker_value = os.environ.get("PETRUS_CODEX_GONDOLIN_WITHHOLD")
        if marker_value:
            marker = Path(marker_value)
            try:
                marker.touch(exist_ok=False)
            except FileExistsError:
                pass
            else:
                time.sleep(3600)
        return result

    return {_ACTIVITY: activity}
