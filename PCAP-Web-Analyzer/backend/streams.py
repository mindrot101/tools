"""HTTP transaction reassembly with chunked/gzip decoding and object extraction."""
import gzip
import hashlib
import os
import zlib
from typing import Any, Dict, List, Optional, Tuple

import dpkt

import settings

MAX_BODY = 4 * 1024 * 1024


def _decode_body(headers: Dict[str, str], body: bytes) -> bytes:
    te = headers.get("transfer-encoding", "").lower()
    if "chunked" in te:
        out, i = bytearray(), 0
        while i < len(body):
            nl = body.find(b"\r\n", i)
            if nl == -1:
                break
            try:
                size = int(body[i:nl].split(b";")[0], 16)
            except ValueError:
                break
            if size == 0:
                break
            start = nl + 2
            out += body[start:start + size]
            i = start + size + 2
        body = bytes(out)
    ce = headers.get("content-encoding", "").lower()
    try:
        if "gzip" in ce:
            body = gzip.decompress(body)
        elif "deflate" in ce:
            body = zlib.decompress(body)
    except (OSError, zlib.error):
        pass
    return body[:MAX_BODY]


def reassemble_http(flows: Dict[Tuple, List[Tuple[int, bytes]]],
                    extract: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (transactions, extracted_objects) from retained HTTP flow payloads."""
    transactions: List[Dict[str, Any]] = []
    objects: List[Dict[str, Any]] = []
    if extract:
        os.makedirs(settings.EXTRACT_DIR, exist_ok=True)

    for (src, sport, dst, dport), segs in flows.items():
        segs.sort(key=lambda s: s[0])
        stream = b"".join(s[1] for s in segs)
        offset = 0
        for _ in range(50):
            chunk = stream[offset:]
            if not chunk:
                break
            try:
                if chunk[:4] in (b"HTTP",):
                    msg = dpkt.http.Response(chunk)
                    headers = {k.lower(): v for k, v in msg.headers.items()}
                    body = _decode_body(headers, bytes(msg.body))
                    entry = {"kind": "response", "src": src, "dst": dst, "sport": sport,
                             "dport": dport, "status": msg.status, "reason": str(msg.reason),
                             "content_type": headers.get("content-type"), "body_len": len(body)}
                    if body:
                        digest = hashlib.sha256(body).hexdigest()
                        obj = {"sha256": digest, "content_type": headers.get("content-type"),
                               "length": len(body), "flow": f"{src}:{sport}->{dst}:{dport}"}
                        if extract:
                            path = os.path.join(settings.EXTRACT_DIR, digest[:16])
                            with open(path, "wb") as fh:
                                fh.write(body)
                            obj["saved_as"] = digest[:16]
                        objects.append(obj)
                        entry["sha256"] = digest
                    consumed = len(msg) if hasattr(msg, "__len__") else len(chunk)
                else:
                    msg = dpkt.http.Request(chunk)
                    entry = {"kind": "request", "src": src, "dst": dst, "sport": sport,
                             "dport": dport, "method": msg.method, "uri": msg.uri,
                             "version": msg.version, "host": msg.headers.get("host")}
                    consumed = len(msg)
            except (dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError, ValueError):
                break
            transactions.append(entry)
            sep = chunk.find(b"\r\n\r\n")
            offset += (sep + 4) if sep != -1 else max(1, consumed)
        if len(transactions) >= 500:
            break
    return transactions[:500], objects[:500]
