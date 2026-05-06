from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
JORNADA_PAGE = FRONTEND_SRC / "features" / "financeiro" / "bonificacoes-page.js"
JORNADA_SERVICE = FRONTEND_SRC / "services" / "financeiro-lancamentos-jornada-api.js"
BONIFICACOES_SERVICE = FRONTEND_SRC / "services" / "financeiro-bonificacoes-api.js"
ROUTE_REGISTRY = FRONTEND_SRC / "app" / "route-registry.js"
NAVIGATION = FRONTEND_SRC / "shell" / "navigation.js"
APP_CSS = FRONTEND_SRC / "app.css"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_lancamentos_jornada_has_single_canonical_route_owner():
    route_registry = read(ROUTE_REGISTRY)
    page_source = read(JORNADA_PAGE)
    navigation = read(NAVIGATION)

    assert '"#/financeiro/lancamentos-jornada"' in route_registry
    assert 'exportName: "renderFinanceiroLancamentosJornadaPage"' in route_registry
    assert 'export async function renderFinanceiroLancamentosJornadaPage()' in page_source
    assert "renderFinanceiroBonificacoesPage" not in route_registry
    assert "renderFinanceiroBonificacoesPage" not in page_source
    assert 'href: "#/financeiro/lancamentos-jornada"' in navigation
    assert 'Lançamentos de Jornada' in navigation


def test_legacy_bonus_routes_render_same_jornada_owner_without_old_hub_copy():
    route_registry = read(ROUTE_REGISTRY)
    page_source = read(JORNADA_PAGE)
    pages_financeiro = read(FRONTEND_SRC / "pages-financeiro.js")

    legacy_routes = [
        "#/financeiro/bonificacoes",
        "#/financeiro/bonificacoes/horaria",
        "#/financeiro/bonificacoes/produtividade",
    ]

    for route in legacy_routes:
        route_block = re.search(
            rf'"{re.escape(route)}": \{{(?P<body>.*?)\n  \}},',
            route_registry,
            flags=re.DOTALL,
        )
        assert route_block, f"{route} should remain only as a compatibility hash"
        assert 'exportName: "renderFinanceiroLancamentosJornadaPage"' in route_block.group("body")

    assert "renderFinanceiroBonificacoesPage" not in pages_financeiro
    assert "renderFinanceiroBonificacoesPage" not in page_source
    assert "Lançamentos de Jornada" in page_source
    assert "financeiro-bonificacoes-page" not in page_source
    assert "data-bonus-mode" not in page_source
    assert "Fluxo recomendado" not in page_source
    assert "Financeiro apenas audita cálculos" not in page_source


def test_legacy_productivity_route_autoloads_canonical_jornada_and_opens_consolidado():
    page_source = read(JORNADA_PAGE)

    assert 'const FINANCEIRO_PRODUTIVIDADE_LEGACY_ROUTE = "#/financeiro/bonificacoes/produtividade"' in page_source
    assert "function isLegacyBonusRoute()" in page_source
    assert "routePath().startsWith(FINANCEIRO_BONUS_LEGACY_ROUTE)" in page_source
    assert "function isProductivityCompatibilityRoute()" in page_source
    assert "const shouldAutoLoad = autoLoad || isLegacyBonusRoute()" in page_source
    assert "await loadJornadaGrade(jornadaState.filters)" in page_source
    assert "await openProductivityConsolidado()" in page_source
    assert 'jornadaState.status === "initial" ? "Gerar grade"' in page_source


def test_menu_exposes_only_canonical_jornada_entry_for_finance_bonus_flow():
    navigation = read(NAVIGATION)

    assert 'label: "Lançamentos de Jornada"' in navigation
    assert 'href: "#/financeiro/lancamentos-jornada"' in navigation
    assert 'href: "#/financeiro/missoes"' not in navigation
    assert 'href: "#/financeiro/bonificacoes"' not in navigation
    assert 'href: "#/financeiro/bonificacoes/horaria"' not in navigation
    assert 'href: "#/financeiro/bonificacoes/produtividade"' not in navigation
    assert 'route.startsWith("#/financeiro/bonificacoes")' in navigation


