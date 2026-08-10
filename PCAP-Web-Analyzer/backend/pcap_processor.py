"""Streaming PCAP/PCAPNG processing: dedup, protocol stats, detections, IOC/GeoIP."""
import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import dpkt

import detect
import geoip
import ioc as ioc_mod
import settings
import streams
from protocol_analyzer import HTTP_PORTS, dissect

BATCH = 500
MAX_REASSEMBLE_FLOWS = 2000
MAX_FLOW_BYTES = 256 * 1024
MAX_BEACON_KEYS = 5000
MAX_SEG_SEEN = 200_000


def _read(path: Path):
    with open(path, "rb") as f:
        try:
            reader = dpkt.pcapng.Reader(f)
        except (ValueError, dpkt.dpkt.UnpackError):
            f.seek(0)
            reader = dpkt.pcap.Reader(f)
        for ts, buf in reader:
            yield ts, buf


def _parse_frame(buf: bytes):
    try:
        return dpkt.ethernet.Ethernet(buf)
    except (dpkt.dpkt.UnpackError, dpkt.dpkt.NeedData):
        for cls in (dpkt.ip.IP, dpkt.ip6.IP6):
            try:
                wrapper = dpkt.ethernet.Ethernet()
                wrapper.data = cls(buf)
                return wrapper
            except (dpkt.dpkt.UnpackError, dpkt.dpkt.NeedData):
                continue
    return None


