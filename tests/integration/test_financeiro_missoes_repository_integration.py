from __future__ import annotations

import os
import uuid

import pytest

from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from backend.src.controle_treinamentos.repositories.financeiro_missoes import (
    cancel_missao_operacional,
    create_missao_operacional_with_tripulantes,
    fetch_missao_operacional,
    fetch_missao_operacional_detail,
    find_duplicate_missao_operacional,
    insert_missao_tripulante,
    list_missao_tripulantes,
    list_missoes_operacionais,
    remover_missao_tripulantes,
    soft_delete_missao_operacional,
    update_missao_operacional,
)

SKIP_REASON = "DATABASE_URL not set or not pointing to test DB"


def _has_test_db() -> bool:
    url = (os.getenv("DATABASE_URL", "") or "").strip()
    return bool(url) and "test" in url.lower()


pytestmark = pytest.mark.skipif(not _has_test_db(), reason=SKIP_REASON)


@pytest.fixture()
def bootstrapped_db():
    from backend.src.controle_treinamentos import create_app
    from backend.src.controle_treinamentos.db import close_db, execute_schema_bootstrap, get_db

    app = create_app()
    with app.app_context():
        db = get_db()
        execute_schema_bootstrap(db)
        try:
            yield db
        finally:
            db.conn.rollback()
            close_db()


def _savepoint_rejects(db, callback) -> None:
    savepoint_name = f"finance_repo_sp_{uuid.uuid4().hex[:12]}"
    db.execute(f"SAVEPOINT {savepoint_name}")
    with pytest.raises(Exception):
        callback()
    db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
    db.execute(f"RELEASE SAVEPOINT {savepoint_name}")


def _cpf() -> str:
    return str(uuid.uuid4().int % 100_000_000_000).zfill(11)


def _seed_base_rows(db) -> dict[str, int]:
    token = uuid.uuid4().hex[:10]
    user_id = db.execute(
        """
        INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
        VALUES (%s, %s, %s, %s, 'operador', 1, '[]')
        RETURNING id
        """,
        (
            f"Finance Repo User {token}",
            f"finance_repo_{token}",
            f"finance_repo_{token}@local.test",
            "test-hash",
        ),
    ).fetchone()["id"]
    comandante_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Comandante Repo {token}", _cpf(), f"RA{token[:5]}"),
    ).fetchone()["id"]
    copiloto_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Copiloto Repo {token}", _cpf(), f"RB{token[:5]}"),
    ).fetchone()["id"]
    aeronave_id = db.execute(
        """
        INSERT INTO equipamentos (nome, tipo, ativo)
        VALUES (%s, 'aeronave', 1)
        RETURNING id
        """,
        (f"Aeronave Repo {token}",),
    ).fetchone()["id"]
    return {
        "user_id": user_id,
        "comandante_id": comandante_id,
        "copiloto_id": copiloto_id,
        "aeronave_id": aeronave_id,
    }


def _mission_payload(refs: dict[str, int], *, competencia: str = "2026-04") -> dict:
    token = uuid.uuid4().hex[:8]
    return {
        "competencia": competencia,
        "data_missao": f"{competencia}-10",
        "cavok_numero_voo": f"CAVOK-{token}",
        "contratante": f"Cliente {token}",
        "chamado": f"CH-{token}",
        "aeronave_id": refs["aeronave_id"],
        "categoria_financeira_aeronave": "A",
        "comandante_tripulante_id": refs["comandante_id"],
        "copiloto_tripulante_id": refs["copiloto_id"],
        "horario_apresentacao": f"{competencia}-10 08:00:00",
        "horario_abandono": f"{competencia}-10 18:00:00",
        "trecho": "BSB-GRU",
        "houve_pernoite": False,
        "quantidade_pernoites": 0,
        "cobertura_base": False,
        "operacao_especial": None,
        "status": "ativa",
        "observacoes": "repository test",
        "created_by": refs["user_id"],
        "updated_by": refs["user_id"],
    }


