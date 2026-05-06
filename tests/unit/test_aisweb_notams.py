from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.src.controle_treinamentos.application.aisweb_notams import (
    clear_aisweb_notam_cache,
    get_aisweb_notams,
    parse_aisweb_notam_response,
)
from backend.src.controle_treinamentos.infra.aisweb_client import AiswebClientError

REFERENCE_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)


def _notam_xml() -> str:
    return """
    <aisweb>
      <notam id="sample" total="1" updatedat="2026-05-05 15:57:00">
        <item id="11718183">
          <id>11718183</id>
          <icaoairport_id>SBGO</icaoairport_id>
          <cod>QWPLW</cod>
          <status>ACTIVE</status>
          <cat>NAV</cat>
          <tp>NOTAMR</tp>
          <dt>2026-02-27 21:11:00</dt>
          <n>F0824/26</n>
          <loc>SBGO</loc>
          <b>2602272111</b>
          <c>2605270400</c>
          <e>PJE SUBJ AUTH COMPULSORIA APP-ANAPOLIS ACONTECERA CENTRO COORD 164639S0490819W RAIO 10KM RTO</e>
          <state>ACTIVE</state>
        </item>
      </notam>
    </aisweb>
    """


def test_parse_aisweb_notam_response_reads_real_xml_contract():
    payload = parse_aisweb_notam_response(_notam_xml(), icao_code="SBGO", now=REFERENCE_NOW)

    assert payload["status"] == "available"
    assert payload["source"] == "AISWEB"
    assert payload["updatedAt"] == "2026-05-05T15:57:00Z"
    assert payload["items"][0]["id"] == "11718183"
    assert payload["items"][0]["icao"] == "SBGO"
    assert payload["items"][0]["number"] == "F0824/26"
    assert payload["items"][0]["severity"] == "warning"
    assert "PJE SUBJ AUTH" in payload["items"][0]["description"]


def test_get_aisweb_notams_returns_available_contract(monkeypatch):
    clear_aisweb_notam_cache()
    monkeypatch.setenv("AISWEB_API_KEY", "key")
    monkeypatch.setenv("AISWEB_API_PASS", "pass")
    monkeypatch.setenv("AISWEB_BASE_URL", "http://aisweb.example.test/api/")

    payload = get_aisweb_notams("SBGO", now=REFERENCE_NOW, fetcher=lambda **_kwargs: _notam_xml())

    assert payload["status"] == "available"
    assert payload["items"][0]["source"] == "AISWEB"
    assert payload["items"][0]["validUntil"] == "2026-05-27T04:00:00Z"


def test_get_aisweb_notams_returns_unavailable_without_credentials(monkeypatch):
    clear_aisweb_notam_cache()
    monkeypatch.delenv("AISWEB_API_KEY", raising=False)
    monkeypatch.delenv("AISWEB_API_PASS", raising=False)

    payload = get_aisweb_notams("SBGO", now=REFERENCE_NOW, fetcher=lambda **_kwargs: _notam_xml())

    assert payload["status"] == "unavailable"
    assert payload["source"] == "not_configured"
    assert payload["items"] == []


def test_get_aisweb_notams_returns_error_without_fabricating_items(monkeypatch):
    clear_aisweb_notam_cache()
    monkeypatch.setenv("AISWEB_API_KEY", "key")
    monkeypatch.setenv("AISWEB_API_PASS", "pass")

    def failing_fetcher(**_kwargs):
        raise AiswebClientError("timeout")

    payload = get_aisweb_notams("SBGO", now=REFERENCE_NOW, fetcher=failing_fetcher)

    assert payload["status"] == "error"
    assert payload["source"] == "AISWEB"
    assert payload["items"] == []
