"""VXLAN Validator for Aruba CX — single-process app: JSON API + static UI."""
from __future__ import annotations

import json
import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db, runner
from .audit import audit, guard_block_count, tail_audit
from .catalog import CATEGORIES, catalog_dict
from .config import settings
from .discovery.base import get_discovery
from .seed import seed_all

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
START_TS = time.time()

app = FastAPI(title="VXLAN Validator for Aruba CX", version=settings.version)


def _load_connection(name: str | None) -> dict | None:
    """Resolve a saved connection profile to usable creds (secret decoded here,
    never exposed via the API)."""
    if not name:
        return None
    rows = db.q("SELECT * FROM connections WHERE name=?", (name,))
    if not rows:
        raise HTTPException(400, "SSH/REST executor requires a valid connection profile.")
    import base64
    r = rows[0]
    return {"host": r["host"], "username": r["username"],
            "password": base64.b64decode(r["secret_enc"] or b"").decode(),
            "vrf": r["vrf"], "insecure": bool(r["insecure"])}


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    # Seed the demo fabric only on the very first boot, and only if enabled.
    # After any manual clear, the marker prevents re-seeding on restart.
    if db.get_meta("seeded") is None:
        if settings.seed_demo:
            for kind, items in seed_all().items():
                for it in items:
                    db.upsert_inventory(it["id"], kind, it)
            audit("boot.seed", note="demo inventory loaded (first boot)")
        db.set_meta("seeded", "1")
    # Built-in default admin: created on boot if it does not already exist, so
    # the app is usable with username/password out of the box (no .env needed).
    # SECURITY: change this password before any non-lab deployment.
    if settings.local_users_enabled:
        if not auth.user_exists("admin"):
            auth.create_user("admin", "admin", "admin")
            audit("boot.admin", username="admin", note="built-in default admin created")
        # Optional additional named admin from env.
        env_u = os.getenv("VXV_ADMIN_USER")
        env_p = os.getenv("VXV_ADMIN_PASS")
        if env_u and env_p and env_u != "admin" and not auth.user_exists(env_u):
            auth.create_user(env_u, env_p, "admin")
    audit("boot", version=settings.version, executor=settings.default_executor,
          read_only=settings.read_only)


# ---------------- public ----------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": settings.version, "read_only": True,
            "uptime_s": round(time.time() - START_TS)}


@app.post("/api/auth/login")
async def login(req: Request) -> dict:
    body = await req.json()
    role = auth.verify_user(body.get("username", ""), body.get("password", ""))
    if not role:
        audit("auth.login.fail", username=body.get("username"))
        raise HTTPException(401, "invalid credentials")
    audit("auth.login.ok", username=body["username"], role=role)
    return {"token": auth.issue_token(body["username"], role), "role": role}


# ---------------- meta / catalog ----------------
@app.get("/api/meta")
def meta(p=Depends(auth.require("viewer"))) -> dict:
    return {"version": settings.version, "read_only": True,
            "default_executor": settings.default_executor,
            "categories": CATEGORIES, "role": p.role, "user": p.get("user"),
            "local_users": settings.local_users_enabled}


@app.get("/api/catalog")
def catalog(p=Depends(auth.require("viewer"))) -> dict:
    tests = catalog_dict()
    return {"count": len(tests), "categories": CATEGORIES, "tests": tests}


# ---------------- inventory ----------------
@app.get("/api/inventory")
def inventory(p=Depends(auth.require("viewer"))) -> dict:
    return {k: db.get_inventory(k) for k in ("vtep", "vni", "tunnel", "vsx_pair")}


@app.post("/api/inventory/import")
async def import_inventory(req: Request, p=Depends(auth.require("operator"))) -> dict:
    body = await req.json()
    n = 0
    for kind, items in body.items():
        for it in items:
            db.upsert_inventory(it["id"], kind, it)
            n += 1
    audit("inventory.import", items=n, user=p.get("user"))
    return {"imported": n}


@app.delete("/api/inventory")
def clear_inventory(p=Depends(auth.require("operator"))) -> dict:
    db.clear_inventory()
    db.set_meta("seeded", "1")  # ensure it won't re-seed on restart
    audit("inventory.clear", user=p.get("user"))
    return {"cleared": True}


# ---------------- discovery ----------------
@app.post("/api/discover")
async def discover(req: Request, p=Depends(auth.require("operator"))) -> dict:
    body = await req.json()
    seed = body.get("seed", "")
    depth = body.get("depth", "recursive")
    adapter = body.get("adapter", "simulated")
    connection = _load_connection(body.get("connection")) if adapter == "agent" else None
    log_lines: list[str] = []
    disc = get_discovery(adapter, connection)
    try:
        found = disc.walk(seed, depth, log_lines.append, connection)
    except NotImplementedError as e:
        raise HTTPException(400, str(e))
    existing = {i["id"] for k in ("vtep", "vni", "tunnel", "vsx_pair")
                for i in db.get_inventory(k)}
    for kind in found:
        for it in found[kind]:
            it["_new"] = it["id"] not in existing
    return {"log": log_lines, "found": found}


