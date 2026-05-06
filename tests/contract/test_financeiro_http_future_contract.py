from __future__ import annotations

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_API_ROUTE_PREFIX, FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.contracts.financeiro_http import (
    FINANCE_HTTP_ENVELOPE_FIELDS,
    FINANCE_HTTP_ERROR_ENVELOPE_FIELDS,
    FINANCE_HTTP_CONTRACTS,
    finance_http_paths,
)
from backend.src.controle_treinamentos.financeiro_audit_events import FINANCE_AUDIT_EVENT_NAMES

EXPECTED_FINANCE_ENDPOINTS = {
    ("GET", "/api/v1/financeiro/missoes"),
    ("POST", "/api/v1/financeiro/missoes"),
    ("POST", "/api/v1/financeiro/missoes/preview"),
    ("GET", "/api/v1/financeiro/missoes/{id}"),
    ("GET", "/api/v1/financeiro/missoes/{id}/preflight-calculo"),
    ("PATCH", "/api/v1/financeiro/missoes/{id}"),
    ("POST", "/api/v1/financeiro/missoes/{id}/recalcular"),
    ("POST", "/api/v1/financeiro/missoes/{id}/cancelar"),
    ("GET", "/api/v1/financeiro/lancamentos-jornada"),
    ("POST", "/api/v1/financeiro/lancamentos-jornada"),
    ("POST", "/api/v1/financeiro/lancamentos-jornada/preview"),
    ("PATCH", "/api/v1/financeiro/lancamentos-jornada/{id}"),
    ("POST", "/api/v1/financeiro/lancamentos-jornada/{id}/recalcular"),
    ("POST", "/api/v1/financeiro/lancamentos-jornada/recalcular-grade"),
    ("GET", "/api/v1/financeiro/lancamentos-jornada.pdf"),
    ("GET", "/api/v1/financeiro/horas-totais-voadas"),
    ("GET", "/api/v1/financeiro/horas-totais-voadas.pdf"),
    ("GET", "/api/v1/financeiro/bonificacoes/horaria"),
    ("GET", "/api/v1/financeiro/bonificacoes/horaria/{id}"),
    ("GET", "/api/v1/financeiro/bonificacoes/produtividade"),
    ("GET", "/api/v1/financeiro/produtividade/consolidado"),
    ("GET", "/api/v1/financeiro/produtividade/relatorio-geral"),
    ("GET", "/api/v1/financeiro/produtividade/relatorio-geral.pdf"),
    ("GET", "/api/v1/financeiro/bonificacoes/produtividade/{tripulante_id}"),
    ("GET", "/api/v1/financeiro/relatorios/individual.pdf"),
    ("GET", "/api/v1/financeiro/extrato-periodo"),
    ("GET", "/api/v1/financeiro/extrato-periodo.pdf"),
    ("GET", "/api/v1/financeiro/competencias/{competencia}"),
    ("GET", "/api/v1/financeiro/competencias/{competencia}/preflight-calculo"),
    ("GET", "/api/v1/financeiro/competencias/{competencia}/relatorio.pdf"),
    ("POST", "/api/v1/financeiro/competencias/{competencia}/recalcular"),
    ("POST", "/api/v1/financeiro/competencias/{competencia}/fechar"),
    ("POST", "/api/v1/financeiro/competencias/{competencia}/reabrir"),
    ("GET", "/api/v1/financeiro/parametros"),
    ("POST", "/api/v1/financeiro/parametros"),
    ("PATCH", "/api/v1/financeiro/parametros/{id}"),
    ("GET", "/api/v1/financeiro/feriados"),
    ("POST", "/api/v1/financeiro/feriados"),
    ("PATCH", "/api/v1/financeiro/feriados/{id}"),
    ("GET", "/api/v1/financeiro/auditoria"),
    ("GET", "/api/v1/financeiro/divergencias"),
}

