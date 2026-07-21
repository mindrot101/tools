"""Embedded SQLite storage. No external database dependency."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,          -- vtep | vni | tunnel | vsx_pair
    data        TEXT NOT NULL,          -- json blob
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS connections (
    name        TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    protocol    TEXT NOT NULL,          -- ssh | rest
    vrf         TEXT,
    username    TEXT,
    secret_enc  TEXT,                   -- fernet-less: stored obfuscated, never returned
    insecure    INTEGER DEFAULT 0,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    executor    TEXT NOT NULL,
    started_at  REAL NOT NULL,
    finished_at REAL,
    summary     TEXT NOT NULL,          -- json: totals, pass/warn/fail, scope counts
    seeded      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS results (
    run_id      TEXT NOT NULL,
    test_id     TEXT NOT NULL,
    target      TEXT NOT NULL,
    status      TEXT NOT NULL,          -- pass | warn | fail | error
    detail      TEXT,
    evidence    TEXT,                   -- json: commands + (redacted) output
    ts          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    username    TEXT PRIMARY KEY,
    pw_hash     TEXT NOT NULL,
    role        TEXT NOT NULL,          -- viewer | operator | admin
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA foreign_keys=ON;")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def init_db() -> None:
    conn()


def q(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        cur = conn().execute(sql, params)
        rows = cur.fetchall()
        return rows


def x(sql: str, params: tuple = ()) -> None:
    with _lock:
        conn().execute(sql, params)
        conn().commit()


# --- inventory helpers ---
def upsert_inventory(item_id: str, kind: str, data: dict) -> None:
    x(
        "INSERT INTO inventory(id,kind,data,updated_at) VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
        (item_id, kind, json.dumps(data), time.time()),
    )


def get_inventory(kind: str | None = None) -> list[dict]:
    if kind:
        rows = q("SELECT data FROM inventory WHERE kind=? ORDER BY id", (kind,))
    else:
        rows = q("SELECT data FROM inventory ORDER BY kind,id")
    return [json.loads(r["data"]) for r in rows]


def clear_inventory() -> None:
    x("DELETE FROM inventory")


def get_meta(key: str) -> str | None:
    rows = q("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


def set_meta(key: str, value: str) -> None:
    x("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      (key, value))


# --- run helpers ---
def save_run(run: dict) -> None:
    x(
        "INSERT INTO runs(id,label,executor,started_at,finished_at,summary,seeded) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "finished_at=excluded.finished_at, summary=excluded.summary",
        (
            run["id"], run["label"], run["executor"], run["started_at"],
            run.get("finished_at"), json.dumps(run["summary"]),
            1 if run.get("seeded") else 0,
        ),
    )


def save_result(run_id: str, r: dict) -> None:
    x(
        "INSERT INTO results(run_id,test_id,target,status,detail,evidence,ts) "
        "VALUES(?,?,?,?,?,?,?)",
        (run_id, r["test_id"], r["target"], r["status"], r.get("detail", ""),
         json.dumps(r.get("evidence", {})), time.time()),
    )


def list_runs() -> list[dict]:
    rows = q("SELECT * FROM runs ORDER BY started_at DESC")
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "label": r["label"], "executor": r["executor"],
            "started_at": r["started_at"], "finished_at": r["finished_at"],
            "summary": json.loads(r["summary"]), "seeded": bool(r["seeded"]),
        })
    return out


def get_run(run_id: str) -> dict | None:
    rows = q("SELECT * FROM runs WHERE id=?", (run_id,))
    if not rows:
        return None
    r = rows[0]
    results = [
        {
            "test_id": x["test_id"], "target": x["target"], "status": x["status"],
            "detail": x["detail"], "evidence": json.loads(x["evidence"] or "{}"),
        }
        for x in q("SELECT * FROM results WHERE run_id=? ORDER BY ts", (run_id,))
    ]
    return {
        "id": r["id"], "label": r["label"], "executor": r["executor"],
        "started_at": r["started_at"], "finished_at": r["finished_at"],
        "summary": json.loads(r["summary"]), "seeded": bool(r["seeded"]),
        "results": results,
    }
