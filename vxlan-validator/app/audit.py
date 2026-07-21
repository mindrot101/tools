"""Append-only audit log. JSON lines to <data_dir>/audit.log and stdout."""
from __future__ import annotations

import json
import sys
import threading
import time

from .config import settings

_lock = threading.Lock()
_guard_blocks = 0


def audit(event: str, **fields) -> None:
    rec = {"ts": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "event": event, **fields}
    line = json.dumps(rec, default=str)
    with _lock:
        try:
            with open(settings.audit_path, "a") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        print("AUDIT " + line, file=sys.stdout, flush=True)


def record_guard_block() -> None:
    global _guard_blocks
    with _lock:
        _guard_blocks += 1


def guard_block_count() -> int:
    return _guard_blocks


def tail_audit(n: int = 100) -> list[dict]:
    try:
        with open(settings.audit_path) as fh:
            lines = fh.readlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except (OSError, json.JSONDecodeError):
        return []
