"""SSH executor for AOS-CX via Netmiko.

Read-only by construction: it only ever calls send_command (never send_config_set),
and every command is vetted by the guard before it is sent. Netmiko is imported
lazily so simulated-only deployments do not need it installed.

This executor evaluates the RAW CLI output heuristically. In production you would
attach per-test parsers (the golden-dataset harness in deployment.md). The parsing
here is intentionally conservative: it flags obvious failure keywords and otherwise
reports 'pass' with the captured evidence, so an operator always sees the CLI proof.
"""
from __future__ import annotations

import threading

from ..audit import audit
from ..catalog import Test
from ..config import settings
from .base import guarded_cli, result
from .simulated import _render

# Cap concurrent sessions per switch (CX mgmt plane is finite).
_sema: dict[str, threading.Semaphore] = {}
_sema_lock = threading.Lock()

FAIL_MARKERS = ("% ", "down", "not found", "no such", "error", "invalid", "unreachable", "0 packets received")
WARN_MARKERS = ("drop", "discard", "flap")


def _switch_sema(host: str) -> threading.Semaphore:
    with _sema_lock:
        if host not in _sema:
            _sema[host] = threading.Semaphore(settings.max_sessions_per_switch)
        return _sema[host]


def _connect(target: dict, ctx: dict):
    from netmiko import ConnectHandler  # lazy
    conn = ctx["connection"]
    return ConnectHandler(
        device_type="aruba_aoscx",
        host=conn["host"],
        username=conn["username"],
        password=conn["password"],
        timeout=settings.ssh_timeout,
        fast_cli=False,
    )


class SSHExecutor:
    name = "ssh"

    def run(self, test: Test, target: dict, ctx: dict) -> dict:
        conn = ctx.get("connection")
        if not conn:
            return result("error", "No connection profile bound for SSH executor.")

        host = conn["host"]
        sema = _switch_sema(host)
        if not sema.acquire(timeout=settings.ssh_timeout):
            return result("error", f"Session cap reached for {host}.")

        outputs: list[str] = []
        outs_by_cmd: dict[str, str] = {}
        cmds_meta: list[dict] = []
        try:
            device = None
            try:
                device = _connect(target, ctx)
            except Exception as e:  # noqa: BLE001
                return result("error", f"SSH connect failed: {e}")

            for raw in test.cli:
                rendered = _render(raw, target)
                allowed, cmd = guarded_cli(rendered)
                cmds_meta.append({"command": cmd, "allowed": allowed})
                if not allowed:
                    # Guard refused — never sent. This must not happen with the
                    # curated catalog; it is a hard stop if it ever does.
                    return result("error", f"Guard blocked non-read-only command: {cmd}")
                try:
                    out = device.send_command(cmd, read_timeout=settings.ssh_timeout)
                except Exception as e:  # noqa: BLE001
                    out = f"[command error] {e}"
                outputs.append(f"$ {cmd}\n{out}")
                outs_by_cmd[cmd] = out

            device.disconnect()
        finally:
            sema.release()

        # Prefer a deterministic, parser-backed verdict when we have one.
        from ..checks import CHECKS
        if test.id in CHECKS:
            status, detail = CHECKS[test.id](outs_by_cmd)
        else:
            status, detail = self._evaluate(outputs), "Evaluated from live CLI output (heuristic)."
        ev = {"executor": "ssh", "commands": cmds_meta, "output": outputs}
        audit("test.exec", executor="ssh", host=host, test=test.id,
              target=target.get("id"), status=status)
        return result(status, detail, ev)

    @staticmethod
    def _evaluate(outputs: list[str]) -> str:
        blob = "\n".join(outputs).lower()
        if any(m in blob for m in FAIL_MARKERS):
            return "fail"
        if any(m in blob for m in WARN_MARKERS):
            return "warn"
        return "pass"
