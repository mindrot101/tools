import io
import os
import socket
import struct
import tempfile

# Point storage/uploads at a temp dir BEFORE app modules import.
_tmp = tempfile.mkdtemp(prefix="pcaptest_")
os.environ["DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "up")

import dpkt
import pytest

MAC_A = b"\x00\x11\x22\x33\x44\x55"
MAC_B = b"\x66\x77\x88\x99\xaa\xbb"


def _eth(ip):
    e = dpkt.ethernet.Ethernet(src=MAC_A, dst=MAC_B, type=dpkt.ethernet.ETH_TYPE_IP)
    e.data = ip
    return bytes(e)


def _ip(proto, l4):
    ip = dpkt.ip.IP(src=socket.inet_aton("10.0.0.1"), dst=socket.inet_aton("10.0.0.2"), p=proto)
    ip.data = l4
    ip.len = len(bytes(ip))
    return ip


def _tcp(sport, dport, seq, payload):
    return dpkt.tcp.TCP(sport=sport, dport=dport, seq=seq, flags=dpkt.tcp.TH_ACK, data=payload)


def _client_hello(host="example.com"):
    name = host.encode()
    sni_ext = struct.pack("!H", 3 + len(name)) + b"\x00" + struct.pack("!H", len(name)) + name
    ext = struct.pack("!HH", 0x0000, len(sni_ext)) + sni_ext
    body = (b"\x03\x03" + b"\x00" * 32 + b"\x00" + struct.pack("!H", 2) + b"\x13\x01" +
            b"\x01\x00" + struct.pack("!H", len(ext)) + ext)
    hs = b"\x01" + struct.pack("!I", len(body))[1:] + body
    return b"\x16\x03\x01" + struct.pack("!H", len(hs)) + hs


def build_pcap() -> bytes:
    """A capture exercising DNS(+dup), split HTTP, TLS SNI, ICMP, ARP."""
    frames = []

    dns = dpkt.dns.DNS(id=0x1234, qd=[dpkt.dns.DNS.Q(name="example.com", type=dpkt.dns.DNS_A)])
    udp = dpkt.udp.UDP(sport=40000, dport=53, data=bytes(dns))
    udp.ulen = len(bytes(udp))
    dns_frame = _eth(_ip(dpkt.ip.IP_PROTO_UDP, udp))
    frames.append(dns_frame)
    frames.append(dns_frame)  # exact duplicate -> must be deduped

    frames.append(_eth(_ip(dpkt.ip.IP_PROTO_TCP, _tcp(50000, 80, 1000, b"GET /index.html HTTP/1.1\r\nHost: exa"))))
    frames.append(_eth(_ip(dpkt.ip.IP_PROTO_TCP, _tcp(50000, 80, 1035, b"mple.com\r\n\r\n"))))

    frames.append(_eth(_ip(dpkt.ip.IP_PROTO_TCP, _tcp(50001, 443, 2000, _client_hello()))))

    icmp = dpkt.icmp.ICMP(type=8, data=dpkt.icmp.ICMP.Echo(id=1, seq=1, data=b"ping"))
    frames.append(_eth(_ip(dpkt.ip.IP_PROTO_ICMP, icmp)))

    arp = dpkt.arp.ARP(spa=socket.inet_aton("10.0.0.1"), tpa=socket.inet_aton("10.0.0.2"),
                       sha=MAC_A, tha=b"\x00" * 6, op=dpkt.arp.ARP_OP_REQUEST)
    ea = dpkt.ethernet.Ethernet(src=MAC_A, dst=b"\xff" * 6, type=dpkt.ethernet.ETH_TYPE_ARP)
    ea.data = arp
    frames.append(bytes(ea))

    buf = io.BytesIO()
    w = dpkt.pcap.Writer(buf)
    for i, fr in enumerate(frames):
        w.writepkt(fr, ts=1000.0 + i)
    return buf.getvalue()


@pytest.fixture
def pcap_bytes():
    return build_pcap()
