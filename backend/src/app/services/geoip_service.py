"""GeoIP lookup against a MaxMind GeoLite2-Country database.

The database file is not bundled; operators download it and set
``settings.geoip_country_db_path``. When the file is missing or the IP
cannot be resolved, ``lookup_country`` returns ``None`` — login code
treats geo as best-effort metadata and never fails on its absence.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _reader():  # type: ignore[no-untyped-def]
    path = settings.geoip_country_db_path
    if not path:
        return None
    if not Path(path).is_file():
        logger.warning("GeoIP database not found at %s — country lookup disabled", path)
        return None
    try:
        import maxminddb

        return maxminddb.open_database(path)
    except Exception:
        logger.exception("Failed to open GeoIP database at %s", path)
        return None


def lookup_country(ip: str | None) -> str | None:
    """Return ISO-3166 α-2 country code for ``ip``, or ``None`` if unknown.

    Non-routable addresses (loopback, private, link-local) return ``None``
    without hitting the database.
    """
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_multicast:
        return None

    reader = _reader()
    if reader is None:
        return None
    try:
        record = reader.get(ip)
    except Exception:
        logger.exception("GeoIP lookup failed for %s", ip)
        return None
    if not isinstance(record, dict):
        return None
    country = record.get("country") or {}
    iso = country.get("iso_code") if isinstance(country, dict) else None
    if isinstance(iso, str) and len(iso) == 2:
        return iso.upper()
    return None
