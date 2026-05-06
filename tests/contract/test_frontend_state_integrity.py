from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_critical_draft_state_is_session_scoped_baseline_bound_and_not_file_based() -> None:
    source = _read(FRONTEND_SRC / "state" / "draft-state.js")

    assert "CRITICAL_DRAFT_TTL_MS" in source
    assert "window.sessionStorage" in source
    assert "window.localStorage" not in source
    assert "stableDraftSignature" in source
    assert "baselineSignature" in source
    assert "clearDraft(formKey)" in source
    assert "readAsDataURL" not in source
    assert "FormData" not in source


def test_critical_form_guard_blocks_unintentional_exit_without_overlay_or_reload() -> None:
    source = _read(FRONTEND_SRC / "shared" / "forms" / "draft-protection.js")

    assert "beforeunload" in source
    assert 'closest?.("a[href]")' in source
    assert "window.confirm(DEFAULT_LEAVE_MESSAGE)" in source
    assert '"file"' in source
    assert "writeDraft(" in source
    assert "readDraft(" in source
    assert "clearDraft(" in source
    assert "formEl.dataset.dirtyState" in source
    assert "window.location.reload" not in source
    assert "setTimeout" not in source


def test_tripulante_edit_form_persists_only_scalar_draft_and_clears_after_commit() -> None:
    source = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")

    assert "wireCriticalFormDraftProtection" in source
    assert 'formKey: `tripulante:${tripulanteId || "new"}`' in source
    assert '"observacoes"' in source
    assert '"ativo"' in source
    assert '"tripulantePhotoInput"' not in source.split("includeFields:", 1)[1].split("],", 1)[0]
    assert '"arquivo_pdf"' not in source.split("includeFields:", 1)[1].split("],", 1)[0]
    assert 'tripulanteDraft?.clear({ reason: "save_success" })' in source
    assert 'tripulanteDraft?.clear({ reason: "delete_success" })' in source


def test_tripulante_form_includes_selected_photo_when_saving_record() -> None:
    source = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")
    submit_block = source.split(
        'document.getElementById("tripulante-form")?.addEventListener("submit"',
        1,
    )[1].split('document.getElementById("tripulanteDeleteButton")', 1)[0]

    assert "async function attachSelectedPhotoToPayload(payload)" in source
    assert "const file = photoInput?.files?.[0]" in source
    assert "payload.foto_base64 = await fileToDataUrl(file)" in source
    assert "const photoAttached = await attachSelectedPhotoToPayload(payload)" in submit_block
    assert "if (!photoAttached) return" in submit_block
    assert "json: payload" in submit_block


def test_training_record_and_batch_flows_preserve_progress_without_replaying_pdfs() -> None:
    form_source = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    list_source = _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")
    helpers_source = _read(FRONTEND_SRC / "features" / "treinamentos" / "program-helpers.js")

    assert 'formKey: `treinamento:${treinamentoId}`' in form_source
    assert '"data_realizacao"' in form_source
    assert '"observacao"' in form_source
    assert 'trainingDraft?.clear({ reason: "save_success" })' in form_source

    assert 'name="segmento_${segment.id}"' in helpers_source
    assert "batchDraftBaselineFields()" in list_source
    assert 'formKey: `treinamentos:batch:' in list_source
    baseline_block = list_source.split("function batchDraftBaselineFields()", 1)[1].split("function updateContinueButton", 1)[0]
    assert "arquivo_" not in baseline_block
    assert 'batchDraft?.clear({ reason: "save_success" })' in list_source
    assert 'batchDraft?.clear({ reason: "manual_reset" })' in list_source


def test_training_root_admin_forms_are_protected_and_invalidated_on_commit_or_cancel() -> None:
    source = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")

    assert 'formKey: `treinamento-raiz:tipo:' in source
    assert 'formKey: `treinamento-raiz:segmento:' in source
    assert 'formKey: `treinamento-raiz:horas:' in source
    assert 'typeDraft?.clear({ reason: "save_success" })' in source
    assert 'segmentDraft?.clear({ reason: "save_success" })' in source
    assert 'hourDraft?.clear({ reason: "save_success" })' in source
    assert 'typeDraft?.clear({ reason: "cancel_edit" })' in source
    assert 'segmentDraft?.clear({ reason: "cancel_edit" })' in source
    assert 'hourDraft?.clear({ reason: "cancel_edit" })' in source


def test_state_integrity_migration_is_indexed() -> None:
    readme = _read(ROOT / "README.md")
    migration = ROOT / "docs" / "migration" / "78.frontend-state-integrity-critical-drafts.md"

    assert migration.exists()
    assert "78.frontend-state-integrity-critical-drafts.md" in readme
