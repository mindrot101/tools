"""SQLite persistence: jobs, packets, users, share tokens, settings, filters."""
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import settings as cfg

DATA_DIR = Path(cfg.DATA_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "pcap.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with _connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, created REAL, updated REAL, status TEXT,
                error TEXT, filenames TEXT, dedup_strategy TEXT, time_window REAL,
                total_packets INTEGER DEFAULT 0, processed_packets INTEGER DEFAULT 0,
                unique_packets INTEGER DEFAULT 0, duplicates_removed INTEGER DEFAULT 0,
                summary_json TEXT, owner_id TEXT DEFAULT 'public',
                share_token TEXT, source TEXT DEFAULT 'upload'
            );
            CREATE TABLE IF NOT EXISTS packets (
                job_id TEXT, idx INTEGER, ts REAL, src TEXT, dst TEXT, proto TEXT,
                sport INTEGER, dport INTEGER, length INTEGER, protocols TEXT,
                is_dup INTEGER DEFAULT 0, hash TEXT, PRIMARY KEY (job_id, idx)
            );
            CREATE INDEX IF NOT EXISTS idx_packets_job ON packets(job_id);
            CREATE INDEX IF NOT EXISTS idx_packets_hash ON packets(job_id, hash);
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT UNIQUE, pw_hash TEXT,
                created REAL, is_admin INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS saved_filters (
                id TEXT PRIMARY KEY, owner_id TEXT, name TEXT, expression TEXT, created REAL
            );
            """
        )


# ---- jobs ----
def create_job(job_id, filenames, dedup, window, owner_id="public", source="upload"):
    now = time.time()
    with _connect() as c:
        c.execute("INSERT INTO jobs (id,created,updated,status,filenames,dedup_strategy,"
                  "time_window,owner_id,source) VALUES (?,?,?,?,?,?,?,?,?)",
                  (job_id, now, now, "queued", json.dumps(filenames), dedup, window, owner_id, source))


def update_job(job_id, **fields):
    if not fields:
        return
    fields["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _connect() as c:
        c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def set_summary(job_id, summary):
    update_job(job_id, summary_json=json.dumps(summary))


def _job_row(row):
    d = dict(row)
    d["filenames"] = json.loads(d["filenames"]) if d.get("filenames") else []
    if "summary_json" in d:
        d["summary"] = json.loads(d["summary_json"]) if d.get("summary_json") else None
        d.pop("summary_json")
    return d


def get_job(job_id):
    with _connect() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job_row(row) if row else None


def get_job_by_share(token):
    with _connect() as c:
        row = c.execute("SELECT * FROM jobs WHERE share_token=?", (token,)).fetchone()
    return _job_row(row) if row else None


def list_jobs(limit=50, owner_id=None):
    q = ("SELECT id,created,status,filenames,total_packets,unique_packets,"
         "duplicates_removed,owner_id,share_token,source FROM jobs")
    args: List[Any] = []
    if owner_id is not None:
        q += " WHERE owner_id=?"
        args.append(owner_id)
    q += " ORDER BY created DESC LIMIT ?"
    args.append(limit)
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    return [_job_row(r) for r in rows]


def delete_job(job_id):
    with _connect() as c:
        cur = c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        c.execute("DELETE FROM packets WHERE job_id=?", (job_id,))
    return cur.rowcount > 0


def purge_older_than(cutoff_ts) -> int:
    with _connect() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM jobs WHERE created<?", (cutoff_ts,)).fetchall()]
        for jid in ids:
            c.execute("DELETE FROM jobs WHERE id=?", (jid,))
            c.execute("DELETE FROM packets WHERE job_id=?", (jid,))
    return len(ids)


def job_counts() -> Dict[str, int]:
    with _connect() as c:
        rows = c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
    return {r[0]: r[1] for r in rows}


# ---- packets ----
def add_packets(job_id, rows):
    if not rows:
        return
    with _connect() as c:
        c.executemany("INSERT OR REPLACE INTO packets (job_id,idx,ts,src,dst,proto,sport,"
                      "dport,length,protocols,is_dup,hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def get_packets(job_id, offset, limit, proto=None, include_dups=True,
                where_extra="", extra_args=None):
    q = ("SELECT idx,ts,src,dst,proto,sport,dport,length,protocols,is_dup "
         "FROM packets WHERE job_id=?")
    args: List[Any] = [job_id]
    if not include_dups:
        q += " AND is_dup=0"
    if proto:
        q += " AND protocols LIKE ?"
        args.append(f'%"{proto}"%')
    if where_extra:
        q += f" AND ({where_extra})"
        args += list(extra_args or [])
    q += " ORDER BY idx LIMIT ? OFFSET ?"
    args += [limit, offset]
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["protocols"] = json.loads(d["protocols"]) if d.get("protocols") else []
        out.append(d)
    return out


def count_packets(job_id, include_dups=True, proto=None, where_extra="", extra_args=None):
    q = "SELECT COUNT(*) FROM packets WHERE job_id=?"
    args: List[Any] = [job_id]
    if not include_dups:
        q += " AND is_dup=0"
    if proto:
        q += " AND protocols LIKE ?"
        args.append(f'%"{proto}"%')
    if where_extra:
        q += f" AND ({where_extra})"
        args += list(extra_args or [])
    with _connect() as c:
        return c.execute(q, args).fetchone()[0]


def packet_hashes(job_id, unique_only=True) -> set:
    q = "SELECT DISTINCT hash FROM packets WHERE job_id=?"
    if unique_only:
        q += " AND is_dup=0"
    with _connect() as c:
        return {r[0] for r in c.execute(q, (job_id,)).fetchall() if r[0]}


# ---- users ----
def create_user(uid, username, pw_hash, is_admin=False):
    with _connect() as c:
        c.execute("INSERT INTO users (id,username,pw_hash,created,is_admin) VALUES (?,?,?,?,?)",
                  (uid, username, pw_hash, time.time(), 1 if is_admin else 0))


def get_user_by_name(username):
    with _connect() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def get_user(uid):
    with _connect() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


# ---- kv settings ----
def set_setting(key, value):
    with _connect() as c:
        c.execute("INSERT INTO app_settings (key,value) VALUES (?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_setting(key, default=""):
    with _connect() as c:
        row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


# ---- saved filters ----
def add_filter(fid, owner_id, name, expression):
    with _connect() as c:
        c.execute("INSERT INTO saved_filters (id,owner_id,name,expression,created) VALUES (?,?,?,?,?)",
                  (fid, owner_id, name, expression, time.time()))


def list_filters(owner_id):
    with _connect() as c:
        rows = c.execute("SELECT id,name,expression FROM saved_filters WHERE owner_id IN (?, 'public') "
                         "ORDER BY created DESC", (owner_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_filter(fid):
    with _connect() as c:
        cur = c.execute("DELETE FROM saved_filters WHERE id=?", (fid,))
    return cur.rowcount > 0


def sample_by_hashes(job_id, hashes, limit=25):
    hashes = list(hashes)[:900]
    if not hashes:
        return []
    ph = ",".join("?" * len(hashes))
    q = (f"SELECT idx,ts,src,dst,proto,sport,dport,length,protocols FROM packets "
         f"WHERE job_id=? AND is_dup=0 AND hash IN ({ph}) ORDER BY idx LIMIT ?")
    with _connect() as c:
        rows = c.execute(q, (job_id, *hashes, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["protocols"] = json.loads(d["protocols"]) if d.get("protocols") else []
        out.append(d)
    return out
