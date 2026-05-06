from __future__ import annotations

import os
import uuid

import pytest

from backend.src.controle_treinamentos.application.financeiro_missoes import (
    CompetenciaFinanceiraFechadaErro,
    criar_missao_operacional,
)
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

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
            f"Finance App User {token}",
            f"finance_app_{token}",
            f"finance_app_{token}@local.test",
            "test-hash",
        ),
    ).fetchone()["id"]
    comandante_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Comandante App {token}", _cpf(), f"AA{token[:5]}"),
    ).fetchone()["id"]
    copiloto_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Copiloto App {token}", _cpf(), f"AB{token[:5]}"),
    ).fetchone()["id"]
    aeronave_id = db.execute(
        """
        INSERT INTO equipamentos (nome, tipo, ativo)
        VALUES (%s, 'aeronave', 1)
        RETURNING id
        """,
        (f"Aeronave App {token}",),
    ).fetchone()["id"]
    return {
        "user_id": user_id,
        "comandante_id": comandante_id,
        "copiloto_id": copiloto_id,
        "aeronave_id": aeronave_id,
        "token": token,
    }


def _payload(refs: dict[str, int], *, org_id: str = FINANCE_ORG_SCOPE_DEFAULT, competencia: str = "2026-08") -> dict:
    token = uuid.uuid4().hex[:8]
    return {
        "org_id": org_id,
        "competencia": competencia,
        "data_missao": f"{competencia}-10",
        "cavok_numero_voo": f"CAVOK-APP-{token}",
        "contratante": f"Cliente App {token}",
        "chamado": f"APP-{token}",
        "aeronave_id": refs["aeronave_id"],
        "categoria_financeira_aeronave": "A",
        "comandante_tripulante_id": refs["comandante_id"],
        "copiloto_tripulante_id": refs["copiloto_id"],
        "horario_apresentacao": f"{competencia}-10 08:00:00",
        "horario_abandono": f"{competencia}-10 18:00:00",
        "trecho": "BSB-GRU",
        "status": "ativa",
    }


def test_criar_missao_operacional_persists_participants_and_audit_event(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)

    result = criar_missao_operacional(
        _payload(refs, competencia="2026-08"),
        actor_user_id=refs["user_id"],
        db=bootstrapped_db,
    )

    participants = bootstrapped_db.execute(
        """
        SELECT tripulante_id, funcao
        FROM financeiro_missao_tripulantes
        WHERE org_id = %s
          AND missao_operacional_id = %s
        ORDER BY funcao
        """,
        (FINANCE_ORG_SCOPE_DEFAULT, result["id"]),
    ).fetchall()
    audit = bootstrapped_db.execute(
        """
        SELECT entidade, entidade_id, acao, payload_anterior, payload_novo, realizado_por
        FROM auditoria_eventos
        WHERE entidade = 'finance_mission'
          AND entidade_id = %s
          AND acao = 'finance.mission.created'
        ORDER BY id DESC
        LIMIT 1
        """,
        (result["id"],),
    ).fetchone()

    assert result["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert {row["funcao"] for row in participants} == {"comandante", "copiloto"}
    assert audit["payload_anterior"] is None
    assert audit["payload_novo"]["audit_metadata"]["event_name"] == "finance.mission.created"
    assert audit["realizado_por"] == refs["user_id"]


def test_competencia_fechada_blocks_create_before_persisting_mission(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    org_id = f"test_org_{refs['token']}"
    bootstrapped_db.execute(
        """
        INSERT INTO financeiro_competencias (org_id, competencia, status)
        VALUES (%s, '2026-09', 'fechada')
        """,
        (org_id,),
    )

    with pytest.raises(CompetenciaFinanceiraFechadaErro):
        criar_missao_operacional(
            _payload(refs, org_id=org_id, competencia="2026-09"),
            actor_user_id=refs["user_id"],
            org_id=org_id,
            db=bootstrapped_db,
        )

    row = bootstrapped_db.execute(
        """
        SELECT COUNT(*) AS total
        FROM financeiro_missoes_operacionais
        WHERE org_id = %s
          AND competencia = '2026-09'
        """,
        (org_id,),
    ).fetchone()
    assert int(row["total"]) == 0
