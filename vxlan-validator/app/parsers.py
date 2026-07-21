"""
Deterministic parsers for AOS-CX show-command output.

Written against REAL output from an 8325 running GL.10.13.1040 (see
tests/fixtures/CORE_8325.txt) and exercised by tests/test_parsers.py. These
replace keyword-heuristic evaluation for the commands we have ground truth for.

Platform note: `show vni` is NOT a valid command on this platform/firmware. VNI
state comes from `show interface vxlan1` (operational) and
`show running-config interface vxlan1` (intended). Do not call `show vni`.
"""
from __future__ import annotations

import re


def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]


# --------------------------------------------------------------------------
# show running-config interface vxlan1
# --------------------------------------------------------------------------
def parse_vxlan_running_config(text: str) -> dict:
    """-> {source_ip, shutdown, vnis: [{vni, vlan, vtep_peers: [...]}]}"""
    out: dict = {"source_ip": None, "shutdown": None, "vnis": []}
    cur: dict | None = None
    for ln in _lines(text):
        s = ln.strip()
        m = re.match(r"source ip (\S+)", s)
        if m:
            out["source_ip"] = m.group(1); continue
        if s == "no shutdown":
            out["shutdown"] = False; continue
        if s == "shutdown":
            out["shutdown"] = True; continue
        m = re.match(r"vni (\d+)$", s)
        if m:
            cur = {"vni": int(m.group(1)), "vlan": None, "vtep_peers": []}
            out["vnis"].append(cur); continue
        if cur is not None:
            m = re.match(r"vlan (\d+)$", s)
            if m:
                cur["vlan"] = int(m.group(1)); continue
            m = re.match(r"vtep-peer (\S+)", s)
            if m:
                cur["vtep_peers"].append(m.group(1))
    return out


# --------------------------------------------------------------------------
# show interface vxlan1  (operational)
# --------------------------------------------------------------------------
def parse_show_interface_vxlan(text: str) -> dict:
    """-> {oper_up, admin_up, underlay_vrf, udp_port, source_ip,
           vnis: [{vni, routing, vlan, vrf, vtep_peers, origin}]}"""
    out: dict = {"oper_up": None, "admin_up": None, "underlay_vrf": None,
                 "udp_port": None, "source_ip": None, "vnis": []}
    lines = _lines(text)
    for ln in lines:
        s = ln.strip()
        if re.match(r"Interface vxlan1 is ", s):
            out["oper_up"] = s.endswith("up")
        elif s.startswith("Admin state is"):
            out["admin_up"] = s.endswith("up")
        elif s.startswith("Underlay VRF:"):
            out["underlay_vrf"] = s.split(":", 1)[1].strip()
        elif s.startswith("Destination UDP port:"):
            out["udp_port"] = int(s.split(":", 1)[1].strip())
        elif s.startswith("VTEP source IPv4 address:"):
            out["source_ip"] = s.split(":", 1)[1].strip()
    # table rows: after the dashed separator, columns are
    # VNI  Routing  VLAN  VRF  VTEP-Peers  Origin
    in_table = False
    for ln in lines:
        if re.match(r"^-{3,}\s+-{3,}", ln):
            in_table = True; continue
        if in_table:
            cols = ln.split()
            if len(cols) >= 6 and cols[0].isdigit():
                out["vnis"].append({
                    "vni": int(cols[0]), "routing": cols[1],
                    "vlan": None if cols[2] == "--" else int(cols[2]),
                    "vrf": cols[3], "vtep_peers": [cols[4]], "origin": cols[5],
                })
    return out


# --------------------------------------------------------------------------
# show vsx status
# --------------------------------------------------------------------------
def parse_vsx_status(text: str) -> dict:
    out: dict = {"isl_channel": None, "isl_mgmt": None, "config_sync": None,
                 "device_role": None, "platform": None, "software_version": None,
                 "isl_link": None, "system_mac": None, "peer_software": None}
    for ln in _lines(text):
        s = ln.strip()
        if s.startswith("ISL channel"):
            out["isl_channel"] = s.split(":", 1)[1].strip()
        elif s.startswith("ISL mgmt channel"):
            out["isl_mgmt"] = s.split(":", 1)[1].strip()
        elif s.startswith("Config Sync Status"):
            out["config_sync"] = s.split(":", 1)[1].strip()
        else:
            m = re.match(r"ISL link\s+(\S+)\s+(\S+)", s)
            if m:
                out["isl_link"] = m.group(1)
            m = re.match(r"System MAC\s+(\S+)\s+(\S+)", s)
            if m:
                out["system_mac"] = m.group(1)
            m = re.match(r"Platform\s+(\S+)\s+(\S+)", s)
            if m:
                out["platform"] = m.group(1)
            m = re.match(r"Software Version\s+(\S+)\s+(\S+)", s)
            if m:
                out["software_version"] = m.group(1); out["peer_software"] = m.group(2)
            m = re.match(r"Device Role\s+(\S+)\s+(\S+)", s)
            if m:
                out["device_role"] = m.group(1)
    out["isl_in_sync"] = out["isl_channel"] == "In-Sync"
    out["config_in_sync"] = out["config_sync"] == "In-Sync"
    out["software_match"] = (out["software_version"] == out["peer_software"]
                             if out["software_version"] else None)
    return out


