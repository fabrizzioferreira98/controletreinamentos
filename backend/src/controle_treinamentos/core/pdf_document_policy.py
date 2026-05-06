from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from flask import Response, current_app, g, has_app_context
from flask_login import current_user

from .domain_errors import DomainUnexpectedError
from .metrics import record_pdf_response

PDFDocumentKind = Literal["pdf_export", "pdf_evidence", "signed_document", "temporary_document"]
GENERATED_PDF_KINDS: Final[frozenset[str]] = frozenset({"pdf_export", "temporary_document"})
PDF_DOCUMENT_EOF_MARKER: Final[bytes] = b"%%EOF"
PDF_DOCUMENT_EOF_SCAN_BYTES: Final[int] = 4096


@dataclass(frozen=True)
class PDFDocumentPolicy:
    key: str
    kind: PDFDocumentKind
    domain: str
    data_contract: str
    renderer: str
    template_key: str
    layout_key: str
    storage: str
    versioning: str
    retention: str
    signature_semantics: str
    evidence_level: str
    cache_control: str = "no-store"
    download_disposition: str = "attachment"


REPORTLAB_A4_BRANDED_LAYOUT = "reportlab.a4.branded.v1"
REPORTLAB_BRAND_TEMPLATE = "treinamentos_brasilvida.report.v1"

HABILITACOES_EXPORT_PDF_POLICY = PDFDocumentPolicy(
    key="habilitacoes_export_pdf",
    kind="pdf_export",
    domain="relatorios.habilitacoes",
    data_contract="habilitacoes_report_to_export_payload",
    renderer="build_habilitacoes_consolidado_pdf",
    template_key=REPORTLAB_BRAND_TEMPLATE,
    layout_key=REPORTLAB_A4_BRANDED_LAYOUT,
    storage="temporary_response",
    versioning="rendered_snapshot_at_request",
    retention="not_persisted",
    signature_semantics="unsigned_system_generated",
    evidence_level="operational_export",
)

TRIPULANTE_TREINAMENTOS_EXPORT_PDF_POLICY = PDFDocumentPolicy(
    key="tripulante_treinamentos_export_pdf",
    kind="pdf_export",
    domain="relatorios.tripulante.treinamentos",
    data_contract="fetch_training_rows + summarize_training_status",
    renderer="build_tripulante_treinamentos_pdf",
    template_key=REPORTLAB_BRAND_TEMPLATE,
    layout_key=REPORTLAB_A4_BRANDED_LAYOUT,
    storage="temporary_response",
    versioning="rendered_snapshot_at_request",
    retention="not_persisted",
    signature_semantics="unsigned_system_generated",
    evidence_level="operational_export",
)

AUDITORIA_EXPORT_PDF_POLICY = PDFDocumentPolicy(
    key="auditoria_export_pdf",
    kind="pdf_export",
    domain="auditoria.eventos",
    data_contract="audit_rows_query",
    renderer="build_auditoria_pdf",
    template_key=REPORTLAB_BRAND_TEMPLATE,
    layout_key=REPORTLAB_A4_BRANDED_LAYOUT,
    storage="temporary_response",
    versioning="rendered_snapshot_at_request",
    retention="not_persisted",
    signature_semantics="unsigned_system_generated",
    evidence_level="audit_export",
)

USER_GUIDE_PDF_POLICY = PDFDocumentPolicy(
    key="user_guide_pdf",
    kind="temporary_document",
    domain="manual.usuario",
    data_contract="static_manual_sections + emitted_at",
    renderer="build_user_guide_pdf",
    template_key=REPORTLAB_BRAND_TEMPLATE,
    layout_key=REPORTLAB_A4_BRANDED_LAYOUT,
    storage="temporary_response",
    versioning="rendered_snapshot_at_request",
    retention="not_persisted",
    signature_semantics="unsigned_system_generated",
    evidence_level="reference_document",
)

TRAINING_ATTACHMENT_EVIDENCE_PDF_POLICY = PDFDocumentPolicy(
    key="training_attachment_evidence_pdf",
    kind="pdf_evidence",
    domain="treinamentos.anexos",
    data_contract="treinamento_anexos_pdf metadata + storage_ref",
    renderer="uploaded_pdf_blob",
    template_key="external_pdf_template",
    layout_key="external_pdf_layout",
    storage="persistent_document_storage",
    versioning="append_only_with_soft_delete",
    retention="retained_until_governed_delete",
    signature_semantics="unsigned_uploaded_evidence_hash_tracked",
    evidence_level="documentary_evidence",
)

TRIPULANTE_FILE_EVIDENCE_PDF_POLICY = PDFDocumentPolicy(
    key="tripulante_file_evidence_pdf",
    kind="pdf_evidence",
    domain="tripulantes.file",
    data_contract="tripulante_arquivos_pdf metadata + storage_ref",
    renderer="uploaded_pdf_blob",
    template_key="external_pdf_template",
    layout_key="external_pdf_layout",
    storage="persistent_document_storage",
    versioning="replace_marks_previous_as_substituido",
    retention="retained_for_traceability",
    signature_semantics="unsigned_uploaded_evidence_hash_tracked",
    evidence_level="documentary_evidence",
)