READ_ONLY_METHODS = {"GET"}
MUTATION_METHODS = {"POST", "PATCH"}
AUDITED_READ_ONLY_ENDPOINTS = {
    ("GET", "/api/v1/financeiro/lancamentos-jornada"),
}


def _contracts_by_path_method() -> dict[tuple[str, str], dict]:
    return {
        (contract["method"], contract["path"]): contract
        for contract in FINANCE_HTTP_CONTRACTS
    }


def _normalize_registered_finance_path(path: str) -> str:
    normalized = path.replace("<string:competencia>", "{competencia}")
    normalized = normalized.replace("<int:tripulante_id>", "{tripulante_id}")
    normalized = normalized.replace("<int:linha_id>", "{id}")
    return normalized.replace("<int:mission_id>", "{id}").replace("<int:calculation_id>", "{id}").replace(
        "<int:parameter_id>", "{id}"
    ).replace("<int:holiday_id>", "{id}")


def _registered_finance_endpoint_keys() -> set[tuple[str, str]]:
    app = create_app()
    keys = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(FINANCE_API_ROUTE_PREFIX):
            continue
        for method in set(rule.methods) & {"GET", "POST", "PATCH"}:
            keys.add((method, _normalize_registered_finance_path(rule.rule)))
    return keys


def test_finance_http_contract_matrix_covers_expected_runtime_endpoints():
    endpoint_keys = set(_contracts_by_path_method())

    assert endpoint_keys == EXPECTED_FINANCE_ENDPOINTS
    assert len(FINANCE_HTTP_CONTRACTS) == len(EXPECTED_FINANCE_ENDPOINTS)
    assert set(finance_http_paths()) == {path for _method, path in EXPECTED_FINANCE_ENDPOINTS}


def test_finance_http_contracts_have_required_shape_and_prefix():
    valid_methods = READ_ONLY_METHODS | MUTATION_METHODS

    for contract in FINANCE_HTTP_CONTRACTS:
        assert contract["method"] in valid_methods
        assert contract["path"].startswith(FINANCE_API_ROUTE_PREFIX)
        assert contract["permission"].startswith("finance:")
        assert contract["kind"] in {"read_only", "mutation", "export", "simulation"}
        assert contract["deny_by_default"] is True
        assert contract["requires_org_scope"] is True
        assert contract["org_scope_default"] == FINANCE_ORG_SCOPE_DEFAULT
        assert set(FINANCE_HTTP_ENVELOPE_FIELDS) == {
            "success",
            "status",
            "code",
            "message",
            "request_id",
            "correlation_id",
        }
        assert set(FINANCE_HTTP_ERROR_ENVELOPE_FIELDS) == set(FINANCE_HTTP_ENVELOPE_FIELDS)
        assert contract["success_statuses"]
        assert 401 in contract["error_statuses"]
        assert 403 in contract["error_statuses"]


def test_finance_http_permissions_exist_in_real_rbac_catalog():
    finance_permissions = set(FINANCE_PERMISSION_KEYS)

    for contract in FINANCE_HTTP_CONTRACTS:
        assert contract["permission"] in finance_permissions


def test_finance_http_mutations_require_audit_events_from_real_catalog():
    audit_events = set(FINANCE_AUDIT_EVENT_NAMES)

    for contract in FINANCE_HTTP_CONTRACTS:
        if contract["kind"] == "mutation":
            assert contract["method"] in MUTATION_METHODS
            assert contract["audit_events"], contract["name"]
            assert set(contract["audit_events"]) <= audit_events
            assert contract["request_payload_minimal"], contract["name"]
        elif contract["kind"] == "export":
            assert contract["method"] in READ_ONLY_METHODS
            assert set(contract["audit_events"]) <= audit_events
            assert contract["audit_events"], contract["name"]
        elif contract["kind"] == "simulation":
            assert contract["method"] in MUTATION_METHODS
            assert contract["audit_events"] == ()
            assert contract["request_payload_minimal"], contract["name"]
        else:
            assert contract["method"] in READ_ONLY_METHODS
            if (contract["method"], contract["path"]) in AUDITED_READ_ONLY_ENDPOINTS:
                assert set(contract["audit_events"]) <= audit_events
                assert contract["audit_events"], contract["name"]
            else:
                assert contract["audit_events"] == ()