def process_files(
    file_paths: List[Path],
    dedup: str = "content",
    time_window: float = 0.0,
    sink: Optional[Callable[[List[tuple]], None]] = None,
    progress: Optional[Callable[[int], None]] = None,
    iocs_text: str = "",
) -> Dict[str, Any]:
    import json as _json
    idx = total = unique = 0
    proto_dist: Dict[str, int] = {}
    talkers: Dict[str, int] = {}
    conversations: Dict[Tuple, Dict[str, int]] = {}
    tls_servers: Dict[str, int] = {}
    dns_names: Dict[str, int] = {}
    ja3_map: Dict[str, Dict[str, Any]] = {}
    seen: Dict[str, float] = {}
    http_flows: Dict[Tuple, List[Tuple[int, bytes]]] = {}
    http_flow_bytes: Dict[Tuple, int] = {}
    syn_targets: Dict[str, Dict[str, set]] = {}
    beacons: Dict[Tuple, List[float]] = {}
    seg_seen: set = set()
    expert = {"tcp_resets": 0, "retransmissions": 0, "zero_window": 0, "malformed": 0}
    seen_ips: set = set()
    seen_domains: set = set()
    batch: List[tuple] = []

    def flush():
        nonlocal batch
        if batch and sink:
            sink(batch)
        batch = []

    for path in file_paths:
        for ts, buf in _read(path):
            total += 1
            eth = _parse_frame(buf)
            if eth is None:
                expert["malformed"] += 1
                continue
            info = dissect(eth, len(buf))

            digest = hashlib.sha1(buf).hexdigest()
            if dedup == "none":
                is_dup = False
            elif time_window and time_window > 0:
                prev = seen.get(digest)
                is_dup = prev is not None and (ts - prev) <= time_window
                seen[digest] = ts
            else:
                is_dup = digest in seen
                if not is_dup:
                    seen[digest] = ts
            if not is_dup:
                unique += 1

            if not is_dup:
                if info["src"]:
                    seen_ips.add(info["src"])
                if info["dst"]:
                    seen_ips.add(info["dst"])
                for p in info["protocols"]:
                    t = p["type"]
                    proto_dist[t] = proto_dist.get(t, 0) + 1
                    if t == "tls":
                        if p.get("sni"):
                            tls_servers[p["sni"]] = tls_servers.get(p["sni"], 0) + 1
                            seen_domains.add(p["sni"])
                        if p.get("ja3"):
                            m = ja3_map.setdefault(p["ja3"], {"count": 0, "sni": p.get("sni")})
                            m["count"] += 1
                    elif t == "dns":
                        for q in p.get("questions", []):
                            nm = q.get("name")
                            if nm:
                                dns_names[nm] = dns_names.get(nm, 0) + 1
                                seen_domains.add(nm)
                if info["src"]:
                    talkers[info["src"]] = talkers.get(info["src"], 0) + info["length"]
                if info["dst"]:
                    talkers[info["dst"]] = talkers.get(info["dst"], 0) + info["length"]
                if info["proto"] in ("TCP", "UDP") and info["src"] and info["dst"]:
                    key = tuple(sorted([f"{info['src']}:{info['sport']}",
                                        f"{info['dst']}:{info['dport']}"]) + [info["proto"]])
                    conv = conversations.setdefault(key, {"packets": 0, "bytes": 0})
                    conv["packets"] += 1
                    conv["bytes"] += info["length"]

                l3 = eth.data if isinstance(eth.data, (dpkt.ip.IP, dpkt.ip6.IP6)) else None
                l4 = l3.data if l3 is not None else None
                if isinstance(l4, dpkt.tcp.TCP):
                    flags = l4.flags
                    if flags & dpkt.tcp.TH_RST:
                        expert["tcp_resets"] += 1
                    if (flags & dpkt.tcp.TH_SYN) and not (flags & dpkt.tcp.TH_ACK):
                        tgt = syn_targets.setdefault(info["src"], {"ports": set(), "hosts": set()})
                        tgt["ports"].add(info["dport"])
                        tgt["hosts"].add(info["dst"])
                    if l4.win == 0 and not (flags & dpkt.tcp.TH_RST):
                        expert["zero_window"] += 1
                    if l4.data:
                        sk = (info["src"], info["sport"], info["dst"], info["dport"], l4.seq, len(l4.data))
                        if sk in seg_seen:
                            expert["retransmissions"] += 1
                        elif len(seg_seen) < MAX_SEG_SEEN:
                            seg_seen.add(sk)
                        if ({l4.sport, l4.dport} & HTTP_PORTS):
                            fk = (info["src"], info["sport"], info["dst"], info["dport"])
                            if fk in http_flows or len(http_flows) < MAX_REASSEMBLE_FLOWS:
                                if http_flow_bytes.get(fk, 0) < MAX_FLOW_BYTES:
                                    http_flows.setdefault(fk, []).append((l4.seq, bytes(l4.data)))
                                    http_flow_bytes[fk] = http_flow_bytes.get(fk, 0) + len(l4.data)
                    bk = (info["src"], info["dst"], info["dport"])
                    if bk in beacons or len(beacons) < MAX_BEACON_KEYS:
                        beacons.setdefault(bk, []).append(ts)

            batch.append((
                None, idx, ts, info["src"], info["dst"], info["proto"],
                info["sport"], info["dport"], info["length"],
                _json.dumps([p["type"] for p in info["protocols"]]),
                1 if is_dup else 0, digest,
            ))
            idx += 1
            if len(batch) >= BATCH:
                flush()
                if progress:
                    progress(idx)
    flush()
    if progress:
        progress(idx)

    http_transactions, extracted = streams.reassemble_http(http_flows, extract=settings.EXTRACT_FILES)

    top_talkers = sorted(({"host": h, "bytes": b} for h, b in talkers.items()),
                         key=lambda x: x["bytes"], reverse=True)[:10]
    if geoip.available():
        for t in top_talkers:
            geo = geoip.lookup(t["host"])
            if geo:
                t["geo"] = geo
    top_convs = sorted(({"endpoints": list(k[:2]), "proto": k[2], **v}
                        for k, v in conversations.items()),
                       key=lambda x: x["bytes"], reverse=True)[:20]

    ioc_hits: List[Dict[str, str]] = []
    if iocs_text.strip():
        ioc_hits = ioc_mod.match(ioc_mod.parse_iocs(iocs_text), seen_ips, seen_domains)

    return {
        "total_packets": total,
        "unique_packets": unique,
        "duplicates_removed": total - unique,
        "dedup_strategy": dedup,
        "time_window": time_window,
        "protocol_distribution": proto_dist,
        "tls_servers": sorted(({"server": k, "count": v} for k, v in tls_servers.items()),
                              key=lambda x: x["count"], reverse=True)[:20],
        "dns_queries": sorted(({"name": k, "count": v} for k, v in dns_names.items()),
                              key=lambda x: x["count"], reverse=True)[:20],
        "ja3_fingerprints": sorted(({"ja3": k, **v} for k, v in ja3_map.items()),
                                   key=lambda x: x["count"], reverse=True)[:20],
        "http_transactions": http_transactions,
        "extracted_objects": extracted,
        "top_talkers": top_talkers,
        "conversations": top_convs,
        "detections": {
            "port_scans": detect.finalize_scans(syn_targets),
            "beacons": detect.finalize_beacons(beacons),
        },
        "expert_info": detect.summarize_expert(expert),
        "ioc_hits": ioc_hits,
        "geoip_enabled": geoip.available(),
    }
