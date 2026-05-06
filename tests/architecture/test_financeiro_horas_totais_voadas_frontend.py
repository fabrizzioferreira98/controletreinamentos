from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
JORNADA_PAGE = FRONTEND_SRC / "features" / "financeiro" / "bonificacoes-page.js"
JORNADA_SERVICE = FRONTEND_SRC / "services" / "financeiro-lancamentos-jornada-api.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_general_hours_report_button_exists_on_jornada_page():
    source = read(JORNADA_PAGE)

    assert "Relatório geral de horas" in source
    assert 'data-jornada-insight="general-hours"' in source
    assert "renderGeneralHoursReportPanel" in source
    assert 'id="jornadaExportGeneralHoursPdf"' in source


def test_general_hours_report_sends_competencia():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert "collectGeneralHoursReportFilters" in page_source
    assert 'id="jornadaGeneralHoursCompetencia"' in page_source
    assert "competencia: normalized.competencia" in service_source


def test_general_hours_report_sends_funcao_comandante():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert '"comandante", "copiloto"' in page_source
    assert 'value="${escapeAttr(value)}"' in page_source
    assert 'normalized === "comandante"' in service_source
    assert "funcao: normalized.funcao" in service_source
    assert "Comandantes" in page_source


def test_general_hours_report_sends_funcao_copiloto():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert '"comandante", "copiloto"' in page_source
    assert 'id="jornadaGeneralHoursFuncao"' in page_source
    assert 'normalized === "copiloto"' in service_source
    assert "funcao: normalized.funcao" in service_source
    assert "Copilotos" in page_source


def test_general_hours_valid_pdf_is_downloaded_after_backend_validation():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert "getFinanceiroHorasTotaisVoadas" in page_source
    assert "downloadFinanceiroHorasTotaisVoadasPdf(filters)" in page_source
    assert "downloadValidatedPdf({ ...result, filename }, filename)" in page_source
    assert "ensurePdfContentType(response, data, \"PDF do relatorio geral de horas totais voadas\")" in service_source
    assert 'header.startsWith("%PDF")' in service_source


def test_general_hours_json_error_is_not_downloaded_as_pdf():
    service_source = read(JORNADA_SERVICE)

    assert 'contentType.includes("application/json")' in service_source
    assert 'code: data.code || data.error?.code || "pdf_json_response"' in service_source
    assert 'throw createPdfValidationError(data.message || `${contextLabel} indisponivel para o recorte informado.`' in service_source


def test_general_hours_invalid_content_type_blocks_download():
    service_source = read(JORNADA_SERVICE)

    assert 'response.headers.get("Content-Type")' in service_source
    assert '!response?.ok' in service_source
    assert 'contentType.includes("application/pdf")' in service_source
    assert '"invalid_pdf_content_type"' in service_source


def test_general_hours_double_click_is_blocked_while_exporting():
    source = read(JORNADA_PAGE)

    assert 'jornadaState.generalHoursReportStatus === "exporting"' in source
    assert "jornadaState.generalHoursReportKey = key" in source
    assert 'withActionBusy(button, "Exportando..."' in source
    assert 'id="jornadaExportGeneralHoursPdf" ${isExporting ? "disabled" : ""}' in source


def test_general_hours_pending_calculation_message_is_shown():
    source = read(JORNADA_PAGE)

    expected = "Existem lançamentos sem cálculo persistido. Recalcule a grade antes de exportar o relatório financeiro."
    assert expected in source
    assert "generalHoursPayloadHasPendingCalculations" in source
    assert 'jornadaState.generalHoursReportStatus = "pending"' in source
    assert 'title: "Pendência de recálculo"' in source


def test_general_hours_visual_states_are_rendered():
    source = read(JORNADA_PAGE)

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


def test_general_hours_filename_is_canonical():
    page_source = read(JORNADA_PAGE)
    service_source = read(JORNADA_SERVICE)

    assert "financeiroHorasTotaisVoadasFilename(filters)" in page_source
    assert "relatorio-horas-totais-voadas-${functionSlug}-${normalized.competencia}.pdf" in service_source
    assert '"copilotos"' in service_source
    assert '"comandantes"' in service_source
