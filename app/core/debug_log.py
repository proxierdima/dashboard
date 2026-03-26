from __future__ import annotations

import json
import time
from pathlib import Path

_LOG_PATH = Path("debug-493f03.log")
_SESSION_ID = "493f03"


def debug_log(*, run_id: str, hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    """
    NDJSON debug logger for this Cursor debug session.
    Writes ONLY to debug-493f03.log. Avoid secrets/PII in data.
    """

    payload = {
        "sessionId": _SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    try:
        _LOG_PATH.open("a", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Never break runtime due to debugging IO
        return
