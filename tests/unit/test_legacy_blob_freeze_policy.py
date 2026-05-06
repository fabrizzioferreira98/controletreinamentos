from __future__ import annotations

import re
from pathlib import Path

from backend.src.controle_treinamentos.contracts.treinamentos import serialize_treinamento_attachment
from backend.src.controle_treinamentos.contracts.tripulante_media import serialize_tripulante_file_item
from backend.src.controle_treinamentos.core.document_storage import database_blob_for_persistence, document_blob_state
from backend.src.controle_treinamentos.core.legacy_blob_policy import (
    LEGACY_BLOB_READ_MODE,
    LEGACY_BLOB_WRITE_MODE,
    LEGACY_DATABASE_BLOB_COMPAT_SOURCE,
    LEGACY_PHOTO_BLOB_COMPAT_SOURCE,
    legacy_blob_blocked_writers,
    legacy_blob_death_plan,
    legacy_blob_fallbacks,
    legacy_blob_policy_contract,
)
from backend.src.controle_treinamentos.db.index_debt import duplicate_index_debt_items, index_debt_by_name


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend" / "src" / "controle_treinamentos"


def _source_text(*relative_paths: str) -> str:
    return "\n".join((ROOT / path).read_text(encoding="utf-8") for path in relative_paths)


def test_legacy_blob_policy_freezes_writers_and_records_death_plan():
    blocked = {item["key"]: item for item in legacy_blob_blocked_writers()}
    death_plan = legacy_blob_death_plan()

    assert blocked["tripulante_photo"]["legacy_field"] == "foto_base64"
    assert blocked["tripulante_photo"]["canonical_owner"] == "tripulantes.foto_storage_ref"
    assert blocked["tripulante_document"]["legacy_field"] == "arquivo_pdf"
    assert blocked["training_attachment"]["legacy_field"] == "arquivo_pdf"
    assert {item["write_mode"] for item in blocked.values()} == {LEGACY_BLOB_WRITE_MODE}
    assert "remover a coluna" in death_plan["tripulante_photo"]["death_condition"]
    assert "remover fallback/coluna" in death_plan["tripulante_document"]["death_condition"]


def test_legacy_blob_policy_marks_fallbacks_as_isolated():
    fallbacks = {item["key"]: item for item in legacy_blob_fallbacks()}

    assert fallbacks["tripulante_photo"]["read_mode"] == LEGACY_BLOB_READ_MODE
    assert fallbacks["tripulante_document"]["read_mode"] == LEGACY_BLOB_READ_MODE
    assert fallbacks["training_attachment"]["hot_path"] == "out_of_hot_path"


def test_new_database_blob_writes_stay_blocked_without_explicit_compat_flag():
    payload = {"storage_ref": LEGACY_DATABASE_BLOB_COMPAT_SOURCE, "arquivo_pdf": b"%PDF"}

    assert database_blob_for_persistence(payload) is None
    assert database_blob_for_persistence(payload, allow_legacy_database_blob=True) == b"%PDF"


def test_document_state_and_contracts_do_not_treat_legacy_blob_as_normal():
    state = document_blob_state({"storage_ref": LEGACY_DATABASE_BLOB_COMPAT_SOURCE, "arquivo_pdf": b"%PDF"})
    tripulante_file = serialize_tripulante_file_item(
        {
            "id": 91,
            "tripulante_id": 7,
            "storage_ref": LEGACY_DATABASE_BLOB_COMPAT_SOURCE,
            "blob_storage": state["blob_storage"],
            "blob_available": state["blob_available"],
            "blob_status": state["blob_status"],
            "compat_residual": state["compat_residual"],
            "compat_source": state["compat_source"],
        }
    )
    attachment = serialize_treinamento_attachment(
        {
            "id": 77,
            "treinamento_id": 55,
            "storage_ref": LEGACY_DATABASE_BLOB_COMPAT_SOURCE,
            "blob_storage": state["blob_storage"],
            "blob_available": state["blob_available"],
            "blob_status": state["blob_status"],
            "compat_residual": state["compat_residual"],
            "compat_source": state["compat_source"],
        }
    )

    assert state["compat_residual"] is True
    assert state["compat_source"] == LEGACY_DATABASE_BLOB_COMPAT_SOURCE
    assert tripulante_file["blob_policy"]["legacy_write"] == LEGACY_BLOB_WRITE_MODE
    assert tripulante_file["blob_policy"]["legacy_read"] == LEGACY_BLOB_READ_MODE
    assert tripulante_file["blob_policy"]["compat_residual"] is True
    assert attachment["blob_policy"]["canonical_owner"] == "treinamento_anexos_pdf.storage_ref"
    assert attachment["blob_policy"]["compat_source"] == LEGACY_DATABASE_BLOB_COMPAT_SOURCE


def test_photo_policy_contract_uses_explicit_legacy_source_name():
    contract = legacy_blob_policy_contract(
        "tripulante_photo",
        compat_residual=True,
        compat_source=LEGACY_PHOTO_BLOB_COMPAT_SOURCE,
    )

    assert contract["canonical_owner"] == "tripulantes.foto_storage_ref"
    assert contract["legacy_field"] == LEGACY_PHOTO_BLOB_COMPAT_SOURCE
    assert contract["legacy_write"] == LEGACY_BLOB_WRITE_MODE
    assert contract["legacy_read"] == LEGACY_BLOB_READ_MODE
    assert contract["compat_residual"] is True


def test_hot_path_source_does_not_opt_in_to_new_legacy_blob_writes():
    offenders = []
    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "allow_legacy_database_blob=True" in text:
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_hot_path_photo_writes_only_clear_legacy_base64():
    text = _source_text(
        "backend/src/controle_treinamentos/application/tripulantes.py",
        "backend/src/controle_treinamentos/application/tripulante_media.py",
        "backend/src/controle_treinamentos/repositories/tripulantes.py",
    )

    assert "foto_base64 = NULL" in text
    assert re.search(r"foto_base64\s*=\s*%s", text) is None


def test_legacy_photo_fallback_is_centralized_outside_bases_route():
    bases_route = _source_text("backend/src/controle_treinamentos/blueprints/bases/routes.py")

    assert "load_tripulante_photo_payload" in bases_route
    assert "_decode_photo_data_uri" not in bases_route
    assert "base64.b64decode" not in bases_route


def test_duplicate_index_review_is_objective_debt_not_destructive_cleanup():
    duplicate_names = {item["index_name"] for item in duplicate_index_debt_items()}
    all_debt = index_debt_by_name()

    assert duplicate_names == {
        "idx_treinamentos_tripulante_vencimento",
        "idx_treinamentos_vencimento",
    }
    assert all_debt["idx_treinamentos_tripulante_vencimento"]["duplicate_of"] == (
        "idx_treinamentos_tripulante_data_vencimento"
    )
    assert all_debt["idx_treinamentos_data_venc_tripulante"]["classification"] == "overlap_reversed_columns"
    assert "pg_stat_user_indexes" in all_debt["idx_treinamentos_vencimento"]["precondition_to_drop"]
