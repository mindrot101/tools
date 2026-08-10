"""Protocol dissection for a single parsed link-layer frame.

Fixes vs. the original:
  * analyzers now receive the IP layer, not the Ethernet frame;
  * HTTP uses dpkt.http.Request/Response (dpkt.http.HTTP never existed);
  * TLS SNI is parsed directly from ClientHello bytes (no fragile dpkt.ssl deps);
  * exceptions are narrowed so real bugs surface instead of being swallowed.
"""
import socket
from typing import Any, Dict, List, Optional

import dpkt

import ja3

DNS_PORTS = {53, 5353}
HTTP_PORTS = {80, 8080, 8000, 8888, 3128}
TLS_PORTS = {443, 8443, 993, 995, 465, 990}
DHCP_PORTS = {67, 68}

_TLS_VERSIONS = {
    0x0300: "SSL 3.0", 0x0301: "TLS 1.0", 0x0302: "TLS 1.1",
    0x0303: "TLS 1.2", 0x0304: "TLS 1.3",
}
_PARSE_ERRORS = (dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError, IndexError, ValueError, KeyError)


def ip_to_str(b: bytes) -> str:
    try:
        if len(b) == 16:
            return socket.inet_ntop(socket.AF_INET6, b)
        return socket.inet_ntoa(b)
    except (OSError, ValueError):
        return "?"


def _decode(v: Any) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    return str(v)


def analyze_dns(payload: bytes) -> Optional[Dict[str, Any]]:
    try:
        dns = dpkt.dns.DNS(payload)
    except _PARSE_ERRORS:
        return None
    is_response = bool(dns.qr) if hasattr(dns, "qr") else (dns.op == dpkt.dns.DNS_OP_QUERY)
    result: Dict[str, Any] = {
        "type": "dns", "id": dns.id, "is_response": bool(dns.qr),
        "questions": [], "answers": [],
    }
    for q in dns.qd:
        result["questions"].append({
            "name": _decode(q.name),
            "type": dpkt.dns.__dict__.get("DNS_" + str(q.type), q.type),
        })
    for rr in dns.an:
        ans: Dict[str, Any] = {"name": _decode(rr.name), "ttl": getattr(rr, "ttl", None)}
        if rr.type == dpkt.dns.DNS_A and hasattr(rr, "ip"):
            ans["address"] = ip_to_str(rr.ip)
        elif rr.type == dpkt.dns.DNS_AAAA and hasattr(rr, "ip6"):
            ans["address"] = ip_to_str(rr.ip6)
        elif rr.type == dpkt.dns.DNS_CNAME:
            ans["cname"] = _decode(getattr(rr, "cname", rr.rdata))
        elif rr.type == dpkt.dns.DNS_NS:
            ans["ns"] = _decode(getattr(rr, "nsname", rr.rdata))
        elif rr.type == dpkt.dns.DNS_PTR:
            ans["ptr"] = _decode(getattr(rr, "ptrname", rr.rdata))
        result["answers"].append(ans)
    return result


def analyze_http(payload: bytes) -> Optional[Dict[str, Any]]:
    if not payload:
        return None
    try:
        req = dpkt.http.Request(payload)
        return {
            "type": "http", "kind": "request",
            "method": req.method, "uri": req.uri, "version": req.version,
            "host": req.headers.get("host"),
        }
    except _PARSE_ERRORS:
        pass
    try:
        resp = dpkt.http.Response(payload)
        return {
            "type": "http", "kind": "response",
            "status": resp.status, "reason": _decode(resp.reason), "version": resp.version,
        }
    except _PARSE_ERRORS:
        return None


def parse_sni(payload: bytes) -> Optional[str]:
    """Extract SNI from a TLS ClientHello without external deps."""
    try:
        if len(payload) < 6 or payload[0] != 0x16:  # not a handshake record
            return None
        hs = payload[5:]
        if not hs or hs[0] != 0x01:  # not ClientHello
            return None
        i = 4 + 2 + 32  # handshake header + version + random
        sid_len = hs[i]; i += 1 + sid_len
        cs_len = int.from_bytes(hs[i:i + 2], "big"); i += 2 + cs_len
        comp_len = hs[i]; i += 1 + comp_len
        ext_total = int.from_bytes(hs[i:i + 2], "big"); i += 2
        end = min(len(hs), i + ext_total)
        while i + 4 <= end:
            etype = int.from_bytes(hs[i:i + 2], "big")
            elen = int.from_bytes(hs[i + 2:i + 4], "big")
            i += 4
            if etype == 0x0000:  # server_name
                sn = hs[i:i + elen]
                if len(sn) >= 5:
                    nlen = int.from_bytes(sn[3:5], "big")
                    return sn[5:5 + nlen].decode("utf-8", errors="ignore") or None
                return None
            i += elen
    except (IndexError, ValueError):
        return None
    return None


