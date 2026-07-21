"""Seed fabric inventory for simulated mode. Mirrors the demo topology:
4 VTEPs (2 DCs), 6 VNIs, 4 inter-DC tunnels, 2 VSX pairs. DC2-LEAF-02 carries a
deliberate low-MTU fault so the MTU checks fail realistically."""
from __future__ import annotations

VTEPS = [
    {"id": "DC1-LEAF-01", "hostname": "DC1-LEAF-01", "loopback": "10.255.0.11", "mgmt": "10.0.10.11",
     "dc": "DC1", "vsx_pair": "DC1-VSX", "model": "8360-32Y4C", "mtu": 9198},
    {"id": "DC1-LEAF-02", "hostname": "DC1-LEAF-02", "loopback": "10.255.0.11", "mgmt": "10.0.10.12",
     "dc": "DC1", "vsx_pair": "DC1-VSX", "model": "8360-32Y4C", "mtu": 9198},
    {"id": "DC2-LEAF-01", "hostname": "DC2-LEAF-01", "loopback": "10.255.0.21", "mgmt": "10.0.20.11",
     "dc": "DC2", "vsx_pair": "DC2-VSX", "model": "8360-32Y4C", "mtu": 9198},
    {"id": "DC2-LEAF-02", "hostname": "DC2-LEAF-02", "loopback": "10.255.0.21", "mgmt": "10.0.20.12",
     "dc": "DC2", "vsx_pair": "DC2-VSX", "model": "8360-32Y4C", "mtu": 1500},  # fault
]

VNIS = [
    {"id": "10100", "vni": 10100, "vlan": 100, "tenant": "Corp",   "bum": "HER"},
    {"id": "10200", "vni": 10200, "vlan": 200, "tenant": "Corp",   "bum": "HER"},
    {"id": "10300", "vni": 10300, "vlan": 300, "tenant": "Guest",  "bum": "HER"},
    {"id": "10400", "vni": 10400, "vlan": 400, "tenant": "IoT",    "bum": "HER"},
    {"id": "10500", "vni": 10500, "vlan": 500, "tenant": "OT",     "bum": "HER"},
    {"id": "10600", "vni": 10600, "vlan": 600, "tenant": "Legacy", "bum": "HER"},
]

TUNNELS = [
    {"id": "DC1-LEAF-01__DC2-LEAF-01", "src": "DC1-LEAF-01", "dst": "DC2-LEAF-01",
     "src_lo": "10.255.0.11", "dst_lo": "10.255.0.21"},
    {"id": "DC1-LEAF-01__DC2-LEAF-02", "src": "DC1-LEAF-01", "dst": "DC2-LEAF-02",
     "src_lo": "10.255.0.11", "dst_lo": "10.255.0.21"},
    {"id": "DC1-LEAF-02__DC2-LEAF-01", "src": "DC1-LEAF-02", "dst": "DC2-LEAF-01",
     "src_lo": "10.255.0.11", "dst_lo": "10.255.0.21"},
    {"id": "DC1-LEAF-02__DC2-LEAF-02", "src": "DC1-LEAF-02", "dst": "DC2-LEAF-02",
     "src_lo": "10.255.0.11", "dst_lo": "10.255.0.21"},
]

VSX_PAIRS = [
    {"id": "DC1-VSX", "primary": "DC1-LEAF-01", "secondary": "DC1-LEAF-02", "anycast_lo": "10.255.0.11"},
    {"id": "DC2-VSX", "primary": "DC2-LEAF-01", "secondary": "DC2-LEAF-02", "anycast_lo": "10.255.0.21"},
]


def seed_all() -> dict:
    return {"vtep": VTEPS, "vni": VNIS, "tunnel": TUNNELS, "vsx_pair": VSX_PAIRS}
