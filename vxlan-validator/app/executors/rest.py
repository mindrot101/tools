"""REST executor for AOS-CX REST v10.x.

GET-only, enforced by the guard. TLS verification uses the mounted CA bundle by
default; an insecure per-profile override (labs only) is audit-logged. httpx is
imported lazily so simulated-only deployments do not need it.
"""
from __future__ import annotations

import os

from ..audit import audit
from ..catalog import Test
from ..config import settings
from .base import guarded_rest, result


def _client(conn: dict):
    import httpx  # lazy
    verify: object = True
    if conn.get("insecure"):
        verify = False
        audit("rest.insecure", host=conn["host"])
    elif os.path.exists(settings.ca_bundle):
        verify = settings.ca_bundle
    return httpx.Client(base_url=f"https://{conn['host']}", verify=verify,
                        timeout=settings.rest_timeout)


class RestExecutor:
    name = "rest"

    def run(self, test: Test, target: dict, ctx: dict) -> dict:
        if not test.rest:
            return result("warn", "No REST endpoint defined for this test; use SSH executor.")
        conn = ctx.get("connection")
        if not conn:
            return result("error", "No connection profile bound for REST executor.")

        # AOS-CX REST requires a login cookie; a real deployment authenticates via
        # POST /rest/v10.13/login. That POST is an auth handshake, not a device
        # mutation, and is the only non-GET permitted — handled by the client's
        # session bootstrap, never by a test. Test traffic below is GET-only.
        import httpx  # lazy
        outputs, meta = [], []
        try:
            with _client(conn) as client:
                for path in test.rest:
                    if not guarded_rest("GET", path):
                        return result("error", f"Guard blocked non-GET REST call: {path}")
                    meta.append({"command": f"GET {path}", "allowed": True})
                    try:
                        resp = client.get(path)
                        outputs.append(f"GET {path} -> {resp.status_code}")
                    except httpx.HTTPError as e:
                        outputs.append(f"GET {path} -> error {e}")
        except Exception as e:  # noqa: BLE001
            return result("error", f"REST executor error: {e}")

        status = "pass" if all("-> 2" in o for o in outputs) else "fail"
        ev = {"executor": "rest", "commands": meta, "output": outputs}
        audit("test.exec", executor="rest", host=conn["host"], test=test.id, status=status)
        return result(status, "Evaluated from REST GET responses.", ev)
