from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"
MIGRATION_DOC = ROOT / "docs" / "migration" / "97.individual-report-boundary-hardening.md"
README = ROOT / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_individual_report_spa_route_is_selector_not_detail_surface():
    registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    selector = _read(FRONTEND_SRC / "features" / "relatorio-individual" / "page.js")

    assert '"#/relatorios/individual"' in registry
    assert 'exportName: "renderRelatorioIndividualPage"' in registry
    assert "#/relatorios/individual/" not in registry
    assert 'renderTripulantesListPage("report")' in selector


def test_individual_report_selector_formalizes_ssr_document_boundary():
    source = _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js")

    assert 'INDIVIDUAL_REPORT_DOCUMENT_BOUNDARY = "ssr_document_read_model"' in source
    assert 'INDIVIDUAL_REPORT_PDF_BOUNDARY = "ssr_document_pdf"' in source
    assert "function individualReportDocumentHref(tripulanteId)" in source
    assert "function individualReportPdfHref(tripulanteId)" in source
    assert "Seletor SPA canonico" in source
    assert "Abrir documento" in source
    assert "Baixar PDF" in source
    assert 'href="/tripulantes/${item.id}/relatorio"' not in source
    assert 'href="/tripulantes/${item.id}/relatorio/export.pdf"' not in source


def test_dashboard_no_longer_opens_individual_report_document_as_casual_shortcut():
    dashboard_routes = _read(BACKEND_SRC / "blueprints" / "dashboard" / "routes.py")
    dashboard_template = _read(BACKEND_SRC / "templates" / "dashboard.html")

    assert 'url_for("cadastros.tripulante_report"' not in dashboard_routes
    assert "f\"/#/tripulantes/{item['tripulante_id']}\"" in dashboard_routes
    assert "Ver piloto" not in dashboard_template
    assert "Abrir cadastro" in dashboard_template


def test_individual_report_document_has_explicit_spa_return_and_document_markers():
    template = _read(BACKEND_SRC / "templates" / "relatorio_tripulante.html")
    legacy_list = _read(BACKEND_SRC / "templates" / "tripulantes_list.html")

    assert 'href="/#/relatorios/individual"' in template
    assert 'data-boundary="spa-selector-return"' in template
    assert 'href="/#/tripulantes/{{ tripulante.id }}"' in template
    assert 'data-boundary="ssr_document_pdf"' in template
    assert 'data-boundary="ssr_document_read_model"' in legacy_list
    assert "Documento individual" in legacy_list


def test_individual_report_boundary_is_documented_and_indexed():
    migration = _read(MIGRATION_DOC)
    readme = _read(README)
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    assert "97.individual-report-boundary-hardening.md" in readme
    assert "`#/relatorios/individual`" in migration
    assert "`/tripulantes/<id>/relatorio`" in migration
    assert "`hibrido_documental_blindado`" in migration
    assert "`hibrido_documental_blindado`" in architecture
