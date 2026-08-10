"""Simulated executor.

Produces deterministic, plausible results seeded from the current inventory so
the entire workflow runs with zero real devices. The one modeled fault is a
low-MTU VTEP (DC2-LEAF-02 @ 1500): every MTU/jumbo check that touches it fails,
tunnel drop/bidir checks warn, everything else passes. This reproduces the
"38 pass / 4 warn / 2 fail" shape shown in the app.
"""
from __future__ import annotations

from ..catalog import Test
from .base import guarded_cli, guarded_rest, result

FABRIC_MTU = 9198
LOW_MTU = 1500


def _touches_low_mtu(target: dict, ctx: dict) -> bool:
    vteps = {v["id"]: v for v in ctx["inventory"]["vtep"]}
    kind = target.get("_kind")
    if kind == "vtep":
        return target.get("mtu", FABRIC_MTU) < FABRIC_MTU
    if kind == "tunnel":
        for end in (target.get("src"), target.get("dst")):
            if vteps.get(end, {}).get("mtu", FABRIC_MTU) < FABRIC_MTU:
                return True
        return False
    if kind == "vni":
        # A VNI's data-plane spans all VTEPs; the fabric has a low-MTU member.
        return any(v.get("mtu", FABRIC_MTU) < FABRIC_MTU for v in vteps.values())
    if kind == "vsxPair":
        for member in (target.get("primary"), target.get("secondary")):
            if vteps.get(member, {}).get("mtu", FABRIC_MTU) < FABRIC_MTU:
                return True
    return False


def _evidence(test: Test, target: dict, lines: list[str]) -> dict:
    cmds = []
    for c in test.cli:
        rendered = _render(c, target)
        allowed, cmd = guarded_cli(rendered)
        cmds.append({"command": cmd, "allowed": allowed})
    for r in test.rest:
        guarded_rest("GET", r)
    return {"executor": "simulated", "commands": cmds, "rest": test.rest, "output": lines}


def _render(cmd: str, target: dict) -> str:
    return (cmd
            .replace("<remote-loopback>", target.get("dst_lo", "10.255.0.21"))
            .replace("<remote-tenant-ip>", "198.18.0.2")
            .replace("<tenant-vrf>", "TENANT")
            .replace("<vlan>", str(target.get("vlan", "100")))
            .replace("<id>", str(target.get("vni", "10100")))
            .replace("<access-port>", "1/1/10")
            .replace("<isl-lag>", "lag256")
            .replace("<isl-member>", "1/1/49"))


class SimulatedExecutor:
    name = "simulated"

    def run(self, test: Test, target: dict, ctx: dict) -> dict:
        low = _touches_low_mtu(target, ctx)

        # MTU family: hard-fail on anything touching the low-MTU VTEP.
        if test.category == "MTU" and low:
            if test.id in ("mtu-hop", "mtu-p2p", "mtu-sweep", "mtu-tenant"):
                ev = _evidence(test, target, [
                    "1472/1472 bytes: OK (DF)",
                    f"8972 bytes: 5/5 dropped (DF set) — path MTU < {FABRIC_MTU}",
                    "!!! frag-needed suppressed at hardware pipeline",
                ])
                return result("fail",
                              f"DF-bit jumbo fails to {target.get('dst', 'peer')}; "
                              f"path MTU capped near {LOW_MTU}.", ev)
            ev = _evidence(test, target, [f"underlay MTU {LOW_MTU} < fabric standard {FABRIC_MTU}"])
            return result("fail", "Underlay MTU below fabric standard on this element.", ev)

        # Tunnel drops / bidirectional growth warn when a low-MTU end is involved.
        if test.id in ("tun-drops", "tun-bidir", "mtu-icmp") and low:
            ev = _evidence(test, target, ["encap counters advancing", "decap counters flat (one-way)"])
            return result("warn", "Asymmetric counters consistent with a one-way MTU problem.", ev)

        # Data-plane jumbo warns fabric-wide because a member is low-MTU.
        if test.id == "dp-jumbo" and low:
            ev = _evidence(test, target, ["tenant 1400B ping OK", "tenant 8000B DF ping FAILS"])
            return result("warn", "Tenant jumbo fails across overlay; underlay MTU headroom missing.", ev)

        # Everything else passes with plausible evidence.
        ev = _evidence(test, target, ["output nominal"])
        return result("pass", "OK", ev)