# ---------------- connections ----------------
@app.get("/api/connections")
def list_connections(p=Depends(auth.require("viewer"))) -> dict:
    rows = db.q("SELECT name,host,protocol,vrf,username,insecure,updated_at FROM connections")
    return {"connections": [dict(r) for r in rows]}  # secret never selected/returned


@app.post("/api/connections")
async def save_connection(req: Request, p=Depends(auth.require("admin"))) -> dict:
    b = await req.json()
    name = (b.get("name") or "").strip()
    host = (b.get("host") or "").strip()
    if not name or not host:
        raise HTTPException(400, "Profile name and host are both required.")
    import base64
    enc = base64.b64encode((b.get("password", "")).encode()).decode()  # obfuscated at rest
    db.x("INSERT INTO connections(name,host,protocol,vrf,username,secret_enc,insecure,updated_at) "
         "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET host=excluded.host, "
         "protocol=excluded.protocol, vrf=excluded.vrf, username=excluded.username, "
         "secret_enc=excluded.secret_enc, insecure=excluded.insecure, updated_at=excluded.updated_at",
         (name, host, b.get("protocol", "ssh"), b.get("vrf", "mgmt"),
          b.get("username", ""), enc, 1 if b.get("insecure") else 0, time.time()))
    audit("connection.save", name=name, host=host, protocol=b.get("protocol"))
    return {"saved": name}


@app.delete("/api/connections/{name}")
def delete_connection(name: str, p=Depends(auth.require("admin"))) -> dict:
    db.x("DELETE FROM connections WHERE name=?", (name,))
    audit("connection.delete", name=name, user=p.get("user"))
    return {"deleted": name}


# ---------------- run (streaming) ----------------
@app.post("/api/run")
async def run_tests(req: Request, p=Depends(auth.require("operator"))):
    body = await req.json()
    executor = body.get("executor", settings.default_executor)
    label = body.get("label", "Full fabric")
    test_ids = body.get("tests") or [t["id"] for t in catalog_dict()]
    inv = {k: db.get_inventory(k) for k in ("vtep", "vni", "tunnel", "vsx_pair")}
    selected = body.get("targets", {})  # {vteps:[...], tunnels:[...], vnis:[...], vsxpairs:[...]}

    connection = None
    if executor in ("ssh", "rest"):
        connection = _load_connection(body.get("connection"))

    def stream():
        for event in runner.run(label, executor, test_ids, inv, selected, connection):
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ---------------- runs / reports ----------------
@app.get("/api/runs")
def runs(p=Depends(auth.require("viewer"))) -> dict:
    return {"runs": db.list_runs()}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str, p=Depends(auth.require("viewer"))) -> dict:
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


# ---------------- agent status ----------------
@app.get("/api/agent/status")
def agent_status(p=Depends(auth.require("viewer"))) -> dict:
    inv = db.get_inventory("vtep")
    return {
        "version": settings.version, "read_only": True,
        "uptime_s": round(time.time() - START_TS),
        "executor": settings.default_executor,
        "guard_blocks": guard_block_count(),
        "switches": [{"id": v["id"], "mgmt": v.get("mgmt"), "reachable": None} for v in inv],
        "audit_tail": tail_audit(25),
    }


@app.get("/api/audit")
def audit_log(n: int = 100, p=Depends(auth.require("admin"))) -> dict:
    return {"audit": tail_audit(n)}


# ---------------- user management ----------------
@app.get("/api/users")
def list_users(p=Depends(auth.require("admin"))) -> dict:
    return {"users": auth.list_users()}


@app.post("/api/users")
async def create_user(req: Request, p=Depends(auth.require("admin"))) -> dict:
    b = await req.json()
    username = (b.get("username") or "").strip()
    password = b.get("password") or ""
    role = b.get("role", "viewer")
    if not username or not password:
        raise HTTPException(400, "Username and password are both required.")
    if role not in auth.ROLE_RANK:
        raise HTTPException(400, "Role must be viewer, operator, or admin.")
    auth.create_user(username, password, role)
    return {"saved": username, "role": role}


@app.delete("/api/users/{username}")
def delete_user(username: str, p=Depends(auth.require("admin"))) -> dict:
    if username == p.get("user"):
        raise HTTPException(400, "You can't delete the account you're signed in as.")
    rows = db.q("SELECT role FROM users WHERE username=?", (username,))
    if not rows:
        raise HTTPException(404, "user not found")
    if rows[0]["role"] == "admin" and auth.admin_count() <= 1:
        raise HTTPException(400, "Can't delete the last remaining admin.")
    auth.delete_user(username)
    return {"deleted": username}


# ---------------- static UI (mounted last) ----------------
if os.path.isdir(WEB_DIR):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