def test_no_legacy_bonus_feature_files_or_fallback_markers_are_active():
    feature_files = {path.name for path in (FRONTEND_SRC / "features" / "financeiro").glob("*.js")}
    source = read(JORNADA_PAGE)

    forbidden_files = {
        "bonificacao-horaria-page.js",
        "bonificacao-produtividade-page.js",
        "produtividade-page.js",
        "jornada-legacy-page.js",
        "bonificacoes-legacy-page.js",
    }
    assert not (feature_files & forbidden_files)
    assert "Carregando grade" in source
    assert "Não foi possível gerar a grade" in source
    assert "Fluxo recomendado" not in source
    assert "Financeiro apenas audita cálculos" not in source
    assert "data-legacy-title" not in source


def test_legacy_css_is_not_attached_to_jornada_owner():
    source = read(JORNADA_PAGE)
    css = read(APP_CSS)

    assert 'class="financeiro-jornada-page ui-page-shell ui-stack"' in source
    assert "financeiro-bonificacoes-page" not in source
    assert ".financeiro-jornada-page" in css
    assert ".financeiro-bonificacoes-page" not in css


def test_jornada_visual_contract_contains_required_blocks_and_columns():
    source = read(JORNADA_PAGE)
    css = read(APP_CSS)
    required_markers = [
        "Lance uma vez",
        "Lançamento único",
        "Consolidado de produtividade",
        "Carregando consolidado",
        "Total a pagar",
        "Missoes consideradas",
        "Data inicial",
        "Data final",
        "Gerar extrato",
        "downloadFinanceiroExtratoPeriodoPdf",
        "Extrato por período",
        "Relatório individual",
        "Gerar relatório individual",
        "Salve ou descarte a linha antes de gerar o relatório",
        "Exportar PDF",
        "Contexto da grade mensal",
        "Total geral",
        "Hora reduzida",
        "Alertas descanso",
        "Grade de lançamentos",
        "Adicionar linha",
        "Recalcular grade",
        "Apresentação",
        "Abandono",
        "Contratante",
        "Pernoites",
        "Cob. base",
        "Cond. especial",
        "operacaoEspecial",
        "data_final",
        "pos_exec_min",
        "justificativa",
        "quantidade_pernoites",
        "cobertura_base",
        "pernoite_comum",
        "pernoitesRemuneraveis",
        "Pós exec. min",
        "Pré calc min",
        "Pós calc",
    ]
    for marker in required_markers:
        assert marker in source

    assert ".financeiro-jornada-page .jornada-filter-panel" in css
    assert ".financeiro-jornada-page .jornada-indicators" in css
    assert ".financeiro-jornada-page .jornada-report-form" in css
    assert ".financeiro-jornada-page .jornada-table-wrap" in css
    assert "overflow-x: auto" in css


def test_jornada_service_uses_existing_backend_contracts_and_documents_gaps():
    source = read(JORNADA_SERVICE)

    assert "nativeGradeEndpoint: true" in source
    assert "nativeLineCreateEndpoint: true" in source
    assert 'previewEndpoint: "/api/v1/financeiro/lancamentos-jornada/preview"' in source
    assert 'const FINANCEIRO_JORNADA_API = "/api/v1/financeiro/lancamentos-jornada"' in source
    assert 'const FINANCEIRO_PRODUTIVIDADE_CONSOLIDADO_API = "/api/v1/financeiro/produtividade/consolidado"' in source
    assert 'const FINANCEIRO_EXTRATO_PERIODO_API = "/api/v1/financeiro/extrato-periodo"' in source
    assert "getFinanceiroProdutividadeConsolidado" in source
    assert "getFinanceiroExtratoPeriodo" in source
    assert "downloadFinanceiroExtratoPeriodoPdf" in source
    assert 'ensurePdfBlob(data, "PDF do extrato por periodo")' in source
    assert "createFinanceiroJornadaLinha" in source
    assert "recalculateFinanceiroJornadaGrade" in source
    assert "downloadFinanceiroJornadaPdf" in source
    assert "downloadFinanceiroJornadaRelatorioIndividual" in source
    assert "tripulante_id: filters.tripulanteId || filters.tripulante_id || \"\"" in source


