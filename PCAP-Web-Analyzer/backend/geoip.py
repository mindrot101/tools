"""Optional GeoIP/ASN enrichment. Degrades gracefully if lib or DB absent."""
from typing import Any, Dict, Optional

import settings

_reader = None
_tried = False


def _get_reader():
    global _reader, _tried
    if _tried:
        return _reader
    _tried = True
    if not settings.GEOIP_DB:
        return None
    try:
        import geoip2.database  # type: ignore
        _reader = geoip2.database.Reader(settings.GEOIP_DB)
    except Exception:  # noqa: BLE001 - optional dependency / missing db
        _reader = None
    return _reader


def available() -> bool:
    return _get_reader() is not None


def lookup(ip: str) -> Optional[Dict[str, Any]]:
    r = _get_reader()
    if not r:
        return None
    try:
        resp = r.city(ip)
        return {"country": resp.country.iso_code, "city": resp.city.name}
    except Exception:  # noqa: BLE001
        return None
