"""Behavioural heuristics computed from accumulated packet metadata."""
import statistics
from typing import Any, Dict, List, Set, Tuple

import settings


def finalize_scans(syn_targets: Dict[str, Dict[str, Set]]) -> List[Dict[str, Any]]:
    """syn_targets[src] = {'ports': set, 'hosts': set} from SYN-only packets."""
    out: List[Dict[str, Any]] = []
    for src, t in syn_targets.items():
        nports, nhosts = len(t["ports"]), len(t["hosts"])
        if nports >= settings.SCAN_PORT_THRESHOLD or nhosts >= settings.SCAN_HOST_THRESHOLD:
            kind = "horizontal (host sweep)" if nhosts >= settings.SCAN_HOST_THRESHOLD else "vertical (port scan)"
            out.append({"src": src, "distinct_ports": nports, "distinct_hosts": nhosts, "kind": kind})
    return sorted(out, key=lambda x: x["distinct_ports"] + x["distinct_hosts"], reverse=True)[:20]


def finalize_beacons(series: Dict[Tuple, List[float]]) -> List[Dict[str, Any]]:
    """series[(src,dst,dport)] = sorted timestamps. Flags regular intervals."""
    out: List[Dict[str, Any]] = []
    for (src, dst, dport), ts in series.items():
        if len(ts) < settings.BEACON_MIN_HITS:
            continue
        gaps = [b - a for a, b in zip(ts, ts[1:]) if b - a >= 0]
        if len(gaps) < 3:
            continue
        mean = statistics.fmean(gaps)
        if mean <= 0:
            continue
        cv = statistics.pstdev(gaps) / mean
        if cv < 0.15:  # highly regular -> beacon-like
            out.append({"src": src, "dst": dst, "dport": dport,
                        "hits": len(ts), "interval_s": round(mean, 3), "regularity": round(1 - cv, 3)})
    return sorted(out, key=lambda x: x["regularity"], reverse=True)[:20]


def summarize_expert(expert: Dict[str, int]) -> List[Dict[str, Any]]:
    labels = {
        "tcp_resets": "TCP connection resets (RST)",
        "retransmissions": "TCP retransmissions",
        "zero_window": "TCP zero-window (receiver stalled)",
        "malformed": "Malformed / unparseable frames",
    }
    return [{"kind": k, "label": labels.get(k, k), "count": v} for k, v in expert.items() if v]