SIGNED_DOCUMENT_RESERVED_POLICY = PDFDocumentPolicy(
    key="signed_document_reserved",
    kind="signed_document",
    domain="documentos.assinados",
    data_contract="not_active",
    renderer="not_active",
    template_key="not_active",
    layout_key="not_active",
    storage="not_active",
    versioning="not_active",
    retention="not_active",
    signature_semantics="requires_explicit_signer_identity_integrity_and_timestamp",
    evidence_level="not_active",
)

PDF_DOCUMENT_POLICIES: dict[str, PDFDocumentPolicy] = {
    policy.key: policy
    for policy in (
        HABILITACOES_EXPORT_PDF_POLICY,
        TRIPULANTE_TREINAMENTOS_EXPORT_PDF_POLICY,
        AUDITORIA_EXPORT_PDF_POLICY,
        USER_GUIDE_PDF_POLICY,
        TRAINING_ATTACHMENT_EVIDENCE_PDF_POLICY,
        TRIPULANTE_FILE_EVIDENCE_PDF_POLICY,
        SIGNED_DOCUMENT_RESERVED_POLICY,
    )
}


def pdf_document_policy_contract(policy: PDFDocumentPolicy) -> dict:
    return {
        "key": policy.key,
        "kind": policy.kind,
        "domain": policy.domain,
        "data_contract": policy.data_contract,
        "renderer": policy.renderer,
        "template_key": policy.template_key,
        "layout_key": policy.layout_key,
        "storage": policy.storage,
        "versioning": policy.versioning,
        "retention": policy.retention,
        "signature_semantics": policy.signature_semantics,
        "evidence_level": policy.evidence_level,
    }


def assert_pdf_document_payload(payload_bytes, *, policy: PDFDocumentPolicy) -> bytes:
    if isinstance(payload_bytes, bytes):
        data = payload_bytes
    elif isinstance(payload_bytes, bytearray):
        data = bytes(payload_bytes)
    elif isinstance(payload_bytes, memoryview):
        data = payload_bytes.tobytes()
    else:
        raise DomainUnexpectedError(
            "Documento PDF indisponivel para resposta.",
            code=f"{policy.key}_invalid_pdf_payload",
        )
    if not data:
        raise DomainUnexpectedError(
            "Documento PDF vazio para resposta.",
            code=f"{policy.key}_empty_pdf_payload",
        )
    if not data.startswith(b"%PDF"):
        raise DomainUnexpectedError(
            "Documento gerado nao possui assinatura PDF valida.",
            code=f"{policy.key}_invalid_pdf_signature",
        )
    if PDF_DOCUMENT_EOF_MARKER not in data[-PDF_DOCUMENT_EOF_SCAN_BYTES:]:
        raise DomainUnexpectedError(
            "Documento PDF gerado esta incompleto.",
            code=f"{policy.key}_invalid_pdf_eof",
        )
    return data


def assert_pdf_visual_contract(policy: PDFDocumentPolicy) -> None:
    if policy.kind not in GENERATED_PDF_KINDS:
        return
    if policy.template_key != REPORTLAB_BRAND_TEMPLATE or policy.layout_key != REPORTLAB_A4_BRANDED_LAYOUT:
        raise DomainUnexpectedError(
            "Documento PDF gerado sem contrato visual oficial.",
            code=f"{policy.key}_invalid_visual_contract",
        )


def audit_pdf_document(policy: PDFDocumentPolicy, *, filename: str, entity_id: int | str | None = None) -> None:
    if not has_app_context():
        return
    current_app.logger.info(
        "pdf_document policy=%s kind=%s domain=%s entity_id=%s filename=%s user_id=%s request_id=%s "
        "template=%s layout=%s storage=%s signature=%s",
        policy.key,
        policy.kind,
        policy.domain,
        entity_id,
        filename,
        getattr(current_user, "id", None),
        getattr(g, "request_id", None),
        policy.template_key,
        policy.layout_key,
        policy.storage,
        policy.signature_semantics,
    )


def _safe_header_filename(filename: str | None) -> str:
    value = str(filename or "documento.pdf").replace("\r", "").replace("\n", "").replace('"', "").strip()
    return value or "documento.pdf"


def build_pdf_document_response(
    *,
    policy: PDFDocumentPolicy,
    payload_bytes,
    filename: str,
    entity_id: int | str | None = None,
) -> Response:
    try:
        assert_pdf_visual_contract(policy)
        data = assert_pdf_document_payload(payload_bytes, policy=policy)
        safe_filename = _safe_header_filename(filename)
        audit_pdf_document(policy, filename=safe_filename, entity_id=entity_id)
        response = Response(data, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f"{policy.download_disposition}; filename={safe_filename}"
        response.headers["Cache-Control"] = policy.cache_control
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Document-Policy"] = policy.key
        response.headers["X-Document-Kind"] = policy.kind
        response.headers["X-Document-Template"] = policy.template_key
        response.headers["X-Document-Layout"] = policy.layout_key
        response.headers["X-Document-Storage"] = policy.storage
        response.headers["X-Document-Versioning"] = policy.versioning
        response.headers["X-Document-Signature"] = policy.signature_semantics
        response.headers["X-Document-Evidence"] = policy.evidence_level
        record_pdf_response(policy.key, policy.kind, "success", size_bytes=len(data))
        return response
    except Exception:
        record_pdf_response(policy.key, policy.kind, "failed")
        raise
