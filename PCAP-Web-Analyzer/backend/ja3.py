"""TLS ClientHello parsing: SNI extraction and JA3 fingerprinting."""
import hashlib
from typing import Any, Dict, List, Optional


def _is_grease(v: int) -> bool:
    return (v & 0xFF) == (v >> 8) and (v & 0x0F) == 0x0A


def parse_client_hello(payload: bytes) -> Optional[Dict[str, Any]]:
    """Parse a TLS ClientHello record; return version/ciphers/exts/curves/sni."""
    if len(payload) < 6 or payload[0] != 0x16:
        return None
    hs = payload[5:]
    if not hs or hs[0] != 0x01:
        return None
    try:
        i = 4
        version = int.from_bytes(hs[i:i + 2], "big"); i += 2
        i += 32  # random
        sid_len = hs[i]; i += 1 + sid_len
        cs_len = int.from_bytes(hs[i:i + 2], "big"); i += 2
        ciphers: List[int] = []
        for j in range(0, cs_len, 2):
            c = int.from_bytes(hs[i + j:i + j + 2], "big")
            if not _is_grease(c):
                ciphers.append(c)
        i += cs_len
        comp_len = hs[i]; i += 1 + comp_len

        exts: List[int] = []
        curves: List[int] = []
        ecpf: List[int] = []
        sni: Optional[str] = None
        if i + 2 <= len(hs):
            ext_total = int.from_bytes(hs[i:i + 2], "big"); i += 2
            end = min(len(hs), i + ext_total)
            while i + 4 <= end:
                et = int.from_bytes(hs[i:i + 2], "big")
                el = int.from_bytes(hs[i + 2:i + 4], "big")
                i += 4
                body = hs[i:i + el]
                if not _is_grease(et):
                    exts.append(et)
                if et == 0x0000 and len(body) >= 5:  # SNI
                    nlen = int.from_bytes(body[3:5], "big")
                    sni = body[5:5 + nlen].decode("utf-8", errors="ignore") or None
                elif et == 0x000A and len(body) >= 2:  # supported groups
                    gl = int.from_bytes(body[0:2], "big")
                    for j in range(0, gl, 2):
                        g = int.from_bytes(body[2 + j:2 + j + 2], "big")
                        if not _is_grease(g):
                            curves.append(g)
                elif et == 0x000B and len(body) >= 1:  # ec point formats
                    pl = body[0]
                    ecpf.extend(body[1:1 + pl])
                i += el
        return {"version": version, "ciphers": ciphers, "extensions": exts,
                "curves": curves, "ec_point_formats": ecpf, "sni": sni}
    except (IndexError, ValueError):
        return None


def ja3(ch: Dict[str, Any]) -> Dict[str, str]:
    parts = [
        str(ch["version"]),
        "-".join(map(str, ch["ciphers"])),
        "-".join(map(str, ch["extensions"])),
        "-".join(map(str, ch["curves"])),
        "-".join(map(str, ch["ec_point_formats"])),
    ]
    s = ",".join(parts)
    return {"ja3": hashlib.md5(s.encode()).hexdigest(), "ja3_string": s}
