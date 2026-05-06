from __future__ import annotations

from backend.src.controle_treinamentos.application.operational_dashboard import (
    build_dashboard_operational_alerts,
    build_dashboard_relevant_notams,
    build_dashboard_weather_by_base,
)


def test_weather_by_base_external_failure_returns_safe_unavailable_rows():
    def failing_fetcher(_icao_code):
        raise RuntimeError("upstream timeout")

    payload = build_dashboard_weather_by_base(fetcher=failing_fetcher)

    assert payload["status"] == "error"
    assert len(payload["items"]) == 7
    assert all(item["status"] == "error" for item in payload["items"])
    assert all(item["rawMetar"] is None for item in payload["items"])
    assert "Pista 17R/35L fechada" not in str(payload)


def test_weather_by_base_preserves_real_operational_condition():
    def fetcher(icao_code):
        return {
            "icaoCode": icao_code,
            "locationLabel": icao_code,
            "temperatureC": 27,
            "windSpeedKt": 8,
            "visibilityMeters": 10000,
            "condition": "VMC",
            "rawMetar": f"{icao_code} 051200Z 09008KT 9999 FEW030 27/18 Q1015",
            "rawTaf": f"TAF {icao_code}",
            "source": "AISWEB",
            "status": "available",
        }

    payload = build_dashboard_weather_by_base(fetcher=fetcher)

    assert payload["status"] == "available"
    assert {item["condition"] for item in payload["items"]} == {"VMC"}


def test_notams_contract_is_explicitly_unavailable_without_fake_items():
    payload = build_dashboard_relevant_notams(
        fetcher=lambda _icao_code: {
            "status": "unavailable",
            "source": "not_configured",
            "items": [],
            "message": "Integra\u00e7\u00e3o real de NOTAM indispon\u00edvel.",
        }
    )

    assert payload["status"] == "unavailable"
    assert payload["source"] == "not_configured"
    assert payload["items"] == []
    assert "indispon" in payload["message"].lower()


def test_notams_contract_uses_real_aisweb_items_when_available():
    def fetcher(icao_code):
        return {
            "status": "available",
            "source": "AISWEB",
            "items": [
                {
                    "id": f"{icao_code}-1",
                    "code": "NAV",
                    "icao": icao_code,
                    "description": "AUXILIO NAV INOP",
                    "updatedAt": "2026-05-05T12:00:00Z",
                    "updatedAtLabel": "05/05 12:00Z",
                    "validUntil": "2026-05-06T12:00:00Z",
                    "validUntilLabel": "06/05 12:00Z",
                    "severity": "critical",
                    "source": "AISWEB",
                }
            ],
        }

    payload = build_dashboard_relevant_notams(fetcher=fetcher)

    assert payload["status"] == "available"
    assert payload["source"] == "AISWEB"
    assert payload["items"]
    assert {item["source"] for item in payload["items"]} == {"AISWEB"}
    assert "mock" not in str(payload).lower()


def test_operational_alerts_are_derived_from_real_contracts_only():
    payload = build_dashboard_operational_alerts(
        summary_data={
            "alerts": {"vencem_hoje": 1, "vencidos": 2, "em_7_dias": 3},
            "summary": {"sem_informacao": 4},
        },
        base_operations={"bases": [{"ativa": False}]},
        notams={"status": "unavailable", "items": []},
    )

    sources = {item["source"] for item in payload["items"]}
    assert payload["status"] == "available"
    assert "dashboard_summary" in sources
    assert "dashboard_base_operations" in sources
    assert "dashboard_notams" in sources
    assert "mock" not in str(payload).lower()
