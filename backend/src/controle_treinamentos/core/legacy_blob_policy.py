from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

LEGACY_BLOB_WRITE_MODE: Final[str] = "blocked_new_writes"
LEGACY_BLOB_READ_MODE: Final[str] = "isolated_fallback"
LEGACY_BLOB_CONTRACT_MODE: Final[str] = "explicit_compat_residual"
LEGACY_BLOB_HOT_PATH_MODE: Final[str] = "out_of_hot_path"

LEGACY_PHOTO_BLOB_COMPAT_SOURCE: Final[str] = "foto_base64"
LEGACY_DATABASE_BLOB_COMPAT_SOURCE: Final[str] = "db:bytea"


@dataclass(frozen=True)
class LegacyBlobSurface:
    key: str
    domain: str
    table: str
    legacy_field: str
    canonical_owner: str
    write_mode: str
    read_mode: str
    hot_path_mode: str
    contract_mode: str
    death_condition: str


LEGACY_BLOB_SURFACES: Final[dict[str, LegacyBlobSurface]] = {
    "tripulante_photo": LegacyBlobSurface(
        key="tripulante_photo",
        domain="tripulantes.foto",
        table="tripulantes",
        legacy_field="foto_base64",
        canonical_owner="tripulantes.foto_storage_ref",
        write_mode=LEGACY_BLOB_WRITE_MODE,
        read_mode=LEGACY_BLOB_READ_MODE,
        hot_path_mode=LEGACY_BLOB_HOT_PATH_MODE,
        contract_mode=LEGACY_BLOB_CONTRACT_MODE,
        death_condition=(
            "migrar ou limpar todas as linhas com foto_base64 residual, provar ausencia de leitura "
            "por fallback e remover a coluna em migracao dedicada"
        ),
    ),
    "tripulante_document": LegacyBlobSurface(
        key="tripulante_document",
        domain="tripulantes.file",
        table="tripulante_arquivos_pdf",
        legacy_field="arquivo_pdf",
        canonical_owner="tripulante_arquivos_pdf.storage_ref",
        write_mode=LEGACY_BLOB_WRITE_MODE,
        read_mode=LEGACY_BLOB_READ_MODE,
        hot_path_mode=LEGACY_BLOB_HOT_PATH_MODE,
        contract_mode=LEGACY_BLOB_CONTRACT_MODE,
        death_condition=(
            "migrar blobs db:bytea restantes para fs:, zerar inventario legado e remover fallback/coluna "
            "em migracao dedicada"
        ),
    ),
    "training_attachment": LegacyBlobSurface(
        key="training_attachment",
        domain="treinamentos.anexos",
        table="treinamento_anexos_pdf",
        legacy_field="arquivo_pdf",
        canonical_owner="treinamento_anexos_pdf.storage_ref",
        write_mode=LEGACY_BLOB_WRITE_MODE,
        read_mode=LEGACY_BLOB_READ_MODE,
        hot_path_mode=LEGACY_BLOB_HOT_PATH_MODE,
        contract_mode=LEGACY_BLOB_CONTRACT_MODE,
        death_condition=(
            "migrar anexos db:bytea restantes para fs:, provar restore sem dependencia do fallback "
            "e remover fallback/coluna em migracao dedicada"
        ),
    ),
}


def legacy_blob_surface(key: str) -> LegacyBlobSurface:
    surface = LEGACY_BLOB_SURFACES.get((key or "").strip())
    if surface is None:
        raise KeyError(f"Superficie de blob legado desconhecida: {key}")
    return surface


def legacy_blob_policy_contract(
    key: str,
    *,
    compat_residual: bool = False,
    compat_source: str = "",
) -> dict:
    surface = legacy_blob_surface(key)
    return {
        "canonical_owner": surface.canonical_owner,
        "legacy_field": surface.legacy_field,
        "legacy_write": surface.write_mode,
        "legacy_read": surface.read_mode,
        "hot_path": surface.hot_path_mode,
        "contract_mode": surface.contract_mode,
        "compat_residual": bool(compat_residual),
        "compat_source": (compat_source or "").strip(),
    }


def legacy_blob_blocked_writers() -> tuple[dict, ...]:
    return tuple(
        {
            "key": surface.key,
            "table": surface.table,
            "legacy_field": surface.legacy_field,
            "canonical_owner": surface.canonical_owner,
            "write_mode": surface.write_mode,
        }
        for surface in LEGACY_BLOB_SURFACES.values()
        if surface.write_mode == LEGACY_BLOB_WRITE_MODE
    )


def legacy_blob_fallbacks() -> tuple[dict, ...]:
    return tuple(
        {
            "key": surface.key,
            "legacy_field": surface.legacy_field,
            "read_mode": surface.read_mode,
            "hot_path": surface.hot_path_mode,
        }
        for surface in LEGACY_BLOB_SURFACES.values()
        if surface.read_mode == LEGACY_BLOB_READ_MODE
    )


def legacy_blob_death_plan() -> dict[str, dict]:
    return {
        key: {
            **asdict(surface),
            "status": "residual_until_exit_condition_is_proven",
        }
        for key, surface in LEGACY_BLOB_SURFACES.items()
    }
