from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_master_detail_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-master-detail-master-min",
        "--size-master-detail-master-max",
        "--size-master-detail-detail-min",
        "--size-master-detail-detail-max",
        "--space-master-detail-gap",
    ):
        assert expected in tokens

    for expected in (
        ".ui-master-detail",
        ".ui-master-pane",
        ".ui-detail-pane",
        '.ui-detail-pane[data-detail-sticky="true"]',
        ".ui-detail-back",
        ".ui-detail-actions",
        '.ui-master-detail[data-master-detail-state="master"] > .ui-detail-pane',
        '.ui-master-detail[data-master-detail-state="detail"] > .ui-master-pane',
        "overscroll-behavior: contain;",
        "@media (max-width: 900px)",
        "@media (max-width: 640px)",
    ):
        assert expected in primitives

    for forbidden in (
        "dashboard",
        "tripulante",
        "treinamento",
        "relatorio",
        "api(",
        "renderShell",
        "innerHTML",
    ):
        assert forbidden not in primitives

    assert "Master-detail responsivo oficial" in readme
    assert "ui-master-detail" in readme
    assert "wireResponsiveMasterDetail" in readme


def test_master_detail_helper_controls_context_return_focus_and_scroll_without_contract_drift():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        "export function wireResponsiveMasterDetail",
        "function inferMasterDetailContext(trigger)",
        'rootEl.dataset.masterDetail = "ready";',
        "rootEl.dataset.masterDetailState",
        'detailEl.dataset.detailState = "active";',
        "rootEl.dataset.masterDetailContext = context;",
        "detailEl.dataset.detailContext = context;",
        'trigger.setAttribute("aria-selected", String(selected));',
        'masterEl?.setAttribute("data-master-state", "context-preserved");',
        'rootEl.dataset.masterDetailState = "master";',
        "function backToMaster()",
        'scrollIntoView({ block: "start", behavior: "smooth" })',
        "focus({ preventScroll: true })",
        "autoWire = true",
    ):
        assert expected in source

    for preserved in (
        "export function enhanceOperationalSurfaces(root = document)",
        "enhanceResponsiveForms(scope);",
        "enhanceResponsiveFilters(scope);",
        "enhanceResponsiveTables(scope);",
        "export function wireResponsiveOverlay",
    ):
        assert preserved in source


def test_dashboard_calendar_adopts_master_detail_without_dashboard_api_drift():
    source = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")

    for expected in (
        "wireResponsiveMasterDetail",
        'dashboard-calendar-layout dashboard-calendar-responsive-layout" data-dashboard-surface="calendar-detail"',
        'dashboard-calendar-master-detail ui-master-detail" id="dashboardCalendarMasterDetail"',
        'dashboard-calendar-shell ui-master-pane" id="dashboardCalendarMaster"',
        'dashboard-calendar-aside ui-detail-pane" id="dashboardCalendarDetail"',
        'id="dashboardCalendarBack"',
        'data-master-detail-pattern="calendar"',
        "detailList.dataset.detailContext = isoDate;",
        "masterDetail?.activate(",
    ):
        assert expected in source

    for preserved in (
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
        "wireDashboardCalendar(calendarData)",
        "renderDayDetails(button.dataset.calendarDay)",
        'href="#/tripulantes/${item.tripulante_id}"',
        'href="#/treinamentos/${item.id}"',
    ):
        assert preserved in source


def test_tripulante_documents_adopt_master_detail_without_file_contract_drift():
    source = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")

    for expected in (
        "wireResponsiveMasterDetail",
        'document-master-detail ui-master-detail ui-panel-offset-sm" id="tripulanteDocumentMasterDetail"',
        'document-master-pane ui-master-pane" id="tripulanteDocumentMaster"',
        'document-detail-pane ui-detail-pane" id="tripulanteDocumentDetailPane"',
        'id="tripulanteDocumentPreviewBack"',
        'data-master-detail-pattern="documents"',
        'data-detail-target="tripulanteDocumentPreview"',
        "autoWire: false",
        "documentMasterDetail?.activate(button);",
        "document-preview-card ui-surface",
        "ui-table-wrap ui-table-density-compact",
        "fileAvailabilityTone",
        "document-library-row ${primaryFile?.id === item.id ? \"is-selected\" : \"\"}",
        "candidate.closest(\".document-library-row\")?.classList.toggle(\"is-selected\", selected);",
    ):
        assert expected in source

    for preserved in (
        'id="tripulante-file-form"',
        'id="tripulanteFileSubmit"',
        'id="tripulanteDocumentPreviewFrame"',
        'id="tripulanteDocumentPreviewFallback"',
        'id="tripulanteDocumentPreviewOpen"',
        'id="tripulanteDocumentPreviewDownload"',
        'data-file-blob-available=',
        'api(`/api/v1/tripulantes/${tripulanteId}/files`',
        'api(`/api/v1/tripulantes/${tripulanteId}/photo`',
        "renderDocumentPreview({",
        "loadDocumentPreviewBlob({",
        "fetch(url, {",
        'headers: { Accept: "application/pdf" }',
        "URL.createObjectURL(blob)",
        "currentDocumentPreviewObjectUrl",
        "blobAvailable: button.dataset.fileBlobAvailable === \"true\"",
        "O registro existe, mas o arquivo não está acessível no armazenamento atual. Visualização e download foram bloqueados.",
        "Visualização indisponível",
        "withActionBusy(",
    ):
        assert preserved in source


def test_master_detail_policy_css_and_migration_are_registered():
    css = _read(FRONTEND_SRC / "app.css")
    migration = _read(MIGRATION_DIR / "34.2.10-politica-master-detail-responsivo.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "34.2.10: master-detail policy bridges shared primitives to real paired surfaces.",
        ".dashboard-calendar-master-detail.ui-master-detail",
        ".document-master-detail.ui-master-detail",
        ".dashboard-calendar-shell.ui-master-pane",
        ".document-detail-pane.ui-detail-pane",
        ".tripulante-detail-page-shell .document-library-row.is-selected td",
        ".tripulante-detail-page-shell .document-library-availability[data-availability=\"removed\"]",
        ".tripulante-detail-page-shell .document-detail-actions.ui-detail-actions",
        ".dashboard-calendar-back",
        ".document-preview-back",
        "@media (max-width: 900px)",
    ):
        assert expected in css

    for expected in (
        "Politica master-detail responsivo",
        "`ui-master-detail`",
        "`ui-master-pane`",
        "`ui-detail-pane`",
        "`ui-detail-back`",
        "`wireResponsiveMasterDetail`",
        "`#dashboardCalendarMasterDetail`",
        "`#tripulanteDocumentMasterDetail`",
        "backend, contratos, rotas e regras de dominio",
    ):
        assert expected in migration

    assert "34.2.10-politica-master-detail-responsivo.md" in index
