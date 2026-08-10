"""Agent discovery test: drive the real walk logic with the captured 8325 output
instead of a live switch, and verify it assembles correct inventory."""
import os
import re

from app.discovery.base import PROBE_CLI, AgentDiscovery

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


def _stub_runner(host, cmds, log):
    # Map the probe commands to the captured output, regardless of exact spacing.
    def find(sub):
        for k, v in S.items():
            if sub in k:
                return v
        return ""
    out = {}
    for c in cmds:
        log(f"{host} $ {c}")
        if "running-config interface vxlan1" in c:
            out[c] = find("running-config interface vxlan1")
        elif "vsx status" in c:
            out[c] = find("show vsx status")
        elif "loopback 1" in c:
            out[c] = find("show interface loopback 1")
    return out


def test_agent_walk_assembles_inventory():
    disc = AgentDiscovery({"host": "10.15.99.3", "username": "svc", "password": "x"})
    disc._runner = _stub_runner
    log = []
    found = disc.walk("10.15.99.3", "peers", log.append)

    assert len(found["vtep"]) == 1
    vtep = found["vtep"][0]
    assert vtep["loopback"] == "10.15.99.3"
    assert vtep["platform"] == "8325"
    assert vtep["vsx_role"] == "primary"
    assert vtep["software"] == "GL.10.13.1040"

    assert len(found["vni"]) == 13
    v703 = next(v for v in found["vni"] if v["vni"] == 703)
    assert v703["vlan"] is None

    tunnels = {t["dst"] for t in found["tunnel"]}
    assert tunnels == {"10.15.102.3", "10.15.1.3", "10.15.120.3"}

    assert len(found["vsx_pair"]) == 1
    assert found["vsx_pair"][0]["system_mac"] == "02:01:00:00:01:00"


if __name__ == "__main__":
    test_agent_walk_assembles_inventory()
    print("discovery assembly test passed")
