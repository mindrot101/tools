"""Optional authentication: pbkdf2 password hashing + HMAC-signed tokens."""
import base64
import hashlib
import hmac
import secrets
import time
import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException

import settings
import storage

PUBLIC_USER = {"id": "public", "username": "public", "is_admin": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(dk.hex(), expected)


def _sign(msg: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_token(user_id: str) -> str:
    body = f"{user_id}.{int(time.time()) + settings.TOKEN_TTL}"
    b64 = base64.urlsafe_b64encode(body.encode()).decode()
    return f"{b64}.{_sign(body)}"


def verify_token(token: str) -> Optional[str]:
    try:
        b64, sig = token.rsplit(".", 1)
        body = base64.urlsafe_b64decode(b64.encode()).decode()
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        uid, exp = body.rsplit(".", 1)
        if int(exp) < time.time():
            return None
        return uid
    except (ValueError, TypeError):
        return None


def ensure_admin() -> None:
    """Bootstrap an admin user from env when auth is enabled."""
    if not settings.AUTH_ENABLED or not settings.ADMIN_PASSWORD:
        return
    if not storage.get_user_by_name(settings.ADMIN_USER):
        storage.create_user(uuid.uuid4().hex[:12], settings.ADMIN_USER,
                            hash_password(settings.ADMIN_PASSWORD), is_admin=True)


async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not settings.AUTH_ENABLED:
        return PUBLIC_USER
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    uid = verify_token(authorization[7:])
    user = storage.get_user(uid) if uid else None
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin privileges required")
    return user