def test_finance_http_read_only_contracts_do_not_require_mutation_audit_events():
    for contract in FINANCE_HTTP_CONTRACTS:
        if contract["kind"] in {"read_only", "simulation"}:
            if contract["kind"] == "read_only":
                assert contract["method"] == "GET"
            else:
                assert contract["method"] == "POST"
            if (contract["method"], contract["path"]) in AUDITED_READ_ONLY_ENDPOINTS:
                assert contract["audit_events"]
            else:
                assert contract["audit_events"] == ()
            assert contract["blocked_when_period_closed"] is False
            assert contract["closed_period_rule"] in {"read_allowed", "simulation_does_not_mutate_closed_period"}


def test_finance_http_period_endpoints_have_specific_permissions():
    contracts = _contracts_by_path_method()

    assert (
        contracts[("POST", "/api/v1/financeiro/competencias/{competencia}/recalcular")]["permission"]
        == "finance:periods:recalculate"
    )
    assert (
        contracts[("POST", "/api/v1/financeiro/competencias/{competencia}/fechar")]["permission"]
        == "finance:periods:close"
    )
    assert (
        contracts[("POST", "/api/v1/financeiro/competencias/{competencia}/reabrir")]["permission"]
        == "finance:periods:reopen"
    )


def test_finance_mission_recalculate_contract_declares_idempotent_response_and_audit_events():
    contracts = _contracts_by_path_method()
    contract = contracts[("POST", "/api/v1/financeiro/missoes/{id}/recalcular")]

    for field in (
        "mission_id",
        "competence",
        "calculation_status",
        "recalculated_at",
        "affected_calculations",
        "warnings",
        "errors",
        "current_result",
    ):
        assert field in contract["response_payload"]

    for event_name in (
        "finance.mission.recalculation.requested",
        "finance.mission.recalculated",
        "finance.calculation.updated",
        "finance.calculation.superseded",
        "finance.calculation.failed",
    ):
        assert event_name in contract["audit_events"]


def test_finance_http_closed_period_rules_are_declared_for_mutations():
    contracts = _contracts_by_path_method()
    blocked_mutations = {
        ("POST", "/api/v1/financeiro/missoes"),
        ("PATCH", "/api/v1/financeiro/missoes/{id}"),
        ("POST", "/api/v1/financeiro/missoes/{id}/recalcular"),
        ("POST", "/api/v1/financeiro/missoes/{id}/cancelar"),
        ("POST", "/api/v1/financeiro/competencias/{competencia}/recalcular"),
        ("POST", "/api/v1/financeiro/competencias/{competencia}/fechar"),
    }

    for key in blocked_mutations:
        assert contracts[key]["blocked_when_period_closed"] is True
        assert contracts[key]["closed_period_rule"].startswith("blocked")

    reopen = contracts[("POST", "/api/v1/financeiro/competencias/{competencia}/reabrir")]
    assert reopen["blocked_when_period_closed"] is False
    assert reopen["closed_period_rule"] == "allowed_only_when_closed_with_reason"
    assert "motivo" in reopen["request_payload_minimal"]


def test_finance_http_contracts_match_registered_runtime_routes():
    assert _registered_finance_endpoint_keys() == EXPECTED_FINANCE_ENDPOINTS


def test_finance_observability_contracts_are_read_only_and_not_501_stub():
    contracts = _contracts_by_path_method()
    for path in ("/api/v1/financeiro/auditoria", "/api/v1/financeiro/divergencias"):
        contract = contracts[("GET", path)]
        assert contract["kind"] == "read_only"
        assert contract["success_statuses"] == (200,)
        assert 501 not in contract["error_statuses"]