def test_jornada_aircraft_selector_uses_registered_equipment_options():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert "listFinanceiroEquipamentoOptions" in service_source
    assert "equipamentosPayload?.options" in service_source
    assert "equipamentosPayload?.items" in service_source
    assert "data-jornada-equipment" in page_source
    assert "data-equipment-label" in page_source
    assert "data-equipment-name" in page_source
    assert "data-equipment-type" in page_source
    assert "item?.categoria_financeira" in page_source
    assert "item?.category" in page_source
    assert "raw?.categoria_financeira" in page_source
    assert "function applySelectedAircraftToLine" in page_source
    assert "function clearAircraftFromLine" in page_source
    assert "line.aeronave = label" in page_source
    assert "line.categoriaFinanceiraAeronave = category" in page_source
    assert "line.tipo = category" in page_source
    assert "line.aircraftCleared = true" in page_source
    assert "line.aeronaveId = \"\"" in page_source
    assert "line.categoriaFinanceiraAeronave = \"\"" in page_source
    assert "line.equipmentType = \"\"" in page_source
    assert "line.aircraftRaw = null" in page_source
    assert "syncEquipmentSelectionOnRow" in page_source
    assert "typeField.value = next.tipo || \"\"" in page_source
    assert "delete jornadaState.rowPreview[key]" in page_source
    assert "const aircraftCleared = Boolean(draft.aircraftCleared)" in page_source
    assert "aeronave_id: aircraftCleared ? \"\" : draft.aeronaveId" in page_source
    assert "if (validationMessages.length)" in page_source


def test_jornada_crew_pair_is_explicit_and_sent_in_preview_and_save_payloads():
    page_source = read(JORNADA_PAGE)

    assert "Comandante" in page_source
    assert "Copiloto" in page_source
    assert 'data-jornada-field="comandanteTripulanteId"' in page_source
    assert 'data-jornada-field="copilotoTripulanteId"' in page_source
    assert 'data-jornada-crew="comandante"' in page_source
    assert 'data-jornada-crew="copiloto"' in page_source
    assert "function syncCrewSelectionOnLine" in page_source
    assert "function crewValidationMessages" in page_source
    assert "Informe o comandante da missão." in page_source
    assert "Informe o copiloto da missão." in page_source
    assert "Comandante e copiloto não podem ser o mesmo tripulante." in page_source
    assert "comandante_tripulante_id: comandanteTripulanteId" in page_source
    assert "copiloto_tripulante_id: copilotoTripulanteId" in page_source
    assert "counterpart_tripulante_id" in page_source
    assert "payloadValidationMessages(payload)" in page_source


def test_jornada_save_recalculates_backend_line_before_reports_are_used():
    page_source = read(JORNADA_PAGE)

    assert "const recalculation = result?.recalculation || {}" in page_source
    assert "Cálculo vigente atualizado pelo backend" in page_source
    assert "Recálculo pendente" in page_source
    assert "recalculateFinanceiroJornadaLinha" not in page_source
    assert "function lineIdFromSaveResult" not in page_source
    assert "async function recalculateSavedLine" not in page_source


