import pytest

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.core.domain_errors import DomainUnexpectedError
from backend.src.controle_treinamentos.core.pdf_document_policy import (
    HABILITACOES_EXPORT_PDF_POLICY,
    PDF_DOCUMENT_POLICIES,
    PDFDocumentPolicy,
    REPORTLAB_A4_BRANDED_LAYOUT,
    SIGNED_DOCUMENT_RESERVED_POLICY,
    TRAINING_ATTACHMENT_EVIDENCE_PDF_POLICY,
    TRIPULANTE_FILE_EVIDENCE_PDF_POLICY,
    build_pdf_document_response,
    pdf_document_policy_contract,
)


def test_pdf_document_taxonomy_distinguishes_export_evidence_signed_and_temporary():
    kinds = {policy.kind for policy in PDF_DOCUMENT_POLICIES.values()}

    assert "pdf_export" in kinds
    assert "pdf_evidence" in kinds
    assert "signed_document" in kinds
    assert "temporary_document" in kinds
    assert SIGNED_DOCUMENT_RESERVED_POLICY.signature_semantics == (
        "requires_explicit_signer_identity_integrity_and_timestamp"
    )


def test_generated_pdf_exports_share_the_branded_a4_layout():
    generated = [
        policy
        for policy in PDF_DOCUMENT_POLICIES.values()
        if policy.kind in {"pdf_export", "temporary_document"}
    ]

    assert generated
    assert {policy.layout_key for policy in generated} == {REPORTLAB_A4_BRANDED_LAYOUT}
    assert all(policy.storage == "temporary_response" for policy in generated)
    assert all(policy.retention == "not_persisted" for policy in generated)


def test_evidence_pdf_policy_declares_persistent_storage_versioning_and_hash_semantics():
    training_payload = pdf_document_policy_contract(TRAINING_ATTACHMENT_EVIDENCE_PDF_POLICY)
    tripulante_payload = pdf_document_policy_contract(TRIPULANTE_FILE_EVIDENCE_PDF_POLICY)

    assert training_payload["kind"] == "pdf_evidence"
    assert training_payload["storage"] == "persistent_document_storage"
    assert training_payload["versioning"] == "append_only_with_soft_delete"
    assert training_payload["signature_semantics"] == "unsigned_uploaded_evidence_hash_tracked"
    assert tripulante_payload["versioning"] == "replace_marks_previous_as_substituido"
    assert tripulante_payload["evidence_level"] == "documentary_evidence"


def test_build_pdf_document_response_adds_document_headers():
    app = create_app()
    with app.test_request_context("/relatorio.pdf"):
        response = build_pdf_document_response(
            policy=HABILITACOES_EXPORT_PDF_POLICY,
            payload_bytes=b"%PDF-test\n%%EOF",
            filename="relatorio.pdf",
            entity_id="2026-04",
        )

    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-test\n%%EOF"
    assert response.headers["Content-Disposition"] == "attachment; filename=relatorio.pdf"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "habilitacoes_export_pdf"
    assert response.headers["X-Document-Kind"] == "pdf_export"
    assert response.headers["X-Document-Template"] == "treinamentos_brasilvida.report.v1"
    assert response.headers["X-Document-Layout"] == REPORTLAB_A4_BRANDED_LAYOUT
    assert response.headers["X-Document-Storage"] == "temporary_response"
    assert response.headers["X-Document-Signature"] == "unsigned_system_generated"


def test_build_pdf_document_response_rejects_non_pdf_payload():
    app = create_app()
    with app.test_request_context("/relatorio.pdf"):
        with pytest.raises(DomainUnexpectedError) as exc_info:
            build_pdf_document_response(
                policy=HABILITACOES_EXPORT_PDF_POLICY,
                payload_bytes=b"not-a-pdf",
                filename="relatorio.pdf",
            )

    assert exc_info.value.code == "habilitacoes_export_pdf_invalid_pdf_signature"


def test_build_pdf_document_response_rejects_pdf_without_eof_marker():
    app = create_app()
    with app.test_request_context("/relatorio.pdf"):
        with pytest.raises(DomainUnexpectedError) as exc_info:
            build_pdf_document_response(
                policy=HABILITACOES_EXPORT_PDF_POLICY,
                payload_bytes=b"%PDF-broken",
                filename="relatorio.pdf",
            )

    assert exc_info.value.code == "habilitacoes_export_pdf_invalid_pdf_eof"


def test_generated_pdf_policy_requires_official_visual_contract():
    invalid_policy = PDFDocumentPolicy(
        key="broken_export_pdf",
        kind="pdf_export",
        domain="relatorios.broken",
        data_contract="broken",
        renderer="broken",
        template_key="ad_hoc_template",
        layout_key=REPORTLAB_A4_BRANDED_LAYOUT,
        storage="temporary_response",
        versioning="rendered_snapshot_at_request",
        retention="not_persisted",
        signature_semantics="unsigned_system_generated",
        evidence_level="operational_export",
    )
    app = create_app()
    with app.test_request_context("/relatorio.pdf"):
        with pytest.raises(DomainUnexpectedError) as exc_info:
            build_pdf_document_response(
                policy=invalid_policy,
                payload_bytes=b"%PDF-test\n%%EOF",
                filename="relatorio.pdf",
            )

    assert exc_info.value.code == "broken_export_pdf_invalid_visual_contract"
