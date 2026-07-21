"""Executor contract. Every executor runs a Test against one target and returns
a structured result. All device I/O passes through the read-only guard first."""
from __future__ import annotations

from typing import Protocol

from ..audit import audit, record_guard_block
from ..catalog import Test
from ..guard import vet_cli, vet_rest


class Executor(Protocol):
    name: str

    def run(self, test: Test, target: dict, ctx: dict) -> dict:
        """Return {status, detail, evidence}. status in pass|warn|fail|error."""
        ...


def guarded_cli(command: str) -> tuple[bool, str]:
    """Return (allowed, command). Blocks + audits anything not read-only."""
    v = vet_cli(command)
    if not v.allowed:
        record_guard_block()
        audit("guard.block", kind="cli", command=command, reason=v.reason)
    return v.allowed, v.command


def guarded_rest(method: str, path: str) -> bool:
    v = vet_rest(method, path)
    if not v.allowed:
        record_guard_block()
        audit("guard.block", kind="rest", command=f"{method} {path}", reason=v.reason)
    return v.allowed


def result(status: str, detail: str, evidence: dict | None = None) -> dict:
    return {"status": status, "detail": detail, "evidence": evidence or {}}