def test_create_operational_mission_inserts_participants_and_defaults_org(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    payload = _mission_payload(refs)

    mission = create_missao_operacional_with_tripulantes(bootstrapped_db, data=payload)
    participants = list_missao_tripulantes(bootstrapped_db, missao_operacional_id=mission["id"])
    detail = fetch_missao_operacional_detail(bootstrapped_db, missao_operacional_id=mission["id"])

    assert mission["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert {item["funcao"] for item in participants} == {"comandante", "copiloto"}
    assert {item["tripulante_id"] for item in participants} == {
        refs["comandante_id"],
        refs["copiloto_id"],
    }
    assert all("horario_apresentacao" not in item for item in participants)
    assert all("horario_abandono" not in item for item in participants)
    assert detail["id"] == mission["id"]
    assert len(detail["participantes"]) == 2

    duplicate = find_duplicate_missao_operacional(
        bootstrapped_db,
        cavok_numero_voo=payload["cavok_numero_voo"],
        contratante=payload["contratante"],
        chamado=payload["chamado"],
    )
    assert duplicate["id"] == mission["id"]
    assert (
        find_duplicate_missao_operacional(
            bootstrapped_db,
            cavok_numero_voo=payload["cavok_numero_voo"],
            contratante=payload["contratante"],
            chamado=payload["chamado"],
            org_id="other_test_org",
        )
        is None
    )
    assert (
        find_duplicate_missao_operacional(
            bootstrapped_db,
            cavok_numero_voo=payload["cavok_numero_voo"],
            contratante=payload["contratante"],
            chamado=payload["chamado"],
            exclude_id=mission["id"],
        )
        is None
    )


def test_list_detail_update_and_cancel_are_scoped_by_org_and_competencia(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    default_mission = create_missao_operacional_with_tripulantes(
        bootstrapped_db,
        data=_mission_payload(refs, competencia="2026-05"),
    )
    other_org_mission = create_missao_operacional_with_tripulantes(
        bootstrapped_db,
        data=_mission_payload(refs, competencia="2026-05"),
        org_id="other_test_org",
    )

    default_rows = list_missoes_operacionais(bootstrapped_db, competencia="2026-05")
    other_rows = list_missoes_operacionais(
        bootstrapped_db,
        competencia="2026-05",
        org_id="other_test_org",
    )
    empty_rows = list_missoes_operacionais(bootstrapped_db, competencia="2026-06")

    assert {row["id"] for row in default_rows} == {default_mission["id"]}
    assert {row["id"] for row in other_rows} == {other_org_mission["id"]}
    assert empty_rows == []
    assert (
        fetch_missao_operacional(
            bootstrapped_db,
            missao_operacional_id=default_mission["id"],
            org_id="other_test_org",
        )
        is None
    )

    updated = update_missao_operacional(
        bootstrapped_db,
        missao_operacional_id=default_mission["id"],
        data={"trecho": "BSB-CGH", "observacoes": "updated by repository", "updated_by": refs["user_id"]},
    )
    participants_after_update = list_missao_tripulantes(
        bootstrapped_db,
        missao_operacional_id=default_mission["id"],
    )
    cancelled = cancel_missao_operacional(
        bootstrapped_db,
        missao_operacional_id=default_mission["id"],
        updated_by=refs["user_id"],
    )
    after_cancel = fetch_missao_operacional_detail(
        bootstrapped_db,
        missao_operacional_id=default_mission["id"],
    )

    assert updated["trecho"] == "BSB-CGH"
    assert len(participants_after_update) == 2
    assert all("horario_apresentacao" not in item for item in participants_after_update)
    assert cancelled["status"] == "cancelada"
    assert after_cancel["status"] == "cancelada"
    assert len(after_cancel["participantes"]) == 2


def test_soft_deleted_mission_is_hidden_from_active_repository_queries(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    mission = create_missao_operacional_with_tripulantes(
        bootstrapped_db,
        data=_mission_payload(refs, competencia="2026-08"),
    )

    remover_missao_tripulantes(bootstrapped_db, missao_operacional_id=mission["id"])
    deleted = soft_delete_missao_operacional(
        bootstrapped_db,
        missao_operacional_id=mission["id"],
        deleted_by=refs["user_id"],
        delete_reason="erro de lancamento",
    )

    assert deleted["deleted_at"] is not None
    assert list_missoes_operacionais(bootstrapped_db, competencia="2026-08") == []
    assert fetch_missao_operacional(bootstrapped_db, missao_operacional_id=mission["id"]) is None
    assert fetch_missao_operacional_detail(bootstrapped_db, missao_operacional_id=mission["id"]) is None
    assert (
        fetch_missao_operacional(
            bootstrapped_db,
            missao_operacional_id=mission["id"],
            include_deleted=True,
        )["id"]
        == mission["id"]
    )


def test_repository_propagates_core_constraint_errors(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    same_tripulante_payload = _mission_payload(refs)
    same_tripulante_payload["copiloto_tripulante_id"] = refs["comandante_id"]

    _savepoint_rejects(
        bootstrapped_db,
        lambda: create_missao_operacional_with_tripulantes(bootstrapped_db, data=same_tripulante_payload),
    )

    mission = create_missao_operacional_with_tripulantes(
        bootstrapped_db,
        data=_mission_payload(refs, competencia="2026-07"),
    )
    _savepoint_rejects(
        bootstrapped_db,
        lambda: insert_missao_tripulante(
            bootstrapped_db,
            missao_operacional_id=mission["id"],
            tripulante_id=refs["copiloto_id"],
            funcao="comandante",
        ),
    )
