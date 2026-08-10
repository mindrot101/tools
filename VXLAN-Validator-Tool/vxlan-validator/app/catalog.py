"""
The VXLAN validation catalog for static (non-EVPN) VXLAN on Aruba CX.

Every entry is READ-ONLY: it declares only `show`/`ping`/`traceroute` CLI and
REST GET endpoints. The `scope` drives target fan-out in the runner:
    vtep      -> once per VTEP
    tunnel    -> once per tunnel
    vni       -> once per VNI
    vsxPair   -> once per VSX pair
Severity: critical | high | medium | low.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Test:
    id: str
    category: str
    title: str
    scope: str
    severity: str
    description: str
    cli: list[str]
    remediation: str
    rest: list[str] = field(default_factory=list)
    read_only: bool = True

    def as_dict(self) -> dict:
        return {
            "id": self.id, "category": self.category, "title": self.title,
            "scope": self.scope, "severity": self.severity,
            "description": self.description, "cli": self.cli, "rest": self.rest,
            "remediation": self.remediation, "read_only": self.read_only,
        }


CATALOG: list[Test] = [
    # ---------------- Physical ----------------
    Test("phy-xcvr", "Physical", "Uplink transceivers present and readings healthy", "vtep", "high",
         "Every underlay uplink transceiver must be present with Rx/Tx power and temperature in spec.",
         ["show interface transceiver detail", "show interface | include down"],
         "Reseat or replace out-of-spec optics; confirm compatibility with the CX platform."),
    Test("phy-crc", "Physical", "No CRC / input errors on underlay interfaces", "vtep", "high",
         "Rising CRC/input errors on underlay links corrupt VXLAN frames and cause silent overlay loss.",
         ["show interface | include error", "show interface error-statistics non-zero"],
         "Clean/replace fiber, check patch panels; a single dirty link degrades the whole fabric."),
    Test("phy-speed", "Physical", "Underlay uplink speed / duplex consistency", "vtep", "medium",
         "Underlay uplinks must negotiate the expected speed and full duplex on both ends.",
         ["show interface brief", "show lldp neighbor-info"],
         "Correct speed/duplex config or optic type so both ends match."),

    # ---------------- L2 ----------------
    Test("l2-lag", "L2", "LAG member consistency across underlay bundles", "vtep", "high",
         "All members of an underlay LAG must be up and hashing; a silent member-down halves capacity.",
         ["show lag", "show lacp interfaces"],
         "Bring the missing member up; confirm LACP mode/rate match on the peer."),
    Test("l2-stp", "L2", "No unexpected STP topology changes", "vtep", "medium",
         "Frequent TCNs on VSX/access edges point to flaps that ripple into the overlay.",
         ["show spanning-tree", "show spanning-tree detail | include change"],
         "Locate the flapping port; apply edge-port/BPDU guard where appropriate."),
    Test("l2-storm", "L2", "Broadcast / unknown-unicast storm control below threshold", "vtep", "medium",
         "Storm-control counters near their limit inflate BUM replication load across HER.",
         ["show interface | include storm"],
         "Tune storm-control thresholds; investigate the source of BUM traffic."),
    Test("l2-mst-tc", "L2", "MST topology stable (low recent topology-change rate)", "vtep", "medium",
         "Because static VXLAN rides L2, an unstable spanning tree destabilizes the overlay. Check each MST "
         "instance's topology-change flag and that the last change is not recent / not rapidly incrementing.",
         ["show spanning-tree mst 1", "show spanning-tree mst 2"],
         "Find the flapping port from the per-port TCN counters; apply admin-edge / BPDU guard on host ports "
         "and stabilize the offending link."),

    # ---------------- Underlay ----------------
    Test("und-adj", "Underlay", "Underlay routing adjacencies established", "vtep", "critical",
         "The IGP (OSPF/BGP) carrying VTEP loopbacks must be fully adjacent on every underlay link.",
         ["show ip ospf neighbors", "show bgp ipv4 unicast summary"],
         "Fix the underlay routing session before chasing overlay symptoms."),
    Test("und-reach", "Underlay", "Loopback reachability between all VTEPs", "tunnel", "critical",
         "Each VTEP source loopback must be reachable from every other VTEP in the underlay VRF.",
         ["ping <remote-loopback> vrf default source loopback 1",
          "show ip route <remote-loopback>"],
         "Restore the underlay route to the unreachable loopback; check redistribution and filtering."),
    Test("und-ecmp", "Underlay", "ECMP path symmetry between VTEP pairs", "tunnel", "medium",
         "Asymmetric ECMP hashing can hide a single bad member link behind a mostly-working path.",
         ["show ip route <remote-loopback>", "show ip ecmp"],
         "Confirm equal-cost members are all healthy; a degraded member causes flow-dependent loss."),
    Test("und-latency", "Underlay", "Underlay reachability latency within threshold", "tunnel", "low",
         "Sustained high RTT between loopbacks indicates congestion or a suboptimal path.",
         ["ping <remote-loopback> vrf default source loopback 1 repetitions 20"],
         "Investigate the congested hop; validate QoS on transit interfaces."),

    # ---------------- MTU ----------------
    Test("mtu-hop", "MTU", "Underlay MTU on every hop >= tenant MTU + 50", "tunnel", "critical",
         "Underlay MTU on every hop between two VTEP loopbacks must be at least tenant MTU + 50 (IPv4) "
         "/ +70 (IPv6). Standard target on Aruba CX 10G+ fabrics is 9198.",
         ["ping <remote-loopback> vrf default source loopback 1 size 9000 df-bit",
          "show interface | include MTU"],
         "Raise underlay MTU on every transit interface to at least 9198. Confirm with a DF-bit sweep; "
         "do not rely on PMTUD — VXLAN drops occur at the hardware pipeline before an ICMP unreachable."),
    Test("mtu-uniform", "MTU", "Uniform underlay-facing MTU on each VTEP", "vtep", "high",
         "Every underlay-facing physical interface, LAG, and SVI on a VTEP must have the same MTU. "
         "A single lower-MTU uplink introduces flow-hash-dependent black-holing.",
         ["show interface | include MTU", "show running-config interface | include mtu"],
         "Align MTU across all underlay interfaces. Common misconfig: a rebuilt link left at 1500."),
    Test("mtu-p2p", "MTU", "VTEP-to-VTEP MTU consistency (peer-to-peer)", "tunnel", "critical",
         "Both endpoints of a VXLAN tunnel must agree on underlay MTU. A local 9198 talking to a remote "
         "1500 succeeds on small packets and silently fails on tenant jumbo flows.",
         ["show interface vxlan1", "show interface | include MTU",
          "ping <remote-loopback> vrf default source loopback 1 size 8972 df-bit"],
         "Bring the lower-MTU end up to the fabric standard. If impossible, lower tenant MTU on both "
         "ends so tenant MTU + 50 <= min underlay MTU."),
    Test("mtu-tenant", "MTU", "Tenant MTU respects (underlay MTU - 50) headroom", "vni", "critical",
         "For each VNI, tenant SVI / access-port MTU must be at least 50 bytes less than the smallest "
         "underlay path MTU between any two member VTEPs (70 bytes for IPv6 outer).",
         ["show interface vlan <vlan> | include MTU", "show interface <access-port> | include MTU"],
         "Lower tenant SVI / access-port MTU, or raise underlay MTU. On CX the VXLAN encap overhead is "
         "not subtracted implicitly — you must plan for it."),
    Test("mtu-sweep", "MTU", "DF-bit jumbo sweep succeeds across every tunnel", "tunnel", "critical",
         "An underlay DF-bit ping at size 8972 (== 9000 IP incl. headers) must succeed loopback-to-loopback "
         "on every configured tunnel. Failure at 8972 while 1472 succeeds is the classic mismatch signature.",
         ["ping <remote-loopback> vrf default source loopback 1 size 8972 df-bit repetitions 5",
          "ping <remote-loopback> vrf default source loopback 1 size 1472 df-bit repetitions 5"],
         "Walk the path hop-by-hop with a decreasing DF-bit sweep until you find the interface that drops "
         "the frame; that is the MTU-limiting hop."),
    Test("mtu-baseline", "MTU", "System / global L3 MTU baseline meets fabric standard", "vtep", "high",
         "Aruba CX exposes a system-wide L3 MTU baseline. This must be at or above the fabric standard "
         "(typically 9198) so newly configured interfaces inherit the correct value.",
         ["show running-config | include mtu", "show system"],
         "Set `system mtu <value>` (or platform equivalent) to the fabric standard. Reapply on any "
         "interface configured before the baseline was raised."),
    Test("mtu-icmp", "MTU", "No ICMP unreachable / frag-needed alarms observed", "vtep", "medium",
         "A healthy fabric should not generate frag-needed (Type 3 Code 4) messages. Their presence "
         "indicates tenant traffic hitting an MTU wall somewhere in the underlay path.",
         ["show events -d icmp", "show interface error-statistics non-zero"],
         "Chase the source and destination of the frag-needed. It points directly at the MTU-limiting hop."),

    # ---------------- L4 ----------------
    Test("l4-4789", "L4", "UDP 4789 is not filtered anywhere in the underlay", "vtep", "critical",
         "No underlay-facing ACL, PBR, or firewall on the path may drop UDP/4789 between VTEP loopbacks.",
         ["show access-lists", "show access-lists hitcounts",
          "show running-config | include access-list"],
         "Add explicit permits for UDP 4789 sourced/destined between VTEP loopback subnets on transit ACLs."),
    Test("l4-copp", "L4", "Control-plane policer not dropping legitimate protocol traffic", "vtep", "medium",
         "Aggressive CoPP can drop OSPF/BGP/BFD/ARP under load, causing underlay flaps that look like "
         "VXLAN failures.",
         ["show copp-policy statistics", "show copp-policy"],
         "Investigate any non-zero CoPP drop counter. Rebaseline the policy or increase the specific class rate."),

    # ---------------- VTEP Config ----------------
    Test("vtep-iface", "VTEP Config", "VXLAN interface exists and is admin up", "vtep", "critical",
         "Interface vxlan1 must be present, admin up, and bound to the correct source-interface loopback.",
         ["show interface vxlan1", "show running-config interface vxlan1"],
         "Configure `interface vxlan 1` with `source ip <loopback>` and `no shutdown`. Ensure loopback exists.",
         rest=["/rest/v10.13/system/interfaces/vxlan1"]),
    Test("vtep-udp", "VTEP Config", "UDP port 4789 in use", "vtep", "high",
         "Verify the standard IANA VXLAN UDP destination port is configured on all VTEPs. A mismatch "
         "silently drops encapsulated frames.",
         ["show interface vxlan1"],
         "Align `udp-port 4789` across all peers."),
    Test("vtep-lo", "VTEP Config", "Source-interface loopback consistency", "vsxPair", "high",
         "Both VSX peers must use the same source loopback IP (VSX anycast VTEP) so remote peers see a "
         "single VTEP.",
         ["show interface vxlan1", "show interface loopback 1", "show vsx status"],
         "Ensure both VSX peers advertise the same anycast loopback via `interface vxlan 1 / source ip <anycast-lo>`."),
    Test("vtep-vrf", "VTEP Config", "VXLAN interface bound to correct VRF", "vtep", "high",
         "The VXLAN source loopback must live in the underlay VRF used for encap/decap.",
         ["show interface loopback 1", "show running-config interface loopback 1"],
         "Move the loopback into the underlay VRF (typically default) and re-bind the VXLAN interface."),

    # ---------------- Tunnel State ----------------
    Test("tun-peers", "Tunnel State", "Static peer list matches expected topology", "vtep", "critical",
         "Every remote VTEP loopback expected in the topology inventory must be present in the local "
         "static peer configuration.",
         ["show vxlan vteps", "show running-config interface vxlan1"],
         "Add the missing peer under `interface vxlan 1 / vni <id> / vtep-peer <ip>`. Static VXLAN has no auto-discovery.",
         rest=["/rest/v10.13/system/vxlans"]),
    Test("tun-up", "Tunnel State", "Tunnel operational state up", "tunnel", "critical",
         "Each configured tunnel must be in operational up state with non-zero encap/decap counters over "
         "the sample window.",
         ["show vxlan vteps", "show interface vxlan 1 statistics"],
         "Check underlay reachability, MTU, and that at least one VNI is mapped and admin up on both ends."),
    Test("tun-drops", "Tunnel State", "Tunnel drop counters within threshold", "tunnel", "high",
         "Encap/decap drops should be zero. Non-zero drops indicate MTU, ACL, or hardware-table issues.",
         ["show interface vxlan 1 statistics", "show capacities-status"],
         "Investigate MTU on the underlay path, ACLs at the boundary, and hardware VNI / MAC table utilization."),
    Test("tun-bidir", "Tunnel State", "Bidirectional counter growth (encap AND decap)", "tunnel", "medium",
         "On an active tunnel, both encap and decap counters should be advancing. All-encap-no-decap is "
         "the classic signature of a one-way MTU or ACL problem.",
         ["show interface vxlan 1 statistics"],
         "Sweep MTU with DF-bit in the reverse direction. Check underlay ACLs on the return path."),
    Test("tun-stats", "Tunnel State", "VXLAN tunnel statistics baseline (RX/TX, no drops)", "vtep", "medium",
         "Baseline the vxlan1 interface statistics: RX/TX byte and packet counters and, critically, zero "
         "RX/TX drops. Non-zero vxlan1 drops point straight at MTU or hardware-table pressure.",
         ["show interface vxlan 1 statistics"],
         "If drops are non-zero, correlate with the MTU checks and hardware headroom; the vxlan1 drop "
         "counter is the earliest overlay-loss signal."),

    # ---------------- VNI Membership ----------------
    Test("vni-map", "VNI Membership", "VLAN-to-VNI mapping symmetric across peers", "vni", "critical",
         "For every VNI, all member VTEPs must map the SAME VLAN. Mismatched VLAN<->VNI mapping breaks "
         "tenant isolation. (Note: `show vni` does not exist on 8325/GL.10.13.x — VNI/VLAN mapping is read "
         "from `show interface vxlan1` and the vxlan1 running-config.)",
         ["show interface vxlan1", "show running-config interface vxlan1"],
         "Under `interface vxlan 1 / vni <id>` set the same `vlan <id>` on all member VTEPs."),
    Test("vni-admin", "VNI Membership", "VNI present and VXLAN interface up on all members", "vni", "high",
         "Each member VTEP must have the VNI configured under vxlan1 and the vxlan1 interface admin/oper up. "
         "A missing VNI on one leaf silently blackholes tenant traffic to that leaf.",
         ["show interface vxlan1", "show running-config interface vxlan1"],
         "`interface vxlan 1 / vni <id>` on the affected VTEP; ensure vxlan1 is `no shutdown`."),
    Test("vni-vlan", "VNI Membership", "Tenant VLAN exists and is admin up on all member VTEPs", "vni", "high",
         "The mapped VLAN must exist and be admin up on every member VTEP; otherwise the VNI has no local "
         "L2 domain to encap/decap.",
         ["show vlan", "show running-config vlan <id>"],
         "Create the VLAN and `no shutdown` it on the affected VTEP."),

    # ---------------- MAC Learning ----------------
    Test("mac-remote", "MAC Learning", "Remote MACs learned on each VNI", "vni", "medium",
         "At least one remote-learned MAC per VNI on each VTEP indicates working data-plane learning.",
         ["show mac-address-table vni <id>", "show mac-address-table dynamic vlan <vlan>"],
         "If no remote MACs are learned, check tunnel state, HER peer list, and tenant traffic presence."),
    Test("mac-flap", "MAC Learning", "No MAC flap alarms", "vtep", "high",
         "Repeated MAC moves between local and remote VTEP indicate loops or dual-homed misconfig.",
         ["show events -d mac", "show mac-address-table count"],
         "Check for L2 loops, incorrect VSX ISL trunk config, and duplicate MACs."),

    # ---------------- HER ----------------
    Test("her-flood", "HER", "Head-end replication flood list complete", "vni", "critical",
         "For HER-mode VNIs, every other member VTEP must appear in the flood list on every peer.",
         ["show vxlan flood-list vni <id>"],
         "Add the missing `vtep-peer <ip>` under the VNI on the affected leaf."),

    # ---------------- Data Plane ----------------
    Test("dp-bum", "Data Plane", "BUM flooding delivers to all members", "vni", "high",
         "An ARP broadcast in a VNI must reach every member VTEP (HER flood list or multicast group).",
         ["show vxlan flood-list vni <id>", "show ip mroute"],
         "For HER, ensure every peer is in the flood list. For multicast, check PIM neighbors and the underlay group."),
    Test("dp-ping", "Data Plane", "Tenant end-to-end ping across overlay", "vni", "critical",
         "Ping between test SVIs / hosts in the same VNI across VTEPs.",
         ["ping <remote-tenant-ip> vrf <tenant-vrf> source vlan <vlan>"],
         "If MAC learning and tunnels are up but tenant ping fails, check SVI addressing, ACLs, and active-gateway config."),
    Test("dp-jumbo", "Data Plane", "Tenant jumbo ping (df-bit) across overlay", "vni", "high",
         "A tenant-side DF-bit ping at (planned tenant MTU) must succeed across the overlay. This is the "
         "end-to-end MTU proof.",
         ["ping <remote-tenant-ip> vrf <tenant-vrf> source vlan <vlan> size 8000 df-bit"],
         "If small-packet ping succeeds but jumbo fails, the underlay path MTU is smaller than tenant MTU + 50. "
         "Fix the underlay MTU, not the tenant."),

    # ---------------- QoS ----------------
    Test("qos-dscp", "QoS", "DSCP preservation across encap", "vtep", "medium",
         "Inner tenant DSCP should be copied to the outer VXLAN header (or a documented remark applied).",
         ["show qos dscp-map", "show interface vxlan1"],
         "Configure `qos trust dscp` on tenant-facing ports and confirm outer copy-in / copy-out behavior on the platform."),
    Test("qos-drops", "QoS", "Underlay queue drops within threshold", "vtep", "medium",
         "Sustained tail drops in the underlay egress queues cause tenant-visible loss that is hard to "
         "distinguish from VXLAN misconfig.",
         ["show qos queue-statistics"],
         "Rebalance the QoS scheduler or upsize buffers on the offending interface."),

    # ---------------- Hardware ----------------
    Test("hw-headroom", "Hardware", "Hardware table headroom (MAC / VNI / tunnel)", "vtep", "high",
         "MAC, VNI, and tunnel-endpoint hardware tables should be below 80% utilization to allow growth "
         "and BUM overhead.",
         ["show capacities-status", "show capacities"],
         "Retire unused VNIs / MACs, or scale to a higher-capacity CX platform (e.g. CX 8360 -> 10000)."),
    Test("hw-pipeline", "Hardware", "No forwarding-pipeline error counters", "vtep", "high",
         "ASIC / packet-processor internal drops indicate table overflow, parity, or MTU pipeline drops "
         "that are invisible at interface level.",
         ["show system resource-utilization", "show system error-counters"],
         "Correlate with capacity + MTU tests. If MTU pipeline drops are climbing, follow the mtu-* remediation."),
    Test("hw-cpu", "Hardware", "Control-plane CPU / memory headroom", "vtep", "medium",
         "Sustained high control-plane CPU or memory on a VTEP degrades BUM handling, VSX sync, and REST/SSH "
         "responsiveness. Baseline CPU and memory utilization on every VTEP.",
         ["show system resource-utilization"],
         "Identify the top process from resource-utilization; investigate BUM/ARP storms, oversized tables, "
         "or a runaway daemon. Scale to a higher-capacity CX platform if consistently saturated."),

    # ---------------- ARP ----------------
    Test("arp-agw", "ARP", "Active-gateway ARP responds for tenant SVI", "vni", "high",
         "On VSX active-gateway, ARP for the SVI virtual IP must be answered by the local leaf (not "
         "tromboned).",
         ["show active-gateway", "show arp vrf <tenant-vrf>"],
         "Configure `active-gateway ip <vip> mac <vmac>` under the SVI on both VSX peers, matching MAC across the fabric."),

    # ---------------- VSX ----------------
    Test("vsx-isl", "VSX", "VSX ISL and keepalive both up", "vsxPair", "critical",
         "ISL must be up for data-plane; keepalive must be up to prevent split-brain.",
         ["show vsx status", "show vsx status keepalive"],
         "Physically verify ISL LAG; verify keepalive routing in the mgmt VRF."),
    Test("vsx-sync", "VSX", "VSX config-sync clean (no drift)", "vsxPair", "high",
         "VSX config-sync must show no pending diffs on VXLAN/VNI/VLAN/active-gateway blocks.",
         ["show vsx status config-sync", "show vsx config-consistency"],
         "Reconcile out-of-sync blocks; typically re-apply the config on the primary and let sync push."),
    Test("vsx-anycast", "VSX", "Anycast loopback identical on both peers", "vsxPair", "critical",
         "Both VSX peers must present the same VTEP loopback IP so the remote fabric sees a single logical VTEP.",
         ["show interface loopback 1", "show interface vxlan1"],
         "Match `interface loopback 1 / ip address <anycast>/32` on both peers and reference it in `interface vxlan 1 / source ip`."),
    Test("vsx-splitbrain", "VSX", "Split-brain detection", "vsxPair", "critical",
         "When ISL is down but keepalive is up, the secondary should shut its VSX-attached ports to avoid "
         "split-brain.",
         ["show vsx status", "show vsx brief"],
         "Confirm keepalive path independence from the ISL, and verify secondary shutdown behavior in a controlled test."),
    Test("vsx-islmtu", "VSX", "ISL MTU matches fabric underlay MTU", "vsxPair", "high",
         "The VSX ISL LAG must carry the full underlay MTU. If it is left at 1500 while the rest of the "
         "fabric is 9198, VSX-synced VXLAN traffic breaks under load.",
         ["show lag <isl-lag>", "show interface <isl-member> | include MTU"],
         "Set the ISL LAG and its members to the fabric MTU standard (9198). Confirm both peers are aligned."),
]


CATEGORIES: list[str] = []
for _t in CATALOG:
    if _t.category not in CATEGORIES:
        CATEGORIES.append(_t.category)


def catalog_dict() -> list[dict]:
    return [t.as_dict() for t in CATALOG]


def by_id() -> dict[str, Test]:
    return {t.id: t for t in CATALOG}
