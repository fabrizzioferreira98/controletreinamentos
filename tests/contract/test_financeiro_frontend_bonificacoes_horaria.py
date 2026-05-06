from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
JORNADA_PAGE = FRONTEND_SRC / "features" / "financeiro" / "bonificacoes-page.js"
JORNADA_SERVICE = FRONTEND_SRC / "services" / "financeiro-lancamentos-jornada-api.js"
ROUTE_REGISTRY = FRONTEND_SRC / "app" / "route-registry.js"
SHELL_NAVIGATION = FRONTEND_SRC / "shell" / "navigation.js"
CSS_FILE = FRONTEND_SRC / "app.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_js_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def _route_block(route_registry: str, route: str) -> str:
    match = re.search(
        rf'"{re.escape(route)}": \{{(?P<body>.*?)\n  \}},',
        route_registry,
        flags=re.DOTALL,
    )
    assert match, f"{route} should be registered"
    return match.group("body")


def test_financeiro_jornada_route_navigation_and_services_are_registered():
    route_registry = _read(ROUTE_REGISTRY)
    navigation = _read(SHELL_NAVIGATION)
    service = _read(JORNADA_SERVICE)
    page = _read(JORNADA_PAGE)

    assert 'exportName: "renderFinanceiroLancamentosJornadaPage"' in _route_block(
        route_registry,
        "#/financeiro/lancamentos-jornada",
    )
    for legacy_route in (
        "#/financeiro/bonificacoes",
        "#/financeiro/bonificacoes/horaria",
        "#/financeiro/bonificacoes/produtividade",
    ):
        assert 'exportName: "renderFinanceiroLancamentosJornadaPage"' in _route_block(route_registry, legacy_route)
    assert "renderFinanceiroBonificacoesPage" not in route_registry

    assert 'href: "#/financeiro/lancamentos-jornada"' in navigation
    assert 'href: "#/financeiro/bonificacoes"' not in navigation
    assert 'permission: "finance:bonuses:read"' in navigation

    assert 'const FINANCEIRO_JORNADA_API = "/api/v1/financeiro/lancamentos-jornada"' in service
    assert 'previewEndpoint: "/api/v1/financeiro/lancamentos-jornada/preview"' in service
    assert 'const FINANCEIRO_PRODUTIVIDADE_CONSOLIDADO_API = "/api/v1/financeiro/produtividade/consolidado"' in service
    assert 'const FINANCEIRO_EXTRATO_PERIODO_API = "/api/v1/financeiro/extrato-periodo"' in service
    assert "getFinanceiroJornadaGrade" in page
    assert "previewFinanceiroJornadaLinha" in page
    assert "recalculateFinanceiroJornadaGrade" in page
    assert "downloadFinanceiroJornadaRelatorioIndividual" in page


def test_financeiro_jornada_has_single_operational_experience_without_old_hub():
    page = _read(JORNADA_PAGE)
    css = _read(CSS_FILE)

    for expected in (
        "Lançamentos de Jornada",
        "Consolidado de produtividade",
        "Extrato por período",
        "Relatório individual",
        "Contexto da grade mensal",
        "Grade de lançamentos",
        "Adicionar linha",
        "Recalcular grade",
        "data-jornada-insight",
        "data-jornada-row",
        "data-row-preview",
    ):
        assert expected in page

    for legacy_marker in (
        "Hub de selecao do modulo de bonus",
        "renderFinanceiroBonificacoesHub",
        "selectedCalculationFromRoute",
        'data-bonus-mode="hub"',
        'data-finance-bonus-section="hourly"',
        'data-finance-bonus-section="productivity"',
        "data-finance-bonus-tab",
        "renderMobileTabs",
        "wireBonificacoesCalculationCards",
        "data-mobile-active-section",
    ):
        assert legacy_marker not in page

    assert ".financeiro-jornada-page .jornada-filter-panel" in css
    assert ".financeiro-jornada-page .jornada-table-wrap" in css
    assert ".financeiro-jornada-page .jornada-indicators" in css
    assert 'class="financeiro-jornada-page ui-page-shell ui-stack"' in page
    assert "financeiro-bonificacoes-page" not in page


def test_financeiro_jornada_preview_states_use_backend_and_guard_races():
    page = _read(JORNADA_PAGE)

    for expected in (
        "PREVIEW_DEBOUNCE_MS",
        "previewRequestSeq",
        "previewTimers",
        "missingPreviewFields",
        "Preview financeiro pelo backend.",
        "Preview disponível",
        "Sem preview",
        "Preencha data, aeronave, tripulação e horários.",
        "Competência fechada",
        "Sem permissão financeira",
    ):
        assert expected in page


def test_financeiro_jornada_surfaces_required_operational_states_and_errors():
    page = _read(JORNADA_PAGE)

    for expected in (
        "Carregando grade",
        "Não foi possível gerar a grade",
        "Grade vazia",
        "Não foi possível gerar o extrato",
        "Carregando consolidado",
        "Salve ou recalcule a grade antes de gerar o relatório.",
        "Exportando...",
        "Recalculando...",
        "Linha de jornada criada no backend.",
        "Linha de jornada salva no backend.",
        "Grade enviada para recálculo da competência pelo backend.",
    ):
        assert expected in page


def test_financeiro_jornada_frontend_does_not_calculate_definitive_finance():
    page = _read(JORNADA_PAGE)
    service = _read(JORNADA_SERVICE)
    combined = _strip_js_comments(f"{page}\n{service}").lower()

    forbidden_fragments = (
        "math.max(",
        "total_devido = produtividade",
        "horas_noturnas_convertidas =",
        "duracao_hora_noturna_minutos /",
        "minutos_noturnos_reais / 52.5",
        "adicional_noturno *",
        "produtividade_calculada +",
        "produtividade_calculada -",
        "produtividade_calculada *",
        "produtividade_calculada /",
        "post /api/v1/financeiro",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined

    assert 'sourceoftruth: "backend"' in combined
    assert "preview calculado no backend" in combined
    assert "cálculos persistidos no backend" in combined


def test_financeiro_jornada_uses_supported_finance_endpoints_without_legacy_screen_api():
    page = _read(JORNADA_PAGE)
    service = _read(JORNADA_SERVICE)
    combined = _strip_js_comments(f"{page}\n{service}")

    assert "/api/v1/financeiro/lancamentos-jornada" in combined
    assert "/api/v1/financeiro/lancamentos-jornada/preview" in combined
    assert "/api/v1/financeiro/produtividade/consolidado" in combined
    assert "/api/v1/financeiro/extrato-periodo" in combined
    assert "/api/v1/financeiro/relatorios/individual.pdf" in combined
    assert "/api/v1/bonificacoes" not in combined
    assert "/api/v1/missoes" not in combined
    assert "/api/v1/treinamentos/options" not in combined
