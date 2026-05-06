from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.src.controle_treinamentos.application.aisweb_weather import (
    AiswebResponseError,
    AiswebValidationError,
    clear_aisweb_met_cache,
    get_aisweb_met,
    normalize_icao_code,
    parse_aisweb_met_response,
    parse_metar,
)
from backend.src.controle_treinamentos.infra.aisweb_client import AiswebClientError

REFERENCE_NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("metar", "expected"),
    [
        (
            "SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015",
            {"temperatureC": 27, "windDirection": "120", "windSpeedKt": 12},
        ),
        (
            "SBGO 170900Z VRB05KT 9999 FEW030 25/19 Q1013",
            {"windDirection": "VRB", "windSpeedKt": 5},
        ),
        (
            "SBGO 170900Z 00000KT CAVOK 22/15 Q1017",
            {"temperatureC": 22, "windDirection": "000", "windSpeedKt": 0},
        ),
        (
            "SBGO 170900Z 12012KT 9999 FEW030 M02/M05 Q1015",
            {"temperatureC": -2, "windDirection": "120", "windSpeedKt": 12},
        ),
    ],
)
def test_parse_metar_extracts_incremental_fields(metar, expected):
    parsed = parse_metar(metar, now=REFERENCE_NOW)

    for key, value in expected.items():
        assert parsed[key] == value
    assert parsed["condition"] == "VMC"


@pytest.mark.parametrize(
    ("metar", "expected_condition", "expected_visibility"),
    [
        ("SBGO 170900Z 00000KT CAVOK 22/15 Q1017", "VMC", 10000),
        ("SBGO 170900Z 12012KT 7000 BKN020 27/18 Q1015", "MVFR", 7000),
        ("SBGO 170900Z 12012KT 4000 BKN012 27/18 Q1015", "IFR", 4000),
        ("SBGO 170900Z 12012KT 1200 OVC004 22/20 Q1010", "IMC", 1200),
    ],
)
def test_parse_metar_derives_operational_condition(metar, expected_condition, expected_visibility):
    parsed = parse_metar(metar, now=REFERENCE_NOW)

    assert parsed["condition"] == expected_condition
    assert parsed["visibilityMeters"] == expected_visibility


def test_parse_metar_observed_at_uses_current_month_and_year():
    parsed = parse_metar("SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015", now=REFERENCE_NOW)

    assert parsed["observedAt"] == "2026-04-17T09:00:00Z"


def test_parse_aisweb_met_response_reads_xml_contract():
    parsed = parse_aisweb_met_response(
        """
        <aisweb>
          <met>
            <loc>SBGO</loc>
            <metar>SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015</metar>
            <taf>TAF SBGO 170900Z 1712/1812 12010KT CAVOK</taf>
          </met>
        </aisweb>
        """
    )

    assert parsed["loc"] == "SBGO"
    assert parsed["metar"] == "SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015"
    assert parsed["taf"].startswith("TAF SBGO")


def test_parse_aisweb_met_response_rejects_invalid_xml():
    with pytest.raises(AiswebResponseError):
        parse_aisweb_met_response("<aisweb><metar>SBGO")


def test_normalize_icao_code_accepts_only_four_letters():
    assert normalize_icao_code("sbgo") == "SBGO"

    with pytest.raises(AiswebValidationError):
        normalize_icao_code("SB1")


def test_get_aisweb_met_returns_available_contract(monkeypatch):
    clear_aisweb_met_cache()
    monkeypatch.setenv("AISWEB_API_KEY", "key")
    monkeypatch.setenv("AISWEB_API_PASS", "pass")
    monkeypatch.setenv("AISWEB_BASE_URL", "http://aisweb.example.test/api/")

    def _fetcher(**_kwargs):
        return """
        <aisweb><met><loc>SBGO</loc>
        <metar>SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015</metar>
        <taf>TAF SBGO 170900Z 1712/1812 12010KT CAVOK</taf>
        </met></aisweb>
        """

    payload = get_aisweb_met("SBGO", now=REFERENCE_NOW, fetcher=_fetcher)

    assert payload["status"] == "available"
    assert payload["icaoCode"] == "SBGO"
    assert payload["locationLabel"] == "Goi\u00e2nia"
    assert payload["temperatureC"] == 27
    assert payload["windDirection"] == "120"
    assert payload["windSpeedKt"] == 12
    assert payload["condition"] == "VMC"
    assert payload["rawMetar"].startswith("SBGO 170900Z")
    assert payload["rawTaf"].startswith("TAF SBGO")


def test_get_aisweb_met_returns_unavailable_without_credentials(monkeypatch):
    clear_aisweb_met_cache()
    monkeypatch.delenv("AISWEB_API_KEY", raising=False)
    monkeypatch.delenv("AISWEB_API_PASS", raising=False)

    payload = get_aisweb_met("SBGO", now=REFERENCE_NOW, fetcher=lambda **_kwargs: "")

    assert payload["status"] == "unavailable"
    assert payload["rawMetar"] is None
    assert payload["updatedAtLabel"] == "Dados n\u00e3o atualizados"


@pytest.mark.parametrize(
    ("icao_code", "location_label"),
    [
        ("SBGO", "Goi\u00e2nia"),
        ("SBSP", "S\u00e3o Paulo"),
        ("SBPJ", "Palmas"),
        ("SBEG", "Manaus"),
        ("SBSV", "Salvador"),
        ("SBBE", "Bel\u00e9m"),
        ("SBSN", "Santar\u00e9m"),
    ],
)
def test_get_aisweb_met_returns_known_rotation_base_labels(monkeypatch, icao_code, location_label):
    clear_aisweb_met_cache()
    monkeypatch.delenv("AISWEB_API_KEY", raising=False)
    monkeypatch.delenv("AISWEB_API_PASS", raising=False)

    payload = get_aisweb_met(icao_code.lower(), now=REFERENCE_NOW, fetcher=lambda **_kwargs: "")

    assert payload["icaoCode"] == icao_code
    assert payload["locationLabel"] == location_label


def test_get_aisweb_met_returns_stale_cache_when_upstream_fails(monkeypatch):
    clear_aisweb_met_cache()
    monkeypatch.setenv("AISWEB_API_KEY", "key")
    monkeypatch.setenv("AISWEB_API_PASS", "pass")
    monkeypatch.setenv("AISWEB_MET_CACHE_TTL_SECONDS", "60")

    def _success(**_kwargs):
        return "<root><loc>SBGO</loc><metar>SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015</metar><taf>TAF SBGO</taf></root>"

    available = get_aisweb_met("SBGO", now=REFERENCE_NOW, fetcher=_success)
    assert available["status"] == "available"

    def _failure(**_kwargs):
        raise AiswebClientError("boom")

    stale = get_aisweb_met("SBGO", now=REFERENCE_NOW + timedelta(minutes=10), fetcher=_failure)

    assert stale["status"] == "stale"
    assert stale["rawMetar"] == available["rawMetar"]
