from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
ROUTE_REGISTRY = FRONTEND_SRC / "app" / "route-registry.js"
SHELL_NAVIGATION = FRONTEND_SRC / "shell" / "navigation.js"
PAGE_MODULE = FRONTEND_SRC / "pages-financeiro.js"
SETTINGS_PAGE = FRONTEND_SRC / "features" / "financeiro" / "fechamento-parametros-page.js"
PARAMETERS_SERVICE = FRONTEND_SRC / "services" / "financeiro-parametros-api.js"
CSS_FILE = FRONTEND_SRC / "app.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_js_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def test_financeiro_fechamento_route_navigation_and_permissions_are_registered():
    route_registry = _read(ROUTE_REGISTRY)
    navigation = _read(SHELL_NAVIGATION)
    page_module = _read(PAGE_MODULE)

    assert '"#/financeiro/fechamento-parametros"' in route_registry
    assert 'exportName: "renderFinanceiroFechamentoParametrosPage"' in route_registry
    assert 'permissions: ["finance:parameters:read", "finance:periods:read"]' in route_registry
    assert 'href: "#/financeiro/fechamento-parametros"' in navigation
    assert 'permissions: ["finance:parameters:read", "finance:periods:read"]' in navigation
    assert 'from "./features/financeiro/fechamento-parametros-page.js";' in page_module


def test_fechamento_service_declares_real_preflight_audit_divergences_and_pdf_endpoints():
    service = _read(PARAMETERS_SERVICE)

    for expected in (
        '/api/v1/financeiro/competencias',
        "/preflight-calculo",
        "/recalcular",
        "/fechar",
        "/reabrir",
        "/relatorio.pdf",
        'const FINANCEIRO_AUDITORIA_API = "/api/v1/financeiro/auditoria";',
        'const FINANCEIRO_DIVERGENCIAS_API = "/api/v1/financeiro/divergencias";',
        "getFinanceiroCompetenciaPreflight",
        "listFinanceiroAuditoria",
        "listFinanceiroDivergencias",
    ):
        assert expected in service


def test_fechamento_page_calls_preflight_and_renders_gate_states():
    page = _read(SETTINGS_PAGE)

    for expected in (
        "getFinanceiroCompetenciaPreflight",
        "renderGateSummary",
        "Gate de elegibilidade / preflight",
        "gate aprovado",
        "gate reprovado",
        "Calculavel?",
        "Fechavel?",
        "Bloqueios",
        "Parametros faltantes",
        "Parametros invalidos",
        "Parametros nao elegiveis",
        "Parametros ambiguos",
        "Dados QA detectados",
        "Divergencias do gate",
        "Fechar bloqueado:",
    ):
        assert expected in page


def test_fechamento_page_blocks_close_when_gate_fails_and_keeps_confirm_and_reopen_reason():
    page = _read(SETTINGS_PAGE)

    for expected in (
        "gateAllowsClose",
        'id="financePeriodCloseButton"',
        "if (!preflight || preflight.fechavel !== true)",
        "Fechamento bloqueado:",
        "confirmAction({",
        "Fechar competencia financeira?",
        "window.prompt(",
        "Motivo de reabertura e obrigatorio.",
        "Reabrir competencia financeira?",
    ):
        assert expected in page


def test_fechamento_page_uses_real_audit_and_divergences_sections_with_filters():
    page = _read(SETTINGS_PAGE)

    for expected in (
        "renderAuditSection",
        "renderDivergencesSection",
        "financeAuditFiltersForm",
        "financeDivergencesFiltersForm",
        "Atualizar auditoria",
        "Atualizar divergencias",
        "Sem eventos de auditoria para a competencia",
        "Sem divergencias registradas",
        "Auditoria indisponivel",
        "Divergencias indisponiveis",
        'data-finance-audit-section',
        'data-finance-divergences-section',
        "wireObservabilityFilters",
        "listFinanceiroAuditoria",
        "listFinanceiroDivergencias",
    ):
        assert expected in page


def test_fechamento_page_keeps_pdf_flow_read_only_with_operational_http_errors():
    page = _read(SETTINGS_PAGE)
    service = _read(PARAMETERS_SERVICE)
    combined = _strip_js_comments(f"{page}\n{service}")

    for expected in (
        'id="financePeriodPdfButton"',
        "downloadFinanceiroCompetenciaPdf",
        'Accept: "application/pdf"',
        "downloadBlob(result.blob, result.filename)",
        "filenameFromContentDisposition",
        "resolvePdfKindLabel",
        "PDF indisponivel",
        "Sessao expirada para gerar PDF. Entre novamente.",
        "Seu perfil nao possui permissao para gerar PDF.",
        "PDF indisponivel para esta competencia no momento.",
        "PDF bloqueado pelo backend para o estado atual da competencia.",
        "Falha operacional ao gerar PDF no backend.",
    ):
        assert expected in combined


def test_fechamento_frontend_does_not_calculate_totals_or_gate_logic_locally():
    page = _read(SETTINGS_PAGE)
    service = _read(PARAMETERS_SERVICE)
    combined = _strip_js_comments(f"{page}\n{service}").lower()

    assert "frontend nao calcula nem decide gate" in combined
    assert "os totais sao consumidos da api" in combined

    forbidden_fragments = (
        "total_horario +",
        "total_produtividade +",
        "total_geral =",
        "produtividade_calculada +",
        "garantia_minima_calculada",
        "horas_noturnas_convertidas =",
        "/api/v1/financeiro/missoes",
        "/api/v1/treinamentos/options",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined


def test_fechamento_responsive_contract_keeps_tablet_mobile_under_control():
    page = _read(SETTINGS_PAGE)
    css = _read(CSS_FILE)

    for expected in (
        'data-finance-page="fechamento-parametros"',
        "data-finance-mobile-tabs=\"fechamento-parametros\"",
        'data-finance-section="monthly-closing"',
        'data-finance-section="parameters"',
        'data-finance-section="holidays"',
    ):
        assert expected in page

    for expected in (
        '.financeiro-settings-page[data-finance-page="fechamento-parametros"][data-mobile-active-section="monthly-closing"]',
        '.financeiro-settings-page[data-finance-page="fechamento-parametros"][data-mobile-active-section="parameters"]',
        '.financeiro-settings-page[data-finance-page="fechamento-parametros"][data-mobile-active-section="holidays"]',
        ".financeiro-heavy-section-disclosure",
        ".financeiro-heavy-section-disclosure-body",
        ".financeiro-settings-page[data-finance-page=\"fechamento-parametros\"] .ui-table-wrap",
        ".financeiro-settings-page[data-finance-page=\"fechamento-parametros\"] [data-finance-period-actions]",
    ):
        assert expected in css
