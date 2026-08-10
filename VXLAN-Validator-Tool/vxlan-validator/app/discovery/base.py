"""Discovery: probe a seed switch and walk out to the rest of the static-VXLAN
fabric. Two adapters share one interface.

  SimulatedDiscovery - seeded fabric, works with no network.
  AgentDiscovery     - real SSH walk, driven by the tested parsers in
                       app/parsers.py. Read-only (show-commands only).

Platform note: `show vni` is invalid on 8325/GL.10.13.1040. VNI/peer data comes
from `show running-config interface vxlan1` and `show interface vxlan1`.
"""
from __future__ import annotations

from ..audit import audit
from ..config import settings
from ..executors.base import guarded_cli
from ..parsers import parse_loopback, parse_vsx_status, parse_vxlan_running_config
from ..seed import seed_all

# Read-only probe set, in the exact forms the device accepts.
PROBE_CLI = [
    "show running-config interface vxlan1",
    "show vsx status",
    "show interface loopback 1",
]
MAX_HOPS = 32


class SimulatedDiscovery:
    name = "simulated"

    def walk(self, seed: str, depth: str, log, connection=None) -> dict:
        found = seed_all()
        for cmd in PROBE_CLI + ["show interface vxlan1"]:
            _, c = guarded_cli(cmd)
            log(f"$ {c}")
        log(f"seed {seed}: identity, source loopback, VSX role resolved")
        if depth in ("vsx", "peers", "recursive"):
            log("VSX peer discovered and paired (dedup by anycast loopback)")
        if depth in ("peers", "recursive"):
            log(f"{len(found['tunnel'])} static vtep-peers enumerated from vxlan1 config")
        if depth == "recursive":
            log("recursed into remote leaves; fabric walk complete")
        audit("discovery.walk", adapter="simulated", seed=seed, depth=depth,
              vteps=len(found["vtep"]), vnis=len(found["vni"]))
        return found


class AgentDiscovery:
    """Real fabric walk over SSH. Uses the same credentials for every hop (the
    common fabric service-account pattern) and connects to peers by their VTEP
    loopback. Every command is guarded; only show-commands are issued."""
    name = "agent"

    def __init__(self, connection: dict | None):
        self.conn = connection
        self._runner = self._netmiko_runner  # overridable in tests

    def _netmiko_runner(self, host: str, cmds: list[str], log) -> dict:
        from netmiko import ConnectHandler  # lazy
        dev = ConnectHandler(
            device_type="aruba_aoscx", host=host,
            username=self.conn["username"], password=self.conn["password"],
            timeout=settings.ssh_timeout, fast_cli=False,
        )
        out: dict = {}
        try:
            for c in cmds:
                allowed, cc = guarded_cli(c)
                if not allowed:
                    continue
                log(f"{host} $ {cc}")
                out[c] = dev.send_command(cc, read_timeout=settings.ssh_timeout)
        finally:
            dev.disconnect()
        return out

    def _probe(self, host: str, log) -> dict:
        raw = self._runner(host, PROBE_CLI, log)
        rc = parse_vxlan_running_config(raw.get(PROBE_CLI[0], ""))
        vsx = parse_vsx_status(raw.get(PROBE_CLI[1], ""))
        lo = parse_loopback(raw.get(PROBE_CLI[2], ""))
        return {"rc": rc, "vsx": vsx, "lo": lo, "host": host}

    def walk(self, seed: str, depth: str, log, connection=None) -> dict:
        if connection:
            self.conn = connection
        if not self.conn:
            raise NotImplementedError(
                "Agent discovery requires a bound SSH connection profile "
                "(add one under Connections, then select it).")

        found = {"vtep": [], "vni": {}, "tunnel": [], "vsx_pair": []}
        visited_lo: set[str] = set()
        queue: list[str] = [seed]
        hops = 0

        while queue and hops < MAX_HOPS:
            host = queue.pop(0)
            hops += 1
            try:
                p = self._probe(host, log)
            except Exception as e:  # noqa: BLE001
                log(f"{host}: probe failed ({e}) - recorded as unreachable")
                continue

            src = p["rc"].get("source_ip") or p["lo"].get("ipv4") or host
            if src in visited_lo:
                continue
            visited_lo.add(src)

            found["vtep"].append({
                "id": src, "hostname": src, "loopback": src, "mgmt": host,
                "mtu": None, "vsx_role": p["vsx"].get("device_role"),
                "platform": p["vsx"].get("platform"),
                "software": p["vsx"].get("software_version"),
                "vsx_system_mac": p["vsx"].get("system_mac"),
                "isl_link": p["vsx"].get("isl_link"),
            })
            log(f"{host}: VTEP {src} ({p['vsx'].get('platform') or '?'}, "
                f"role {p['vsx'].get('device_role') or 'standalone'})")

            peers_here: set[str] = set()
            for v in p["rc"]["vnis"]:
                key = str(v["vni"])
                entry = found["vni"].setdefault(
                    key, {"id": key, "vni": v["vni"], "vlan": v["vlan"],
                          "tenant": "", "bum": "HER", "members": []})
                if src not in entry["members"]:
                    entry["members"].append(src)
                for peer in v["vtep_peers"]:
                    peers_here.add(peer)
            for peer in sorted(peers_here):
                tid = "__".join(sorted([src, peer]))
                if tid not in {t["id"] for t in found["tunnel"]}:
                    found["tunnel"].append({"id": tid, "src": src, "dst": peer,
                                            "src_lo": src, "dst_lo": peer})
                if depth == "recursive" and peer not in visited_lo and peer not in queue:
                    queue.append(peer)

            if depth == "seed":
                break

        by_mac: dict[str, list[str]] = {}
        for v in found["vtep"]:
            mac = v.get("vsx_system_mac")
            if mac:
                by_mac.setdefault(mac, []).append(v["id"])
        for mac, members in by_mac.items():
            found["vsx_pair"].append(
                {"id": "VSX-" + mac.replace(":", "")[-6:], "members": members,
                 "system_mac": mac, "anycast_lo": members[0]})

        found["vni"] = list(found["vni"].values())
        audit("discovery.walk", adapter="agent", seed=seed, depth=depth,
              vteps=len(found["vtep"]), vnis=len(found["vni"]),
              tunnels=len(found["tunnel"]))
        return found


def get_discovery(adapter: str, connection: dict | None = None):
    return AgentDiscovery(connection) if adapter == "agent" else SimulatedDiscovery()
