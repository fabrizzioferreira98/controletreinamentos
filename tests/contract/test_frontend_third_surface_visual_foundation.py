from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_third_surface_choice_is_live_routed_and_documented():
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    migration = _read(ROOT / "docs" / "migration" / "31.g07-aplicar-padroes-compartilhados-terceira-superficie.md")

    assert '"#/tripulantes/new"' in route_registry
    assert "renderTripulanteFormPage" in route_registry
    assert 'pattern: /^#\\/tripulantes\\/\\d+$/' in route_registry

    for expected in (
        "Aplicacao da fundacao visual na terceira superficie",
        "`tripulante_form_detail`",
        "`#/tripulantes/new`",
        "`#/tripulantes/<id>`",
        "`fechado`",
    ):
        assert expected in architecture
        assert expected in migration


def test_tripulante_form_detail_adopts_foundation_and_shared_table_form_patterns():
    source = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")

    for expected in (
        "tripulante-detail-page-shell priority-page-surface ui-page-shell ui-stack",
        "page-header entity-detail-header priority-page-header ui-page-header ui-surface",
        "entity-status-row ui-cluster",
        "tripulante-entity-form ui-form-grid",
        "entity-form-section ui-surface ui-stack",
        "section-feedback ui-field-help",
        "field-feedback ui-field-help",
        "field-help ui-field-help",
        "tripulante-photo-preview-card ui-surface",
        "tripulante-document-panel ui-surface ui-stack",
        'data-tripulante-section="identity"',
        'data-tripulante-section="operation"',
        'data-tripulante-section="media"',
        'data-tripulante-section="documents"',
        "document-upload-form ui-form-toolbar",
        "document-preview-card ui-surface",
        "ui-table-wrap ui-table-density-compact",
        "actions ui-table-actions",
        "empty ui-table-state",
    ):
        assert expected in source


def test_tripulante_form_detail_preserves_functional_contracts():
    source = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")

    for preserved in (
        'id="tripulante-form"',
        'id="tripulanteFormSubmit"',
        'id="tripulanteDeleteButton"',
        'id="tripulante-file-form"',
        'id="tripulanteFileSubmit"',
        'id="tripulantePhotoUpload"',
        'id="tripulantePhotoRemove"',
        'api("/api/v1/tripulantes/options")',
        "api(`/api/v1/tripulantes/${tripulanteId}`",
        "api(`/api/v1/tripulantes/${tripulanteId}/files`",
        "api(`/api/v1/tripulantes/${tripulanteId}/photo`",
        "PHOTO_ALLOWED_MIME_TYPES",
        "PHOTO_MAX_BYTES",
        "classifyPhotoSelection(file)",
        "classifyPhotoUploadFailure(error, file)",
        "assertPhotoUploadConfirmed(result)",
        "tripulante_photo_blob_unavailable",
        "pré-visualização local; ainda não salva",
        "envio confirmado. Foto salva e disponível para exibição.",
        "Documentos do tripulante",
        "Arquivos PDF vinculados ao cadastro.",
        "Adicionar documento PDF",
        "Modo de envio",
        "Visualização indisponível",
        "O registro existe, mas o arquivo não está acessível no armazenamento atual. Visualização e download foram bloqueados.",
        "Identificação",
        "Código ANAC",
        "Operação",
        "Função operacional",
        "Arquivos visuais e observações",
        "Salvar alterações",
        "withActionBusy(",
        "setFieldFeedback(",
        "validateTripulanteForm()",
        "wireTripulantePhotoFallbacks()",
    ):
        assert preserved in source

    assert "Ãƒ" not in source
    assert "Ã‚" not in source
    for removed_microcopy in (
        "Aba File",
        "Persistencia do envio",
        "Selecao",
        "Sem preview",
        "Arquivo fisico indisponivel no storage atual",
        "Preview embutido indisponivel",
        "Carregando preview autenticado",
        "Foto salva e disponivel",
        "pre-visualizacao local",
    ):
        assert removed_microcopy not in source


def test_tripulante_form_detail_css_is_scoped_and_token_based():
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "G07: tripulante form/detail adopts shared visual foundation",
        ".tripulante-detail-page-shell",
        "40: tripulante detail broad visual refinement without functional drift.",
        ".tripulante-detail-page-shell > .priority-page-header",
        ".tripulante-detail-page-shell .tripulante-entity-form.ui-form-grid",
        ".tripulante-detail-page-shell .entity-form-section.ui-surface",
        ".tripulante-detail-page-shell .entity-form-section[data-tripulante-section]",
        ".tripulante-detail-page-shell .tripulante-document-panel.ui-surface",
        ".tripulante-detail-page-shell .section-feedback.ui-field-help",
        ".tripulante-detail-page-shell .tripulante-photo-preview-card.ui-surface",
        ".tripulante-detail-page-shell .tripulante-photo-actions",
        ".tripulante-detail-page-shell .document-library-row.is-selected td",
        ".tripulante-detail-page-shell .document-detail-actions.ui-detail-actions",
        ".tripulante-detail-page-shell .document-preview-card.ui-surface",
        "var(--space-panel-gap)",
        "var(--space-stack-sm)",
        "var(--space-layout-content-mobile)",
        "var(--radius-surface)",
        "var(--shadow-surface)",
        "var(--shadow-interactive)",
        "var(--color-state-default-surface)",
    ):
        assert expected in app_css
