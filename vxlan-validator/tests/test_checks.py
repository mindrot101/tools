"""Verify parser-backed check evaluators against the real 8325 capture."""
import os
import re

from app import checks

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "CORE_8325.txt")


def _sections():
    text = open(FIXTURE).read()
    parts, cur, buf = {}, None, []
    for ln in text.split("\n"):
        m = re.match(r"S0099CORE001-1#\s*(.+)", ln)
        if m:
            if cur is not None:
                parts[cur] = "\n".join(buf)
            cur, buf = m.group(1).strip(), []
        else:
            buf.append(ln)
    if cur is not None:
        parts[cur] = "\n".join(buf)
    return parts


S = _sections()


def _outs(*cmd_subs):
    """Build a {command: output} dict the evaluators expect, using normalized
    command keys the _find() substring match will hit."""
    out = {}
    mapping = {
        "show interface vxlan1": "show interface vxlan1",
        "vsx status": "show vsx status",
        "error-statistics": "error-statistics non-zero",
        "resource-utilization": "show system resource-utilization",
        "vxlan 1 statistics": "show interface vxlan 1 statistics",
    }
    for key, sub in mapping.items():
        for k, v in S.items():
            if sub in k:
                out[key] = v
    return out


OUTS = _outs()


def test_vtep_iface_pass():
    status, detail = checks.eval_vtep_iface(OUTS)
    assert status == "pass" and "up" in detail


def test_vtep_udp_pass():
    status, _ = checks.eval_vtep_udp(OUTS)
    assert status == "pass"


def test_vsx_isl_pass():
    status, detail = checks.eval_vsx_isl(OUTS)
    assert status == "pass" and "primary" in detail


def test_vsx_sync_pass():
    status, _ = checks.eval_vsx_sync(OUTS)
    assert status == "pass"  # config In-Sync + software match


def test_crc_fail_on_lag23():
    status, detail = checks.eval_crc(OUTS)
    assert status == "fail"
    assert "1/1/23" in detail and "887" in detail  # real error caught


def test_cpu_pass():
    status, detail = checks.eval_cpu(OUTS)
    assert status == "pass" and "CPU 3%" in detail


def test_tun_stats_pass():
    status, _ = checks.eval_tun_stats(OUTS)
    assert status == "pass"  # all counters zero, no drops


def test_stp_stable_on_real_capture():
    stp = {}
    for k, v in S.items():
        if "spanning-tree mst 1" in k:
            stp["show spanning-tree mst 1"] = v
        elif "spanning-tree mst 2" in k:
            stp["show spanning-tree mst 2"] = v
    status, detail = checks.eval_stp(stp)
    assert status == "pass"           # last change ~88 days ago = stable
    assert "disabled port" in detail  # notes 1/1/26, lag30 admin-disabled


def test_stp_flags_recent_change():
    recent = {"show spanning-tree mst 1": (
        "#### MST1\n"
        "Port           Role           State      Cost  Priority  Type  BPDU-Tx BPDU-Rx TCN-Tx TCN-Rx\n"
        "-------------- -------------- ---------- ----- --------- ----- ------- ------- ------ ------\n"
        "1/1/2          Designated     Forwarding 2000  128       P2P   100     0       0      0\n"
        "Topology change flag          : True\n"
        "Number of topology changes    : 999\n"
        "Last topology change occurred : 42 seconds ago\n")}
    status, detail = checks.eval_stp(recent)
    assert status == "fail" and "42s ago" in detail


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"  PASS {fn.__name__}")
        except Exception:
            print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"{passed}/{len(fns)} check tests passed")