# --------------------------------------------------------------------------
# show interface loopback 1
# --------------------------------------------------------------------------
def parse_loopback(text: str) -> dict:
    out: dict = {"name": None, "oper_up": None, "admin_up": None,
                 "vrf": None, "ipv4": None, "mtu": None}
    for ln in _lines(text):
        s = ln.strip()
        m = re.match(r"Interface (loopback\d+) is (\S+)", s)
        if m:
            out["name"] = m.group(1); out["oper_up"] = m.group(2) == "up"
        elif s.startswith("Admin state is"):
            out["admin_up"] = s.endswith("up")
        elif s.startswith("VRF name is"):
            out["vrf"] = s.replace("VRF name is", "").strip()
        else:
            m = re.match(r"IPv4 address (\S+)", s)
            if m:
                out["ipv4"] = m.group(1).split("/")[0]
                out["prefix"] = m.group(1)
            m = re.match(r"MTU (\d+)", s)
            if m:
                out["mtu"] = int(m.group(1))
    return out


# --------------------------------------------------------------------------
# show interface vxlan 1 statistics
# --------------------------------------------------------------------------
_VX_STAT_COLS = ["rx_bytes", "rx_packets", "rx_drops", "tx_bytes", "tx_packets",
                 "tx_drops", "rx_broadcast", "rx_multicast", "tx_broadcast",
                 "tx_multicast", "rx_pause", "tx_pause"]


def parse_vxlan_statistics(text: str) -> dict:
    for ln in _lines(text):
        cols = ln.split()
        if cols and cols[0] == "vxlan1" and len(cols) >= 13:
            vals = [int(c) for c in cols[1:13]]
            return dict(zip(_VX_STAT_COLS, vals))
    return {}


# --------------------------------------------------------------------------
# show spanning-tree mst <n>
# --------------------------------------------------------------------------
def parse_stp_mst(text: str) -> dict:
    out: dict = {"instance": None, "tc_flag": None, "num_tc": None,
                 "last_tc_s": None, "ports": []}
    in_ports = False
    for ln in _lines(text):
        s = ln.strip()
        m = re.match(r"#### MST(\d+)", s)
        if m:
            out["instance"] = int(m.group(1)); continue
        if s.startswith("Topology change flag"):
            out["tc_flag"] = s.split(":", 1)[1].strip() == "True"; continue
        if s.startswith("Number of topology changes"):
            out["num_tc"] = int(s.split(":", 1)[1].strip()); continue
        if s.startswith("Last topology change occurred"):
            m = re.search(r"(\d+)\s+seconds", s)
            if m:
                out["last_tc_s"] = int(m.group(1))
            continue
        if re.match(r"^Port\s+Role\s+State", s):
            in_ports = True; continue
        if re.match(r"^-{3,}\s+-{3,}", s):
            continue
        if in_ports:
            cols = s.split()
            # Port Role State Cost Priority Type... BPDU-Tx BPDU-Rx TCN-Tx TCN-Rx
            if len(cols) >= 9 and re.match(r"\d+/\d+/\d+|lag\d+", cols[0]):
                out["ports"].append({
                    "port": cols[0], "role": cols[1], "state": cols[2],
                    "bpdu_tx": int(cols[-4]), "bpdu_rx": int(cols[-3]),
                    "tcn_tx": int(cols[-2]), "tcn_rx": int(cols[-1]),
                })
            else:
                in_ports = False
    return out


# --------------------------------------------------------------------------
# show interface error-statistics non-zero
# --------------------------------------------------------------------------
def parse_error_statistics(text: str) -> list[dict]:
    """-> [{interface, lag, rx_errors, tx_errors, rx_giants, rx_runts, crc_fcs, collisions}]"""
    rows: list[dict] = []
    for ln in _lines(text):
        s = ln.strip()
        if not s or s.startswith("-") or s.startswith("Interface"):
            continue
        cols = s.split()
        if not cols or not re.match(r"\d+/\d+/\d+|lag\d+", cols[0]):
            continue
        nums = [int(c) for c in cols if c.isdigit()]
        if len(nums) < 6:
            continue
        stats = nums[-6:]
        lag = None
        m = re.search(r"-\s+(lag\d+)", s)
        if m:
            lag = m.group(1)
        rows.append({
            "interface": cols[0], "lag": lag,
            "rx_errors": stats[0], "tx_errors": stats[1], "rx_giants": stats[2],
            "rx_runts": stats[3], "crc_fcs": stats[4], "collisions": stats[5],
        })
    return rows


# --------------------------------------------------------------------------
# show system resource-utilization
# --------------------------------------------------------------------------
def parse_system_resources(text: str) -> dict:
    out: dict = {"cpu_pct": None, "mem_pct": None}
    for ln in _lines(text):
        s = ln.strip()
        m = re.match(r"CPU usage\(%\)\s*:\s*(\d+)", s)
        if m:
            out["cpu_pct"] = int(m.group(1))
        m = re.match(r"Memory usage\(%\)\s*:\s*(\d+)", s)
        if m:
            out["mem_pct"] = int(m.group(1))
    return out
