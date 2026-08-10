import io
import time

import dpkt
import pytest

import protocol_analyzer as pa
from pcap_processor import process_files


def test_dissect_dns_and_tls(pcap_bytes):
    r = dpkt.pcap.Reader(io.BytesIO(pcap_bytes))
    frames = [dpkt.ethernet.Ethernet(buf) for _, buf in r]
    dns = pa.dissect(frames[0], 100)
    assert any(p["type"] == "dns" for p in dns["protocols"])
    tls = pa.dissect(frames[4], 100)
    tls_proto = next(p for p in tls["protocols"] if p["type"] == "tls")
    assert tls_proto["sni"] == "example.com"


def test_http_request_response():
    assert pa.analyze_http(b"GET /x HTTP/1.1\r\nHost: h\r\n\r\n")["method"] == "GET"
    assert pa.analyze_http(b"HTTP/1.1 200 OK\r\n\r\n")["status"] == "200"
    assert pa.analyze_http(b"not http") is None


def test_content_dedup_keeps_distinct_flow_packets(tmp_path):
    """The original 5-tuple hash collapsed a whole flow to one packet."""
    buf = io.BytesIO()
    w = dpkt.pcap.Writer(buf)
    import socket
    for i in range(6):
        ip = dpkt.ip.IP(src=socket.inet_aton("10.0.0.1"), dst=socket.inet_aton("10.0.0.2"),
                        p=dpkt.ip.IP_PROTO_TCP)
        ip.data = dpkt.tcp.TCP(sport=1111, dport=80, seq=i, data=f"payload-{i}".encode())
        ip.len = len(bytes(ip))
        e = dpkt.ethernet.Ethernet(type=dpkt.ethernet.ETH_TYPE_IP); e.data = ip
        w.writepkt(bytes(e), ts=1000.0 + i)
    p = tmp_path / "flow.pcap"
    p.write_bytes(buf.getvalue())
    out = process_files([p])
    assert out["total_packets"] == 6
    assert out["unique_packets"] == 6           # was 1 under the old logic
    assert out["duplicates_removed"] == 0


def test_process_full_capture(tmp_path, pcap_bytes):
    p = tmp_path / "c.pcap"
    p.write_bytes(pcap_bytes)
    out = process_files([p])
    assert out["total_packets"] == 7
    assert out["unique_packets"] == 6           # the duplicate DNS packet removed
    assert out["duplicates_removed"] == 1
    dist = out["protocol_distribution"]
    assert dist.get("dns") == 1 and dist.get("tls") == 1
    assert dist.get("arp") == 1 and dist.get("icmp") == 1
    txns = out["http_transactions"]
    assert txns and txns[0]["method"] == "GET" and txns[0]["host"] == "example.com"
    assert any(t["server"] == "example.com" for t in out["tls_servers"])
    assert any(q["name"] == "example.com" for q in out["dns_queries"])


def test_api_flow(tmp_path, pcap_bytes):
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as client:
        resp = client.post("/upload", files={"files": ("c.pcap", pcap_bytes, "application/octet-stream")})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        for _ in range(50):
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        assert job["status"] == "done", job
        assert job["summary"]["unique_packets"] == 6
        pk = client.get(f"/jobs/{job_id}/packets", params={"limit": 10}).json()
        assert pk["total"] == 7 and len(pk["packets"]) == 7
        csv_resp = client.get(f"/jobs/{job_id}/download", params={"format": "csv"})
        assert csv_resp.status_code == 200 and "idx,ts,src" in csv_resp.text
        assert client.post("/upload", files={"files": ("bad.pcap", b"nothtml", "x")}).status_code == 400


def _write(tmp_path, frames, name="x.pcap"):
    buf = io.BytesIO()
    w = dpkt.pcap.Writer(buf)
    for i, fr in enumerate(frames):
        w.writepkt(fr, ts=1000.0 + i)
    p = tmp_path / name
    p.write_bytes(buf.getvalue())
    return p


def _syn(src, dst, dport):
    import socket
    ip = dpkt.ip.IP(src=socket.inet_aton(src), dst=socket.inet_aton(dst), p=dpkt.ip.IP_PROTO_TCP)
    ip.data = dpkt.tcp.TCP(sport=44444, dport=dport, flags=dpkt.tcp.TH_SYN, seq=1)
    ip.len = len(bytes(ip))
    e = dpkt.ethernet.Ethernet(type=dpkt.ethernet.ETH_TYPE_IP); e.data = ip
    return bytes(e)


def test_ja3_and_iocs(tmp_path, pcap_bytes):
    p = tmp_path / "c.pcap"; p.write_bytes(pcap_bytes)
    out = process_files([p], iocs_text="example.com\n10.0.0.2")
    assert out["ja3_fingerprints"] and len(out["ja3_fingerprints"][0]["ja3"]) == 32
    kinds = {(h["type"], h["indicator"]) for h in out["ioc_hits"]}
    assert ("domain", "example.com") in kinds
    assert ("ip", "10.0.0.2") in kinds


def test_port_scan_detection(tmp_path):
    frames = [_syn("10.0.0.9", "10.0.0.10", d) for d in range(1, 61)]
    out = process_files([_write(tmp_path, frames)])
    scans = out["detections"]["port_scans"]
    assert scans and scans[0]["src"] == "10.0.0.9" and scans[0]["distinct_ports"] >= 50


def test_retransmission_expert(tmp_path):
    import socket
    def seg():
        ip = dpkt.ip.IP(src=socket.inet_aton("10.0.0.1"), dst=socket.inet_aton("10.0.0.2"), p=dpkt.ip.IP_PROTO_TCP)
        ip.data = dpkt.tcp.TCP(sport=1234, dport=22, seq=5000, flags=dpkt.tcp.TH_ACK, data=b"hello")
        ip.len = len(bytes(ip))
        e = dpkt.ethernet.Ethernet(type=dpkt.ethernet.ETH_TYPE_IP); e.data = ip
        return bytes(e)
    out = process_files([_write(tmp_path, [seg(), seg()], "retx.pcap")], dedup="none")
    labels = {e["kind"]: e["count"] for e in out["expert_info"]}
    assert labels.get("retransmissions", 0) >= 1
