"""Tests for the GeoIP lookup service."""

from __future__ import annotations

import pytest

from app.services import geoip_service


@pytest.fixture(autouse=True)
def _clear_reader_cache() -> None:
    geoip_service._reader.cache_clear()


def test_lookup_returns_none_when_no_db_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geoip_service.settings, "geoip_country_db_path", None, raising=False)
    assert geoip_service.lookup_country("8.8.8.8") is None


def test_lookup_returns_none_when_db_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        geoip_service.settings,
        "geoip_country_db_path",
        str(tmp_path / "nope.mmdb"),
        raising=False,
    )
    assert geoip_service.lookup_country("8.8.8.8") is None


def test_lookup_skips_private_addresses() -> None:
    assert geoip_service.lookup_country("127.0.0.1") is None
    assert geoip_service.lookup_country("10.0.0.1") is None
    assert geoip_service.lookup_country("192.168.1.1") is None


def test_lookup_handles_invalid_ip() -> None:
    assert geoip_service.lookup_country("not-an-ip") is None
    assert geoip_service.lookup_country(None) is None
    assert geoip_service.lookup_country("") is None
