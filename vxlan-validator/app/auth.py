"""Authentication and authorization.

Primary:   API key via `X-API-Key` header (single operator / field use).
Secondary: local users (bcrypt) issuing HMAC-signed bearer tokens with a role.
Roles:     viewer < operator < admin.

No anonymous access. Every protected route depends on `require(role)`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import bcrypt
from fastapi import Depends, Header, HTTPException

from . import db
from .audit import audit
from .config import settings

ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


# ---------- local users ----------
def create_user(username: str, password: str, role: str) -> None:
    if role not in ROLE_RANK:
        raise ValueError("invalid role")
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.x(
        "INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,?) "
        "ON CONFLICT(username) DO UPDATE SET pw_hash=excluded.pw_hash, role=excluded.role",
        (username, h, role, time.time()),
    )
    audit("user.upsert", username=username, role=role)


def verify_user(username: str, password: str) -> str | None:
    rows = db.q("SELECT pw_hash,role FROM users WHERE username=?", (username,))
    if not rows:
        return None
    if bcrypt.checkpw(password.encode(), rows[0]["pw_hash"].encode()):
        return rows[0]["role"]
    return None


def user_exists(username: str) -> bool:
    return bool(db.q("SELECT 1 FROM users WHERE username=?", (username,)))


def user_count() -> int:
    return db.q("SELECT COUNT(*) c FROM users")[0]["c"]


def admin_count() -> int:
    return db.q("SELECT COUNT(*) c FROM users WHERE role='admin'")[0]["c"]


def list_users() -> list[dict]:
    return [{"username": r["username"], "role": r["role"], "created_at": r["created_at"]}
            for r in db.q("SELECT username,role,created_at FROM users ORDER BY role DESC, username")]


def delete_user(username: str) -> None:
    db.x("DELETE FROM users WHERE username=?", (username,))
    audit("user.delete", username=username)


# ---------- signed session tokens ----------
def _sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def issue_token(username: str, role: str) -> str:
    return _sign({"u": username, "r": role, "exp": time.time() + settings.session_ttl_seconds})


def verify_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    pad = "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ---------- FastAPI dependency ----------
class Principal(dict):
    @property
    def role(self) -> str:
        return self.get("role", "viewer")


async def current_principal(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    # API key path — full operator rights.
    if x_api_key:
        if hmac.compare_digest(x_api_key, settings.api_key):
            return Principal({"kind": "apikey", "user": "apikey", "role": "operator"})
        audit("auth.fail", kind="apikey")
        raise HTTPException(401, "invalid API key")

    # Bearer token path (local users).
    if authorization and authorization.lower().startswith("bearer "):
        payload = verify_token(authorization[7:].strip())
        if payload:
            return Principal({"kind": "user", "user": payload["u"], "role": payload["r"]})
        audit("auth.fail", kind="bearer")
        raise HTTPException(401, "invalid or expired token")

    raise HTTPException(401, "authentication required")


def require(min_role: str = "viewer"):
    threshold = ROLE_RANK[min_role]

    async def _dep(p: Principal = Depends(current_principal)) -> Principal:
        if ROLE_RANK.get(p.role, 0) < threshold:
            raise HTTPException(403, f"requires role >= {min_role}")
        return p

    return _dep
