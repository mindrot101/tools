"""Golden-dataset tests: run parsers against real 8325 (GL.10.13.1040) output."""
import os
import re

from app import parsers

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "CORE_8325.txt")


def _sections() -> dict:
    """Split the capture into {command: output_text} by the CLI prompt lines."""
    text = open(FIXTURE).read()
    parts, cur_cmd, buf = {}, None, []
    for ln in text.split("\n"):
        m = re.match(r"S0099CORE001-1#\s*(.+)", ln)
        if m:
            if cur_cmd is not None:
                parts[cur_cmd] = "\n".join(buf)
            cur_cmd, buf = m.group(1).strip(), []
        else:
            buf.append(ln)
    if cur_cmd is not None:
        parts[cur_cmd] = "\n".join(buf)
    return parts


S = _sections()


def _get(substr):
    for k, v in S.items():
        if substr in k:
            return v
    raise KeyError(substr)


def test_vxlan_running_config():
    r = parsers.parse_vxlan_running_config(_get("running-config interface vxlan1"))
    assert r["source_ip"] == "10.15.99.3"
    assert r["shutdown"] is False
    assert len(r["vnis"]) == 13
    v100 = next(v for v in r["vnis"] if v["vni"] == 100)
    assert v100["vlan"] == 100 and v100["vtep_peers"] == ["10.15.102.3"]
    v703 = next(v for v in r["vnis"] if v["vni"] == 703)
    assert v703["vlan"] is None  # routing VNI, no vlan line
    peers = {p for v in r["vnis"] for p in v["vtep_peers"]}
    assert peers == {"10.15.102.3", "10.15.1.3", "10.15.120.3"}


def test_show_interface_vxlan():
    r = parsers.parse_show_interface_vxlan(_get("show interface vxlan1"))
    assert r["oper_up"] and r["admin_up"]
    assert r["underlay_vrf"] == "default"
    assert r["udp_port"] == 4789
    assert r["source_ip"] == "10.15.99.3"
    assert len(r["vnis"]) == 13
    assert next(v for v in r["vnis"] if v["vni"] == 703)["vlan"] is None


def test_vsx_status():
    r = parsers.parse_vsx_status(_get("show vsx status"))
    assert r["isl_in_sync"] and r["config_in_sync"]
    assert r["device_role"] == "primary"
    assert r["platform"] == "8325"
    assert r["software_version"] == "GL.10.13.1040"
    assert r["isl_link"] == "lag256"
    assert r["software_match"] is True


def test_loopback():
    r = parsers.parse_loopback(_get("show interface loopback 1"))
    assert r["name"] == "loopback1"
    assert r["oper_up"] and r["admin_up"]
    assert r["vrf"] == "default"
    assert r["ipv4"] == "10.15.99.3"
    assert r["prefix"] == "10.15.99.3/32"
    assert r["mtu"] == 1500  # loopback MTU is normally 1500 — must NOT be flagged


def test_vxlan_statistics():
    r = parsers.parse_vxlan_statistics(_get("show interface vxlan 1 statistics"))
    assert r["rx_bytes"] == 0 and r["tx_drops"] == 0
    assert set(r) >= {"rx_bytes", "tx_bytes", "rx_drops", "tx_drops"}


def test_stp_mst():
    r = parsers.parse_stp_mst(_get("spanning-tree mst 1"))
    assert r["instance"] == 1
    assert r["tc_flag"] is True
    assert r["num_tc"] == 245
    assert r["last_tc_s"] == 7642213
    assert len(r["ports"]) >= 15
    p26 = next(p for p in r["ports"] if p["port"] == "1/1/26")
    assert p26["state"] == "Down" and p26["role"] == "Disabled"
    lag256 = next(p for p in r["ports"] if p["port"] == "lag256")
    assert lag256["tcn_rx"] == 6


def test_error_statistics():
    rows = parsers.parse_error_statistics(_get("error-statistics non-zero"))
    assert rows, "should find at least one non-zero error interface"
    r23 = next(r for r in rows if r["interface"] == "1/1/23")
    assert r23["lag"] == "lag23"
    assert r23["crc_fcs"] == 887 and r23["rx_errors"] == 887


def test_system_resources():
    r = parsers.parse_system_resources(_get("show system resource-utilization"))
    assert r["cpu_pct"] == 3
    assert r["mem_pct"] == 28


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"  PASS {fn.__name__}")
        except Exception:
            print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"{passed}/{len(fns)} parser tests passed")