def analyze_tls(payload: bytes) -> Optional[Dict[str, Any]]:
    if len(payload) < 3 or payload[0] not in (0x14, 0x15, 0x16, 0x17):
        return None
    version = int.from_bytes(payload[1:3], "big")
    result: Dict[str, Any] = {
        "type": "tls",
        "version": _TLS_VERSIONS.get(version, hex(version)),
        "is_handshake": payload[0] == 0x16,
    }
    ch = ja3.parse_client_hello(payload)
    if ch:
        if ch["sni"]:
            result["sni"] = ch["sni"]
        result.update(ja3.ja3(ch))
    else:
        sni = parse_sni(payload)
        if sni:
            result["sni"] = sni
    return result


def analyze_dhcp(payload: bytes) -> Optional[Dict[str, Any]]:
    try:
        dhcp = dpkt.dhcp.DHCP(payload)
    except _PARSE_ERRORS:
        return None
    msg_type = None
    for opt, val in getattr(dhcp, "opts", []):
        if opt == dpkt.dhcp.DHCP_OPT_MSGTYPE and val:
            msg_type = val[0]
    return {"type": "dhcp", "op": dhcp.op, "msg_type": msg_type,
            "yiaddr": ip_to_str(dhcp.yiaddr.to_bytes(4, "big")) if dhcp.yiaddr else None}


def analyze_icmp(icmp: Any) -> Dict[str, Any]:
    return {"type": "icmp", "icmp_type": getattr(icmp, "type", None),
            "code": getattr(icmp, "code", None)}


def dissect(eth: Any, seg_len: int) -> Dict[str, Any]:
    """Return a normalized packet record with a list of detected protocols."""
    info: Dict[str, Any] = {
        "src": "", "dst": "", "proto": "OTHER",
        "sport": 0, "dport": 0, "length": seg_len, "protocols": [],
    }
    protos: List[Dict[str, Any]] = info["protocols"]

    # ---- ARP (L2) ----
    if isinstance(getattr(eth, "data", None), dpkt.arp.ARP):
        arp = eth.data
        info.update(src=ip_to_str(arp.spa), dst=ip_to_str(arp.tpa), proto="ARP")
        protos.append({"type": "arp", "op": arp.op})
        return info

    ip = getattr(eth, "data", None)
    if not isinstance(ip, (dpkt.ip.IP, dpkt.ip6.IP6)):
        return info

    is_v6 = isinstance(ip, dpkt.ip6.IP6)
    info["src"] = ip_to_str(ip.src)
    info["dst"] = ip_to_str(ip.dst)
    proto_num = ip.nxt if is_v6 else ip.p
    l4 = ip.data

    if isinstance(l4, dpkt.tcp.TCP):
        info.update(proto="TCP", sport=l4.sport, dport=l4.dport)
        ports = {l4.sport, l4.dport}
        payload = bytes(l4.data)
        if payload:
            if ports & HTTP_PORTS:
                r = analyze_http(payload)
                if r:
                    protos.append(r)
            if ports & TLS_PORTS:
                r = analyze_tls(payload)
                if r:
                    protos.append(r)
            if ports & DNS_PORTS and len(payload) > 2:
                r = analyze_dns(payload[2:])  # TCP DNS has a 2-byte length prefix
                if r:
                    protos.append(r)
    elif isinstance(l4, dpkt.udp.UDP):
        info.update(proto="UDP", sport=l4.sport, dport=l4.dport)
        ports = {l4.sport, l4.dport}
        payload = bytes(l4.data)
        if ports & DNS_PORTS:
            r = analyze_dns(payload)
            if r:
                protos.append(r)
        if ports & DHCP_PORTS:
            r = analyze_dhcp(payload)
            if r:
                protos.append(r)
    elif isinstance(l4, (dpkt.icmp.ICMP, dpkt.icmp6.ICMP6)):
        info["proto"] = "ICMP" if not is_v6 else "ICMPv6"
        protos.append(analyze_icmp(l4))
    else:
        info["proto"] = {1: "ICMP", 6: "TCP", 17: "UDP", 58: "ICMPv6"}.get(proto_num, str(proto_num))

    return info
