"""Deterministic check evaluators built on the tested parsers.

Each function takes a dict of {command_string: raw_output} and returns
(status, detail). Only checks with real ground-truth parsing live here; the SSH
executor falls back to heuristic evaluation for the rest. Keyed by test id in
CHECKS at the bottom.
"""
from __future__ import annotations

from . import parsers

CPU_WARN = 85
MEM_WARN = 85


def _find(outs: dict, *subs: str) -> str:
    for cmd, out in outs.items():
        if all(s in cmd for s in subs):
            return out
    return ""


def eval_vtep_iface(outs: dict) -> tuple[str, str]:
    r = parsers.parse_show_interface_vxlan(_find(outs, "show interface vxlan1"))
    if r["admin_up"] and r["oper_up"]:
        return "pass", (f"vxlan1 up; source {r['source_ip']}, UDP {r['udp_port']}, "
                        f"underlay VRF {r['underlay_vrf']}, {len(r['vnis'])} VNIs")
    return "fail", "vxlan1 is not admin/oper up"


def eval_vtep_udp(outs: dict) -> tuple[str, str]:
    r = parsers.parse_show_interface_vxlan(_find(outs, "show interface vxlan1"))
    if r["udp_port"] == 4789:
        return "pass", "destination UDP port 4789"
    return "fail", f"unexpected VXLAN UDP port: {r['udp_port']}"


def eval_vsx_isl(outs: dict) -> tuple[str, str]:
    r = parsers.parse_vsx_status(_find(outs, "vsx status"))
    if r["isl_in_sync"]:
        return "pass", f"ISL {r['isl_channel']}, role {r['device_role']}, ISL link {r['isl_link']}"
    return "fail", f"ISL channel not in-sync: {r['isl_channel']}"


def eval_vsx_sync(outs: dict) -> tuple[str, str]:
    r = parsers.parse_vsx_status(_find(outs, "vsx status"))
    if r["config_in_sync"] is True:
        sw = "; sw match" if r["software_match"] else "; SOFTWARE MISMATCH"
        status = "pass" if r["software_match"] else "warn"
        return status, f"config-sync {r['config_sync']}{sw} ({r['software_version']} vs {r['peer_software']})"
    return "fail", f"config-sync not clean: {r['config_sync']}"


def eval_crc(outs: dict) -> tuple[str, str]:
    rows = parsers.parse_error_statistics(_find(outs, "error-statistics"))
    bad = [r for r in rows if r["crc_fcs"] > 0 or r["rx_errors"] > 0]
    if not bad:
        return "pass", "no non-zero CRC/FCS or input errors"
    worst = max(bad, key=lambda r: r["crc_fcs"])
    return "fail", (f"{len(bad)} interface(s) with errors; worst {worst['interface']}"
                    f"{' (' + worst['lag'] + ')' if worst['lag'] else ''}: CRC/FCS {worst['crc_fcs']}")


def eval_cpu(outs: dict) -> tuple[str, str]:
    r = parsers.parse_system_resources(_find(outs, "resource-utilization"))
    cpu, mem = r.get("cpu_pct"), r.get("mem_pct")
    if cpu is None:
        return "warn", "could not read resource utilization"
    if cpu >= CPU_WARN or (mem or 0) >= MEM_WARN:
        return "warn", f"CPU {cpu}% / mem {mem}% — above threshold"
    return "pass", f"CPU {cpu}% / mem {mem}%"


def eval_tun_stats(outs: dict) -> tuple[str, str]:
    r = parsers.parse_vxlan_statistics(_find(outs, "vxlan 1 statistics"))
    if not r:
        return "warn", "no vxlan1 statistics returned"
    drops = r["rx_drops"] + r["tx_drops"]
    if drops > 0:
        return "fail", f"vxlan1 drops: RX {r['rx_drops']} / TX {r['tx_drops']}"
    return "pass", f"vxlan1 RX {r['rx_packets']}pkt / TX {r['tx_packets']}pkt, no drops"


# STP contributes to VXLAN health because static VXLAN bridges over L2. A recently
# or rapidly changing spanning tree destabilizes the tenant L2 domains. Evaluate
# every MST instance the check collected.
RECENT_TC_S = 600          # a change in the last 10 min = active instability
WATCH_TC_S = 3600          # a change in the last hour = worth noting


def eval_stp(outs: dict) -> tuple[str, str]:
    instances = []
    for cmd, out in outs.items():
        if "spanning-tree mst" in cmd:
            instances.append(parsers.parse_stp_mst(out))
    instances = [i for i in instances if i["instance"] is not None]
    if not instances:
        return "warn", "no MST instances parsed"

    recents, down_ports = [], []
    for inst in instances:
        if inst["last_tc_s"] is not None and inst["last_tc_s"] < WATCH_TC_S:
            recents.append((inst["instance"], inst["last_tc_s"]))
        for p in inst["ports"]:
            # A port STP sees as Down that is NOT administratively Disabled is a
            # real link problem feeding instability into the overlay.
            if p["state"].lower() == "down" and p["role"].lower() != "disabled":
                down_ports.append(f"MST{inst['instance']}:{p['port']}")

    if any(sec < RECENT_TC_S for _, sec in recents):
        inst, sec = min(recents, key=lambda x: x[1])
        return "fail", f"active STP topology change on MST{inst} {sec}s ago — L2 instability can disrupt the overlay"
    if down_ports:
        return "warn", f"STP sees down (non-disabled) port(s): {', '.join(sorted(set(down_ports))[:6])}"
    if recents:
        inst, sec = min(recents, key=lambda x: x[1])
        return "warn", f"recent STP topology change on MST{inst} {round(sec/60)}m ago — monitor for flapping"

    # Stable: report how long it's been and note any admin-disabled ports.
    oldest = max((i["last_tc_s"] for i in instances if i["last_tc_s"] is not None), default=None)
    disabled = sorted({p["port"] for i in instances for p in i["ports"]
                       if p["role"].lower() == "disabled"})
    age = f", last change {round(oldest/86400)}d ago" if oldest else ""
    note = f"; {len(disabled)} disabled port(s): {', '.join(disabled[:6])}" if disabled else ""
    return "pass", f"{len(instances)} MST instance(s) stable{age}{note}"


CHECKS = {
    "vtep-iface": eval_vtep_iface,
    "vtep-udp": eval_vtep_udp,
    "vsx-isl": eval_vsx_isl,
    "vsx-sync": eval_vsx_sync,
    "phy-crc": eval_crc,
    "hw-cpu": eval_cpu,
    "tun-stats": eval_tun_stats,
    "l2-mst-tc": eval_stp,
}
