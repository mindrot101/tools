import time

import pytest
from fastapi.testclient import TestClient


def _wait(client, job_id, tok=None):
    h = {"Authorization": f"Bearer {tok}"} if tok else {}
    for _ in range(60):
        j = client.get(f"/jobs/{job_id}", headers=h).json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


@pytest.fixture
def client():
    import main
    with TestClient(main.app) as c:
        yield c


def _upload(client, pcap_bytes, name="c.pcap"):
    r = client.post("/upload", files={"files": (name, pcap_bytes, "application/octet-stream")})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def test_filter_and_report_and_share(client, pcap_bytes):
    jid = _upload(client, pcap_bytes)
    _wait(client, jid)
    # display filter: only UDP packets (the two DNS frames)
    r = client.get(f"/jobs/{jid}/packets", params={"filter": "proto == UDP"})
    assert r.json()["total"] == 2
    # protocol tag filter
    r = client.get(f"/jobs/{jid}/packets", params={"filter": "protocol == tls"})
    assert r.json()["total"] == 1
    # bad filter -> 400
    assert client.get(f"/jobs/{jid}/packets", params={"filter": "bogus @@ 1"}).status_code == 400
    # HTML report
    rep = client.get(f"/jobs/{jid}/report")
    assert rep.status_code == 200 and "PCAP Analysis Report" in rep.text
    # share -> public read
    tok = client.post(f"/jobs/{jid}/share").json()["share_token"]
    assert client.get(f"/shared/{tok}").json()["id"] == jid
    assert "PCAP Analysis Report" in client.get(f"/shared/{tok}/report").text


def test_diff(client, pcap_bytes):
    a = _upload(client, pcap_bytes, "a.pcap"); _wait(client, a)
    b = _upload(client, pcap_bytes, "b.pcap"); _wait(client, b)
    d = client.get("/diff", params={"a": a, "b": b}).json()
    assert d["similarity"] == 1.0 and d["only_in_a"] == 0 and d["only_in_b"] == 0


def test_chunked_upload(client, pcap_bytes):
    uid = client.post("/uploads/init", data={"filename": "big.pcap"}).json()["upload_id"]
    half = len(pcap_bytes) // 2
    client.post(f"/uploads/{uid}/chunk", content=pcap_bytes[:half])
    client.post(f"/uploads/{uid}/chunk", content=pcap_bytes[half:])
    jid = client.post(f"/uploads/{uid}/complete").json()["job_id"]
    j = _wait(client, jid)
    assert j["summary"]["total_packets"] == 7


def test_iocs_and_saved_filters_and_metrics(client, pcap_bytes):
    assert client.put("/settings/iocs", json={"iocs": "example.com"}).status_code == 200
    jid = _upload(client, pcap_bytes); j = _wait(client, jid)
    assert any(h["indicator"] == "example.com" for h in j["summary"]["ioc_hits"])
    fid = client.post("/filters", json={"name": "udp", "expression": "proto == UDP"}).json()["id"]
    assert any(f["id"] == fid for f in client.get("/filters").json()["filters"])
    m = client.get("/metrics")
    assert m.status_code == 200 and "pcap_jobs" in m.text
