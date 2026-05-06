from __future__ import annotations

from pathlib import Path

from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.financeiro_audit_events import (
    FINANCE_AUDIT_COMMON_METADATA_FIELDS,
    FINANCE_AUDIT_EVENT_CATALOG,
    FINANCE_AUDIT_EVENT_NAMES,
    FINANCE_AUDIT_EVENTS_BY_NAME,
)

ROOT = Path(__file__).resolve().parents[2]
FINANCE_AUDIT_EVENTS_MODULE = ROOT / "backend" / "src" / "controle_treinamentos" / "financeiro_audit_events.py"

REQUIRED_FINANCE_AUDIT_EVENTS = {
    "finance.mission.created",
    "finance.mission.updated",
    "finance.mission.cancel.requested",
    "finance.mission.cancelled",
    "finance.mission.cancel.failed",
    "finance.mission.delete.requested",
    "finance.mission.deleted",
    "finance.mission.delete.blocked",
    "finance.mission.delete.failed",
    "finance.mission.recalculation.requested",
    "finance.mission.recalculated",
    "finance.calculation.updated",
    "finance.calculation.superseded",
    "finance.calculation.invalidated_by_mission_cancel",
    "finance.calculation.failed",
    "finance.hourly_bonus.calculated",
    "finance.productivity.calculated",
    "finance.parameter.created",
    "finance.parameter.updated",
    "finance.period.recalculated",
    "finance.period.closed",
    "finance.period.reopened",
    "finance.journey_grid.generated",
    "finance.journey_line.created",
    "finance.journey_line.updated",
    "finance.journey_line.cancelled",
    "finance.journey_line.deleted",
    "finance.journey_line.recalculated",
    "finance.journey_grid.recalculated",
    "finance.journey_grid.exported",
    "finance.report.individual.generated",
    "finance.extract.period.generated",
    "finance.productivity.consolidated.generated",
    "finance.export.generated",
}

EXPECTED_ENTITY_TYPES = {
    "finance_mission",
    "finance_hourly_bonus",
    "finance_productivity_bonus",
    "finance_parameter",
    "finance_holiday",
    "finance_period",
    "finance_export",
    "finance_journey_grid",
    "finance_journey_line",
}

CRITICAL_BEFORE_AFTER_EVENTS = {
    "finance.mission.updated",
    "finance.mission.cancelled",
    "finance.mission.recalculated",
    "finance.calculation.updated",
    "finance.calculation.superseded",
    "finance.parameter.updated",
    "finance.period.recalculated",
    "finance.period.closed",
    "finance.period.reopened",
}


def test_finance_audit_catalog_contains_all_required_events():
    assert set(FINANCE_AUDIT_EVENT_NAMES) == REQUIRED_FINANCE_AUDIT_EVENTS
    assert set(FINANCE_AUDIT_EVENTS_BY_NAME) == REQUIRED_FINANCE_AUDIT_EVENTS
    assert len(FINANCE_AUDIT_EVENT_CATALOG) == len(REQUIRED_FINANCE_AUDIT_EVENTS)


def test_finance_audit_event_names_are_unique_and_specific():
    assert len(FINANCE_AUDIT_EVENT_NAMES) == len(set(FINANCE_AUDIT_EVENT_NAMES))
    assert all(event_name.startswith("finance.") for event_name in FINANCE_AUDIT_EVENT_NAMES)
    assert "finance.updated" not in FINANCE_AUDIT_EVENT_NAMES
    assert "finance.created" not in FINANCE_AUDIT_EVENT_NAMES


def test_finance_audit_events_have_entity_type_and_permission():
    finance_permissions = set(FINANCE_PERMISSION_KEYS)

    for event in FINANCE_AUDIT_EVENT_CATALOG:
        assert event["entity_type"] in EXPECTED_ENTITY_TYPES
        assert set(event.get("allowed_entity_types", (event["entity_type"],))) <= EXPECTED_ENTITY_TYPES
        assert event["permission"] in finance_permissions
        assert event["permission"].startswith("finance:")


def test_finance_audit_events_define_common_metadata():
    common_fields = set(FINANCE_AUDIT_COMMON_METADATA_FIELDS)

    for event in FINANCE_AUDIT_EVENT_CATALOG:
        assert common_fields <= set(event["required_metadata"])


def test_critical_finance_audit_events_require_before_and_after_payloads():
    for event_name in CRITICAL_BEFORE_AFTER_EVENTS:
        event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
        assert event["requires_before"] is True
        assert event["requires_after"] is True


def test_finance_audit_events_define_expected_event_specific_metadata():
    assert {"changed_fields", "reason"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.mission.updated"]["required_metadata"]
    )
    assert {"reason", "mission_id"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.mission.recalculation.requested"]["required_metadata"]
    )
    assert {"tripulante_id", "funcao", "calculation_version"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.calculation.updated"]["required_metadata"]
    )
    assert "error_code" in FINANCE_AUDIT_EVENTS_BY_NAME["finance.calculation.failed"]["required_metadata"]
    assert {"snapshot_id", "closed_at", "total_geral"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.period.closed"]["required_metadata"]
    )
    assert {"reason", "previous_snapshot_id"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.period.reopened"]["required_metadata"]
    )
    assert "finance_holiday" in FINANCE_AUDIT_EVENTS_BY_NAME["finance.parameter.created"]["allowed_entity_types"]
    assert "finance_holiday" in FINANCE_AUDIT_EVENTS_BY_NAME["finance.parameter.updated"]["allowed_entity_types"]
    assert {"format", "filters", "record_count"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.export.generated"]["required_metadata"]
    )
    assert {"filters", "record_count"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.journey_grid.generated"]["required_metadata"]
    )
    assert {"linha_id", "mission_id"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.journey_line.created"]["required_metadata"]
    )
    assert {"format", "filters", "record_count"} <= set(
        FINANCE_AUDIT_EVENTS_BY_NAME["finance.extract.period.generated"]["required_metadata"]
    )


def test_finance_audit_catalog_does_not_dispatch_audit_events_yet():
    source = FINANCE_AUDIT_EVENTS_MODULE.read_text(encoding="utf-8")

    assert "record_audit_event" not in source
    assert "audit_event(" not in source
    assert "get_db" not in source


def test_finance_audit_catalog_does_not_register_routes_or_blueprints():
    source = FINANCE_AUDIT_EVENTS_MODULE.read_text(encoding="utf-8")

    assert "Blueprint" not in source
    assert ".route(" not in source
    assert "/api/v1/financeiro" not in source
