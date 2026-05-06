from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
JORNADA_PAGE = FRONTEND_SRC / "features" / "financeiro" / "bonificacoes-page.js"
JORNADA_SERVICE = FRONTEND_SRC / "services" / "financeiro-lancamentos-jornada-api.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_general_productivity_report_button_exists_on_jornada_page():
    source = read(JORNADA_PAGE)

    assert 'data-jornada-insight="general-productivity"' in source
    assert "Relatório geral de produtividade" in source
    assert "renderGeneralProductivityReportPanel" in source
    assert 'id="jornadaExportGeneralProductivityPdf"' in source


def test_general_productivity_report_uses_canonical_backend_contract():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert 'const FINANCEIRO_PRODUTIVIDADE_RELATORIO_GERAL_API = "/api/v1/financeiro/produtividade/relatorio-geral"' in service_source
    assert "getFinanceiroProdutividadeRelatorioGeral" in page_source
    assert "downloadFinanceiroProdutividadeRelatorioGeralPdf(filters)" in page_source
    assert "competencia: normalized.competencia" in service_source
    assert "funcao: normalized.funcao" in service_source


def test_general_productivity_report_validates_pdf_before_download():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert "financeiroProdutividadeRelatorioGeralFilename(filters)" in page_source
    assert "downloadValidatedPdf({ ...result, filename }, filename)" in page_source
    assert 'ensurePdfContentType(response, data, "PDF do relatorio geral de produtividade")' in service_source
    assert 'ensurePdfBlob(data, "PDF do relatorio geral de produtividade")' in service_source
    assert 'header.startsWith("%PDF")' in service_source
    assert 'trailer.includes("%%EOF")' in service_source


def test_general_productivity_report_blocks_json_html_and_double_click():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert 'contentType.includes("application/json")' in service_source
    assert '"invalid_pdf_content_type"' in service_source
    assert 'jornadaState.generalProductivityReportStatus === "exporting"' in page_source
    assert "jornadaState.generalProductivityReportKey = key" in page_source
    assert 'id="jornadaExportGeneralProductivityPdf" ${isExporting ? "disabled" : ""}' in page_source


def test_general_productivity_report_visual_states_and_pending_message():
    source = read(JORNADA_PAGE)

    assert "GENERAL_PRODUCTIVITY_PENDING_MESSAGE" in source
    assert "productivityGeneralPayloadHasPendingCalculations" in source
    assert 'jornadaState.generalProductivityReportStatus = "pending"' in source
    for title in [
        'title: "Pronto para exportar"',
        'title: "Exportando"',
        'title: "PDF gerado"',
        'title: "Sem dados"',
        'title: "Pendência de recálculo"',
        'title: "Erro de permissão"',
        'title: "Erro inesperado"',
    ]:
        assert title in source


def test_general_productivity_report_filename_is_canonical():
    service_source = read(JORNADA_SERVICE)

    assert "relatorio-geral-produtividade-${functionSlug}-${normalized.competencia}.pdf" in service_source
    assert '"copilotos"' in service_source
    assert '"comandantes"' in service_source
