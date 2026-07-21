"""Test run engine. Expands (selected tests x scoped targets) into checks, runs
each through the chosen executor, and yields streaming events for the UI while
persisting the run and its results."""
from __future__ import annotations

import time
import uuid

from . import db
from .audit import audit
from .catalog import by_id
from .executors.base import result as _res
from .executors.rest import RestExecutor
from .executors.simulated import SimulatedExecutor
from .executors.ssh import SSHExecutor

EXECUTORS = {"simulated": SimulatedExecutor(), "ssh": SSHExecutor(), "rest": RestExecutor()}


def _targets_for_scope(scope: str, inv: dict, selected: dict) -> list[dict]:
    """Return target dicts tagged with _kind for a given test scope."""
    def tag(items, kind, sel_key):
        picked = selected.get(sel_key)
        out = []
        for it in items:
            if picked is None or it["id"] in picked:
                out.append({**it, "_kind": kind})
        return out

    if scope == "vtep":
        return tag(inv["vtep"], "vtep", "vteps")
    if scope == "tunnel":
        return tag(inv["tunnel"], "tunnel", "tunnels")
    if scope == "vni":
        return tag(inv["vni"], "vni", "vnis")
    if scope == "vsxPair":
        return tag(inv["vsx_pair"], "vsxPair", "vsxpairs")
    return []


def plan_count(test_ids: list[str], inv: dict, selected: dict) -> int:
    cat = by_id()
    n = 0
    for tid in test_ids:
        t = cat.get(tid)
        if t:
            n += len(_targets_for_scope(t.scope, inv, selected))
    return n


def run(label: str, executor: str, test_ids: list[str], inv: dict,
        selected: dict, connection: dict | None = None):
    """Generator yielding streaming events; final event carries the summary."""
    cat = by_id()
    ex = EXECUTORS.get(executor, EXECUTORS["simulated"])
    run_id = uuid.uuid4().hex[:12]
    started = time.time()
    ctx = {"inventory": inv, "connection": connection}

    totals = {"pass": 0, "warn": 0, "fail": 0, "error": 0}
    scope_targets = {"vtep": set(), "tunnel": set(), "vni": set(), "vsxPair": set()}
    cat_worst: dict[str, str] = {}
    _rank = {"pass": 0, "warn": 1, "error": 2, "fail": 3}

    db.save_run({"id": run_id, "label": label, "executor": executor,
                 "started_at": started, "finished_at": None,
                 "summary": {"totals": totals, "total": 0}, "seeded": False})

    audit("run.start", run_id=run_id, label=label, executor=executor, tests=len(test_ids))
    yield {"type": "start", "run_id": run_id, "label": label, "executor": executor}

    for tid in test_ids:
        t = cat.get(tid)
        if not t:
            continue
        for target in _targets_for_scope(t.scope, inv, selected):
            try:
                out = ex.run(t, target, ctx)
            except Exception as e:  # noqa: BLE001
                out = _res("error", f"executor exception: {e}")
            status = out["status"]
            totals[status] = totals.get(status, 0) + 1
            scope_targets[t.scope].add(target["id"])
            if _rank.get(status, 0) >= _rank.get(cat_worst.get(t.category, "pass"), 0):
                cat_worst[t.category] = status
            row = {"test_id": tid, "target": target["id"], "status": status,
                   "detail": out["detail"], "evidence": out["evidence"]}
            db.save_result(run_id, row)
            yield {"type": "result", "test_id": tid, "title": t.title,
                   "category": t.category, "severity": t.severity,
                   "target": target["id"], "status": status, "detail": out["detail"]}

    total = sum(totals.values())
    overall = "critical" if totals["fail"] or totals["error"] else ("degraded" if totals["warn"] else "healthy")
    summary = {
        "totals": totals, "total": total,
        "pass_pct": round(100 * totals["pass"] / total) if total else 0,
        "vteps": len(scope_targets["vtep"]), "tunnels": len(scope_targets["tunnel"]),
        "vnis": len(scope_targets["vni"]), "vsxpairs": len(scope_targets["vsxPair"]),
        "by_category": cat_worst, "overall_health": overall,
    }
    db.save_run({"id": run_id, "label": label, "executor": executor,
                 "started_at": started, "finished_at": time.time(),
                 "summary": summary, "seeded": False})
    audit("run.finish", run_id=run_id, **totals, total=total)
    yield {"type": "done", "run_id": run_id, "summary": summary}
