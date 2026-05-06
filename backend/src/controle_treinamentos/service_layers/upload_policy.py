"""Upload policy shared by API, SSR and application validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..constants import (
    MAX_PHOTO_BYTES,
    PHOTO_ALLOWED_MIME,
    TRAINING_ATTACHMENT_ALLOWED_MIME,
    TRAINING_ATTACHMENT_MAX_BYTES,
    TRIPULANTE_FILE_ALLOWED_MIME,
    TRIPULANTE_FILE_MAX_BYTES,
)


@dataclass(frozen=True)
class UploadPolicy:
    key: str
    domain: str
    accepted_extensions: tuple[str, ...]
    accepted_mime_types: frozenset[str]
    compatible_declared_mime_types: frozenset[str]
    canonical_mime_type: str
    max_bytes: int
    fallback_filename: str
    physical_name_kind: str
    required_permissions: tuple[str, ...]
    deduplication: str
    metadata_fields: tuple[str, ...]

    @property
    def max_mb(self) -> int:
        return max(1, self.max_bytes // (1024 * 1024))

    def normalize_declared_mime(self, value: str | None) -> str:
        raw = (value or "").strip().lower()
        return raw.split(";", 1)[0].strip()

    def accepts_declared_mime(self, value: str | None) -> bool:
        normalized = self.normalize_declared_mime(value)
        return normalized in self.accepted_mime_types or normalized in self.compatible_declared_mime_types

    def accepts_extension(self, filename: str | None) -> bool:
        lowered = (filename or "").strip().lower()
        return any(lowered.endswith(extension) for extension in self.accepted_extensions)


PDF_CONTENT_SIGNATURE: Final[bytes] = b"%PDF"
PDF_EOF_MARKER: Final[bytes] = b"%%EOF"
PDF_EOF_SCAN_BYTES: Final[int] = 4096
PDF_COMPATIBLE_DECLARED_MIME: Final[frozenset[str]] = frozenset({"", "application/octet-stream"})

PDF_METADATA_FIELDS: Final[tuple[str, ...]] = (
    "nome_original",
    "nome_interno",
    "mime_type",
    "tamanho_bytes",
    "arquivo_hash",
    "storage_ref",
    "enviado_por",
    "enviado_em",
    "status",
)


TRAINING_ATTACHMENT_UPLOAD_POLICY: Final[UploadPolicy] = UploadPolicy(
    key="training_attachment_pdf",
    domain="treinamentos.anexos",
    accepted_extensions=(".pdf",),
    accepted_mime_types=frozenset(TRAINING_ATTACHMENT_ALLOWED_MIME),
    compatible_declared_mime_types=PDF_COMPATIBLE_DECLARED_MIME,
    canonical_mime_type="application/pdf",
    max_bytes=TRAINING_ATTACHMENT_MAX_BYTES,
    fallback_filename="anexo.pdf",
    physical_name_kind="training_attachment",
    required_permissions=("treinamentos_anexos:create",),
    deduplication="reject_same_training_record_hash",
    metadata_fields=PDF_METADATA_FIELDS,
)

TRAINING_PROGRAM_EVIDENCE_UPLOAD_POLICY: Final[UploadPolicy] = UploadPolicy(
    key="training_program_evidence_pdf",
    domain="treinamentos.programa.evidencias",
    accepted_extensions=(".pdf",),
    accepted_mime_types=frozenset(TRAINING_ATTACHMENT_ALLOWED_MIME),
    compatible_declared_mime_types=PDF_COMPATIBLE_DECLARED_MIME,
    canonical_mime_type="application/pdf",
    max_bytes=TRAINING_ATTACHMENT_MAX_BYTES,
    fallback_filename="anexo.pdf",
    physical_name_kind="training_attachment",
    required_permissions=("treinamentos:create", "treinamentos_anexos:create"),
    deduplication="reject_same_training_record_hash",
    metadata_fields=PDF_METADATA_FIELDS,
)

TRIPULANTE_FILE_UPLOAD_POLICY: Final[UploadPolicy] = UploadPolicy(
    key="tripulante_file_pdf",
    domain="tripulantes.file",
    accepted_extensions=(".pdf",),
    accepted_mime_types=frozenset(TRIPULANTE_FILE_ALLOWED_MIME),
    compatible_declared_mime_types=PDF_COMPATIBLE_DECLARED_MIME,
    canonical_mime_type="application/pdf",
    max_bytes=TRIPULANTE_FILE_MAX_BYTES,
    fallback_filename="documento_tripulante.pdf",
    physical_name_kind="tripulante_document",
    required_permissions=("tripulantes_file:create",),
    deduplication="reject_same_tripulante_active_hash",
    metadata_fields=PDF_METADATA_FIELDS + ("tipo_documento", "substitui_arquivo_id"),
)

TRIPULANTE_PHOTO_UPLOAD_POLICY: Final[UploadPolicy] = UploadPolicy(
    key="tripulante_photo_image",
    domain="tripulantes.foto",
    accepted_extensions=(".jpg", ".jpeg", ".png", ".webp"),
    accepted_mime_types=frozenset(PHOTO_ALLOWED_MIME),
    compatible_declared_mime_types=frozenset(),
    canonical_mime_type="",
    max_bytes=MAX_PHOTO_BYTES,
    fallback_filename="foto",
    physical_name_kind="tripulante_photo",
    required_permissions=("tripulantes:edit",),
    deduplication="replace_current_photo",
    metadata_fields=("foto_storage_ref", "foto_mime_type", "possui_foto"),
)

UPLOAD_POLICIES: Final[dict[str, UploadPolicy]] = {
    policy.key: policy
    for policy in (
        TRAINING_ATTACHMENT_UPLOAD_POLICY,
        TRAINING_PROGRAM_EVIDENCE_UPLOAD_POLICY,
        TRIPULANTE_FILE_UPLOAD_POLICY,
        TRIPULANTE_PHOTO_UPLOAD_POLICY,
    )
}


def get_upload_policy(key: str) -> UploadPolicy:
    policy = UPLOAD_POLICIES.get((key or "").strip())
    if policy is None:
        raise KeyError(f"Politica de upload desconhecida: {key}")
    return policy
