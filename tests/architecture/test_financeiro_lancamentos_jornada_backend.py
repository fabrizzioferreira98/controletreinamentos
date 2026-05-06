from pathlib import Path

from backend.src.controle_treinamentos.auth import ENDPOINT_PERMISSION_MAP
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_API_CONTRACT
from backend.src.controle_treinamentos.contracts.financeiro_http import FINANCE_HTTP_CONTRACTS
from backend.src.controle_treinamentos.financeiro_audit_events import FINANCE_AUDIT_EVENT_NAMES


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"
ROUTES = BACKEND_SRC / "api" / "http" / "financeiro" / "routes.py"
APP = BACKEND_SRC / "application" / "financeiro_lancamentos_jornada.py"
QUERY = BACKEND_SRC / "application" / "financeiro_jornada_query.py"
REPORTS = BACKEND_SRC / "application" / "financeiro_relatorios.py"
MISSOES_APP = BACKEND_SRC / "application" / "financeiro_missoes.py"
REPOSITORY = BACKEND_SRC / "repositories" / "financeiro_lancamentos_jornada.py"
SCHEMA = BACKEND_SRC / "db" / "schema.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def contracts_by_name() -> dict[str, dict]:
    return {contract["name"]: contract for contract in FINANCE_HTTP_CONTRACTS}


def test_jornada_backend_has_canonical_http_contracts():
    contracts = contracts_by_name()
    expected = {
        "finance_journey_grid_list": ("GET", "/api/v1/financeiro/lancamentos-jornada"),
        "finance_journey_line_create": ("POST", "/api/v1/financeiro/lancamentos-jornada"),
        "finance_journey_line_preview": ("POST", "/api/v1/financeiro/lancamentos-jornada/preview"),
        "finance_journey_line_update": ("PATCH", "/api/v1/financeiro/lancamentos-jornada/{id}"),
        "finance_journey_line_recalculate": ("POST", "/api/v1/financeiro/lancamentos-jornada/{id}/recalcular"),
        "finance_journey_grid_recalculate": ("POST", "/api/v1/financeiro/lancamentos-jornada/recalcular-grade"),
        "finance_journey_grid_pdf": ("GET", "/api/v1/financeiro/lancamentos-jornada.pdf"),
        "finance_productivity_consolidated": ("GET", "/api/v1/financeiro/produtividade/consolidado"),
        "finance_total_flight_hours": ("GET", "/api/v1/financeiro/horas-totais-voadas"),
        "finance_total_flight_hours_pdf": ("GET", "/api/v1/financeiro/horas-totais-voadas.pdf"),
        "finance_period_extract": ("GET", "/api/v1/financeiro/extrato-periodo"),
        "finance_period_extract_pdf": ("GET", "/api/v1/financeiro/extrato-periodo.pdf"),
    }
    for name, (method, path) in expected.items():
        assert name in contracts
        assert contracts[name]["method"] == method
        assert contracts[name]["path"] == path
        assert contracts[name]["requires_org_scope"] is True


def test_jornada_routes_have_rbac_endpoint_mapping():
    expected_permissions = {
        "financeiro.api_finance_journey_grid_list": "finance:bonuses:read",
        "financeiro.api_finance_journey_line_create": "finance:missions:create",
        "financeiro.api_finance_journey_line_preview": "finance:bonuses:read",
        "financeiro.api_finance_journey_line_update": "finance:missions:update",
        "financeiro.api_finance_journey_line_recalculate": "finance:missions:recalculate",
        "financeiro.api_finance_productivity_consolidated": "finance:bonuses:read",
        "financeiro.api_finance_total_flight_hours": "finance:bonuses:read",
        "financeiro.api_finance_total_flight_hours_pdf": "finance:exports:create",
        "financeiro.api_finance_period_extract": "finance:bonuses:read",
        "financeiro.api_finance_period_extract_pdf": "finance:exports:create",
        "financeiro.api_finance_journey_grid_recalculate": "finance:periods:recalculate",
        "financeiro.api_finance_journey_grid_pdf": "finance:exports:create",
    }
    for endpoint, permission in expected_permissions.items():
        assert ENDPOINT_PERMISSION_MAP[endpoint] == permission


