"""Best-effort live packet capture (gated by ENABLE_LIVE_CAPTURE).

Requires CAP_NET_RAW / NET_ADMIN on the container and a host interface.
Falls back with a clear error when unavailable.
"""
import socket
import time
from pathlib import Path

import dpkt

import settings


def capture_to_file(interface: str, out_path: Path, max_packets: int = 1000,
                    max_seconds: int = 30) -> int:
    if not settings.ENABLE_LIVE_CAPTURE:
        raise PermissionError("Live capture is disabled (set ENABLE_LIVE_CAPTURE=true)")
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    except (AttributeError, PermissionError, OSError) as e:
        raise PermissionError(f"Cannot open raw socket ({e}); needs CAP_NET_RAW on Linux")
    if interface:
        s.bind((interface, 0))
    s.settimeout(1.0)
    n, deadline = 0, time.time() + max_seconds
    with open(out_path, "wb") as fh:
        writer = dpkt.pcap.Writer(fh)
        while n < max_packets and time.time() < deadline:
            try:
                buf = s.recv(65535)
            except socket.timeout:
                continue
            writer.writepkt(buf)
            n += 1
    s.close()
    return n