def test_jornada_grid_shows_persisted_calculation_total_and_status():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert "const JORNADA_TABLE_COLSPAN = 28" in page_source
    assert "<th>Total</th>" in page_source
    assert "<th>Status</th>" in page_source
    assert 'data-label="Total">${renderPreviewCell(row)}' in page_source
    assert "function seedPreviewFromPersistedRow" in page_source
    assert "function refreshPreviewForGradeRows" in page_source
    assert "previewPayloadFromDraft(buildRowDraft(row))" in page_source
    assert "refreshPreviewForGradeRows(jornadaState.rows)" in page_source
    assert 'data-label="Status"><span class="status-pill ${statusClass(row.status)}"' in page_source
    assert "calculationStatus: normalizeText(item.calculation_status || item.status || \"pendente\")" in service_source
    assert "status: normalizeText(item.calculation_status || item.status || \"pendente\")" in service_source


def test_jornada_pdf_download_validates_blob_before_saving_file():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)
    bonus_service_source = read(BONIFICACOES_SERVICE)

    assert "function saveValidatedPdfDownload" in page_source
    assert "downloadFinanceiroJornadaPdf(jornadaState.filters)" in page_source
    assert "downloadFinanceiroExtratoPeriodoPdf(filters)" in page_source
    assert "downloadFinanceiroJornadaRelatorioIndividual({" in page_source
    assert "PDF do fechamento validado e download iniciado." in page_source
    assert "URL.createObjectURL(blob)" in page_source
    assert "URL.revokeObjectURL(url)" in page_source
    assert "PDF_OBJECT_URL_REVOKE_MS = 120000" in page_source
    assert "window.location.assign" not in page_source
    assert "startNativePdfDownload" not in page_source
    assert "downloadBlob" not in page_source
    assert "financeiroJornadaPdfHref" not in page_source
    assert "financeiroExtratoPeriodoPdfHref" not in page_source
    assert "financeiroRelatorioIndividualPdfHref" not in page_source
    assert "async function ensurePdfBlob" in service_source
    assert 'header.startsWith("%PDF")' in service_source
    assert 'trailer.includes("%%EOF")' in service_source
    assert "timeoutMs: 120000" in service_source
    assert 'ensurePdfBlob(data, "PDF do extrato por periodo")' in service_source
    assert "async function ensurePdfBlob" in bonus_service_source
    assert 'ensurePdfBlob(data, "Relatorio individual financeiro")' in bonus_service_source
    assert 'header !== "%PDF-"' in bonus_service_source
    assert 'trailer.includes("%%EOF")' in bonus_service_source


def test_jornada_individual_report_uses_full_crew_and_infers_funcao():
    page_source = read(JORNADA_PAGE)

    assert "function addReportTripulanteEntry" in page_source
    assert "function reportFuncaoForTripulante" in page_source
    assert "row.comandanteTripulanteId || row.comandante_tripulante_id" in page_source
    assert "row.copilotoTripulanteId || row.copiloto_tripulante_id" in page_source
    assert 'document.getElementById("jornadaIndividualTripulante")?.addEventListener("change"' in page_source
    assert "reportFuncaoForTripulante(tripulanteId, explicitFuncao)" in page_source
    assert "Filtrar por tripulante" in page_source
    assert "Filtrar por função" in page_source


def test_jornada_does_not_expose_manual_tripulante_funcao_fields_when_crew_pair_exists():
    page_source = read(JORNADA_PAGE)

    assert "function renderEditableRow(row, index)" in page_source
    body = page_source.split("function renderEditableRow(row, index)", 1)[1].split("function renderGridRows()", 1)[0]

    assert 'data-jornada-field="comandanteTripulanteId"' in body
    assert 'data-jornada-field="copilotoTripulanteId"' in body
    assert 'data-jornada-field="tripulanteId"' not in body
    assert 'data-jornada-field="funcao"' not in body
    assert 'data-jornada-derived="tripulante"' in body
    assert 'data-jornada-derived="funcao"' in body
    assert "Tripulante da linha" in page_source
    assert "Função da linha" in page_source