def test_jornada_audit_events_are_registered():
    for event_name in {
        "finance.journey_grid.generated",
        "finance.journey_line.created",
        "finance.journey_line.updated",
        "finance.journey_line.cancelled",
        "finance.journey_line.recalculated",
        "finance.journey_grid.recalculated",
        "finance.journey_grid.exported",
        "finance.report.individual.generated",
    }:
        assert event_name in FINANCE_AUDIT_EVENT_NAMES


def test_jornada_reuses_existing_financial_tables_with_gapfix_columns():
    app_source = read(APP)
    query_source = read(QUERY)
    report_source = read(REPORTS)
    missoes_source = read(MISSOES_APP)
    repository_source = read(REPOSITORY)
    schema_source = read(SCHEMA)

    assert "financeiro_missoes_operacionais" in repository_source
    assert "financeiro_missao_tripulantes" in repository_source
    assert "financeiro_calculos_horarios" in repository_source
    assert "financeiro_calculos_produtividade" in repository_source
    assert "data_final" in schema_source
    assert "pos_exec_min" in schema_source
    assert "justificativa" in schema_source
    assert "financeiro_missoes_operacionais_periodo_valido" in schema_source
    assert '"data_final"' in app_source
    assert '"pos_exec_min"' in app_source
    assert '"justificativa"' in app_source
    assert "quantidade_pernoites" in repository_source
    assert "operacao_especial" in repository_source
    assert "valor_pernoite_comum" in schema_source
    assert "pernoite_comum_sem_cobertura" in app_source
    assert "consultar_linhas_jornada" in app_source
    assert '"contratante"' in app_source
    assert '"quantidade_pernoites"' in app_source
    assert '"cobertura_base"' in app_source
    assert '"operacao_especial"' in app_source
    assert "consultar_calculos_horarios_jornada" in report_source
    assert "consultar_calculos_produtividade_jornada" in report_source
    assert "consolidar_produtividade_jornada" in app_source
    assert "gerar_extrato_periodo_jornada" in app_source
    assert "exportar_extrato_periodo_pdf" in app_source
    assert "consultar_linhas_jornada_periodo" in app_source
    assert "Linha salva na grade, ainda sem calculo horario vigente." in query_source
    assert "invalidar_calculos_produtividade_vigentes_da_competencia" in missoes_source
    assert "recalcular_missao_operacional" in app_source
    assert "recalcular_competencia_financeira" in app_source
    assert "CREATE TABLE IF NOT EXISTS financeiro_lancamentos_jornada" not in schema_source


def test_jornada_api_contract_exposes_resource_family():
    resources = FINANCE_API_CONTRACT["resources"]
    assert "lancamentos_jornada" in resources
    paths = resources["lancamentos_jornada"]["canonical_paths"]
    assert "/api/v1/financeiro/lancamentos-jornada" in paths
    assert "/api/v1/financeiro/lancamentos-jornada/preview" in paths
    assert "/api/v1/financeiro/lancamentos-jornada/recalcular-grade" in paths
    assert "/api/v1/financeiro/produtividade/consolidado" in FINANCE_API_CONTRACT["resources"]["produtividade"]["canonical_paths"]
    assert "/api/v1/financeiro/horas-totais-voadas" in FINANCE_API_CONTRACT["resources"]["relatorios"]["canonical_paths"]
    assert "/api/v1/financeiro/horas-totais-voadas.pdf" in FINANCE_API_CONTRACT["resources"]["relatorios"]["canonical_paths"]
    assert "/api/v1/financeiro/extrato-periodo" in FINANCE_API_CONTRACT["resources"]["relatorios"]["canonical_paths"]
    assert "/api/v1/financeiro/extrato-periodo.pdf" in FINANCE_API_CONTRACT["resources"]["relatorios"]["canonical_paths"]
