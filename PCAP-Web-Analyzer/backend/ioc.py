"""Indicator-of-Compromise loading and matching.

IOC text format: one indicator per line. Optional `type:value`
(ip/cidr/domain), or a bare value auto-classified. `#` comments allowed.
"""
import ipaddress
from typing import Any, Dict, List, Set, Tuple


def parse_iocs(text: str) -> Dict[str, Any]:
    ips: Set[str] = set()
    nets: List[ipaddress._BaseNetwork] = []
    domains: Set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, val = line.partition(":") if ":" in line and line.split(":", 1)[0] in (
            "ip", "cidr", "domain") else ("", "", line)
        val = (val or line).strip().lower()
        try:
            if "/" in val:
                nets.append(ipaddress.ip_network(val, strict=False))
                continue
            ipaddress.ip_address(val)
            ips.add(val)
        except ValueError:
            domains.add(val.lstrip("*."))
    return {"ips": ips, "nets": nets, "domains": domains}


def match(iocs: Dict[str, Any], seen_ips: Set[str], seen_domains: Set[str]) -> List[Dict[str, str]]:
    hits: List[Dict[str, str]] = []
    for ip in seen_ips:
        low = ip.lower()
        if low in iocs["ips"]:
            hits.append({"type": "ip", "indicator": ip})
            continue
        for net in iocs["nets"]:
            try:
                if ipaddress.ip_address(ip) in net:
                    hits.append({"type": "cidr", "indicator": f"{ip} in {net}"})
                    break
            except ValueError:
                pass
    for dom in seen_domains:
        d = dom.lower().rstrip(".")
        for bad in iocs["domains"]:
            if d == bad or d.endswith("." + bad):
                hits.append({"type": "domain", "indicator": dom})
                break
    return hits
