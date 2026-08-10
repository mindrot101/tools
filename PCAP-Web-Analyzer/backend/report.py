"""Self-contained HTML report for a completed job."""
import html
from typing import Any, Dict, List


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    if not rows:
        return "<p class='muted'>None.</p>"
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def html_report(job: Dict[str, Any]) -> str:
    s = job.get("summary") or {}
    pd = s.get("protocol_distribution", {})
    det = s.get("detections", {})
    stat = lambda n, l: f"<div class='stat'><div class='n'>{n}</div><div class='l'>{html.escape(l)}</div></div>"
    stats = "".join([
        stat(s.get("total_packets", 0), "Total packets"),
        stat(s.get("unique_packets", 0), "Unique packets"),
        stat(s.get("duplicates_removed", 0), "Duplicates removed"),
        stat(len(s.get("ioc_hits", [])), "IOC hits"),
        stat(len(det.get("port_scans", [])) + len(det.get("beacons", [])), "Detections"),
    ])
    sections = [
        ("Protocol distribution", _table(["Protocol", "Packets"], [[k.upper(), v] for k, v in pd.items()])),
        ("IOC hits", _table(["Type", "Indicator"], [[h["type"], h["indicator"]] for h in s.get("ioc_hits", [])])),
        ("Port scans", _table(["Source", "Ports", "Hosts", "Kind"],
                              [[d["src"], d["distinct_ports"], d["distinct_hosts"], d["kind"]] for d in det.get("port_scans", [])])),
        ("Beacons", _table(["Source", "Dest", "Port", "Hits", "Interval(s)", "Regularity"],
                           [[d["src"], d["dst"], d["dport"], d["hits"], d["interval_s"], d["regularity"]] for d in det.get("beacons", [])])),
        ("Expert info", _table(["Finding", "Count"], [[e["label"], e["count"]] for e in s.get("expert_info", [])])),
        ("Top talkers", _table(["Host", "Bytes", "Geo"],
                              [[t["host"], t["bytes"], (t.get("geo") or {}).get("country", "")] for t in s.get("top_talkers", [])])),
        ("Conversations", _table(["Endpoint A", "Endpoint B", "Proto", "Packets", "Bytes"],
                                [[c["endpoints"][0], c["endpoints"][1], c["proto"], c["packets"], c["bytes"]] for c in s.get("conversations", [])])),
        ("DNS queries", _table(["Name", "Count"], [[d["name"], d["count"]] for d in s.get("dns_queries", [])])),
        ("TLS servers (SNI)", _table(["Server", "Count"], [[t["server"], t["count"]] for t in s.get("tls_servers", [])])),
        ("JA3 fingerprints", _table(["JA3", "SNI", "Count"], [[j["ja3"], j.get("sni") or "", j["count"]] for j in s.get("ja3_fingerprints", [])])),
        ("HTTP transactions", _table(["Kind", "Method/Status", "Host", "URI/Type"],
                                    [[h.get("kind"), h.get("method") or h.get("status"), h.get("host") or "", h.get("uri") or h.get("content_type") or ""] for h in s.get("http_transactions", [])])),
    ]
    body = "".join(f"<h2>{html.escape(t)}</h2>{c}" for t, c in sections)
    files = html.escape(", ".join(job.get("filenames", [])))
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>PCAP Report {html.escape(job['id'])}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#0f172a}}h1{{margin:0}}
.muted{{color:#64748b}}.stats{{display:flex;gap:14px;flex-wrap:wrap;margin:16px 0}}
.stat{{background:#f1f5f9;border-radius:10px;padding:12px 16px}}.stat .n{{font-size:24px;font-weight:700}}
.stat .l{{color:#64748b;font-size:12px}}table{{border-collapse:collapse;margin:6px 0 18px;width:100%}}
th,td{{border:1px solid #e2e8f0;padding:5px 8px;text-align:left;font-size:13px}}th{{background:#f8fafc}}
h2{{font-size:15px;margin:18px 0 6px;border-bottom:2px solid #38bdf8;padding-bottom:3px}}</style></head>
<body><h1>PCAP Analysis Report</h1><p class='muted'>Job {html.escape(job['id'])} &middot; {files} &middot; dedup: {html.escape(str(job.get('dedup_strategy')))}</p>
<div class='stats'>{stats}</div>{body}</body></html>"""
