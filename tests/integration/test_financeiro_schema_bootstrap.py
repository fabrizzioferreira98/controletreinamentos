from __future__ import annotations

import os
import uuid

import pytest

FINANCE_TABLES = (
    "financeiro_missoes_operacionais",
    "financeiro_missao_tripulantes",
    "financeiro_parametros",
    "financeiro_feriados",
    "financeiro_competencias",
    "financeiro_calculos_horarios",
    "financeiro_calculos_produtividade",
    "financeiro_divergencias",
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


def _columns(db, table_name: str) -> set[str]:
    rows = db.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {row["column_name"] for row in rows}


def _org_default(db, table_name: str) -> str:
    row = db.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = 'org_id'
        """,
        (table_name,),
    ).fetchone()
    return str(row["column_default"] or "") if row else ""


def _constraint_names(db, table_name: str) -> set[str]:
    rows = db.execute(
        """
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {row["constraint_name"] for row in rows}


def _foreign_keys(db) -> set[tuple[str, str, str]]:
    rows = db.execute(
        """
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = ANY(%s)
        """,
        (list(FINANCE_TABLES),),
    ).fetchall()
    return {(row["table_name"], row["column_name"], row["foreign_table_name"]) for row in rows}


def _index_definitions(db) -> dict[str, str]:
    rows = db.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = ANY(%s)
        """,
        (list(FINANCE_TABLES),),
    ).fetchall()
    return {row["indexname"]: row["indexdef"] for row in rows}


def _savepoint_rejects(db, statement: str, params: tuple) -> None:
    savepoint_name = f"finance_test_sp_{uuid.uuid4().hex[:12]}"
    db.execute(f"SAVEPOINT {savepoint_name}")
    with pytest.raises(Exception):
        db.execute(statement, params)
    db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
    db.execute(f"RELEASE SAVEPOINT {savepoint_name}")


def _seed_base_rows(db) -> dict[str, int]:
    token = uuid.uuid4().hex[:10]
    digits = str(uuid.uuid4().int % 10_000_000_000).zfill(10)
    user_id = db.execute(
        """
        INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
        VALUES (%s, %s, %s, %s, 'operador', 1, '[]')
        RETURNING id
        """,
        (
            f"Finance Test User {token}",
            f"finance_test_{token}",
            f"finance_test_{token}@local.test",
            "test-hash",
        ),
    ).fetchone()["id"]
    comandante_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Comandante Test {token}", f"8{digits}", f"A{token[:5]}"),
    ).fetchone()["id"]
    copiloto_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Copiloto Test {token}", f"9{digits}", f"B{token[:5]}"),
    ).fetchone()["id"]
    equipamento_id = db.execute(
        """
        INSERT INTO equipamentos (nome, tipo, ativo)
        VALUES (%s, 'aeronave', 1)
        RETURNING id
        """,
        (f"Aeronave Test {token}",),
    ).fetchone()["id"]
    return {
        "user_id": user_id,
        "comandante_id": comandante_id,
        "copiloto_id": copiloto_id,
        "equipamento_id": equipamento_id,
    }


def _insert_missao_operacional(db, refs: dict[str, int]) -> dict:
    return dict(
        db.execute(
            """
            INSERT INTO financeiro_missoes_operacionais (
                competencia,
                data_missao,
                cavok_numero_voo,
                aeronave_id,
                comandante_tripulante_id,
                copiloto_tripulante_id,
                horario_apresentacao,
                horario_abandono,
                created_by
            )
            VALUES ('2026-04', '2026-04-10', %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, org_id
            """,
            (
                f"CAVOK-{uuid.uuid4().hex[:8]}",
                refs["equipamento_id"],
                refs["comandante_id"],
                refs["copiloto_id"],
                "2026-04-10 08:00:00",
                "2026-04-10 18:00:00",
                refs["user_id"],
            ),
        ).fetchone()
    )


def test_finance_bootstrap_creates_tables_columns_and_org_defaults(bootstrapped_db):
    rows = bootstrapped_db.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        """,
        (list(FINANCE_TABLES),),
    ).fetchall()

    assert {row["table_name"] for row in rows} == set(FINANCE_TABLES)
    for table_name in FINANCE_TABLES:
        assert "org_id" in _columns(bootstrapped_db, table_name)
        assert "default_single_tenant" in _org_default(bootstrapped_db, table_name)

    assert {"horario_apresentacao", "horario_abandono"} <= _columns(
        bootstrapped_db,
        "financeiro_missoes_operacionais",
    )
    assert "horario_apresentacao" not in _columns(bootstrapped_db, "financeiro_missao_tripulantes")
    assert "horario_abandono" not in _columns(bootstrapped_db, "financeiro_missao_tripulantes")


def test_finance_bootstrap_creates_fks_constraints_and_indexes(bootstrapped_db):
    foreign_keys = _foreign_keys(bootstrapped_db)
    indexes = _index_definitions(bootstrapped_db)

    assert (
        "financeiro_missoes_operacionais",
        "comandante_tripulante_id",
        "tripulantes",
    ) in foreign_keys
    assert (
        "financeiro_missoes_operacionais",
        "copiloto_tripulante_id",
        "tripulantes",
    ) in foreign_keys
    assert ("financeiro_missoes_operacionais", "aeronave_id", "equipamentos") in foreign_keys
    assert (
        "financeiro_missao_tripulantes",
        "missao_operacional_id",
        "financeiro_missoes_operacionais",
    ) in foreign_keys
    assert ("financeiro_missao_tripulantes", "tripulante_id", "tripulantes") in foreign_keys
    assert (
        "financeiro_calculos_horarios",
        "missao_operacional_id",
        "financeiro_missoes_operacionais",
    ) in foreign_keys
    assert ("financeiro_calculos_horarios", "tripulante_id", "tripulantes") in foreign_keys
    assert ("financeiro_calculos_produtividade", "tripulante_id", "tripulantes") in foreign_keys

    assert "financeiro_missoes_operacionais_tripulantes_distintos" in _constraint_names(
        bootstrapped_db,
        "financeiro_missoes_operacionais",
    )
    assert "financeiro_missoes_operacionais_horarios_validos" in _constraint_names(
        bootstrapped_db,
        "financeiro_missoes_operacionais",
    )
    assert "uq_financeiro_missao_tripulantes_org_missao_funcao" in _constraint_names(
        bootstrapped_db,
        "financeiro_missao_tripulantes",
    )
    assert "financeiro_parametros_vigencia_valida" in _constraint_names(
        bootstrapped_db,
        "financeiro_parametros",
    )
    assert "uq_financeiro_competencias_org_competencia" in _constraint_names(
        bootstrapped_db,
        "financeiro_competencias",
    )
    assert "uq_financeiro_calculos_produtividade_org_comp_trip_funcao" in _constraint_names(
        bootstrapped_db,
        "financeiro_calculos_produtividade",
    )

    for index_name in (
        "idx_financeiro_missoes_operacionais_org_competencia",
        "idx_financeiro_parametros_org_tipo_vigencia",
        "uq_financeiro_feriados_org_data_tipo_localidade",
        "idx_financeiro_calculos_horarios_org_missao_tripulante_funcao",
        "uq_financeiro_calculos_horarios_current",
        "idx_financeiro_calculos_produtividade_org_comp_trip_funcao",
        "idx_financeiro_divergencias_org_competencia_status",
    ):
        assert index_name in indexes
        assert "org_id" in indexes[index_name]


def test_finance_bootstrap_enforces_core_constraints_with_controlled_inserts(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    mission = _insert_missao_operacional(bootstrapped_db, refs)

    assert mission["org_id"] == "default_single_tenant"

    _savepoint_rejects(
        bootstrapped_db,
        """
        INSERT INTO financeiro_missoes_operacionais (
            competencia,
            data_missao,
            comandante_tripulante_id,
            copiloto_tripulante_id,
            horario_apresentacao,
            horario_abandono
        )
        VALUES ('2026-04', '2026-04-11', %s, %s, %s, %s)
        """,
        (
            refs["comandante_id"],
            refs["comandante_id"],
            "2026-04-11 08:00:00",
            "2026-04-11 18:00:00",
        ),
    )

    bootstrapped_db.execute(
        """
        INSERT INTO financeiro_missao_tripulantes (missao_operacional_id, tripulante_id, funcao)
        VALUES (%s, %s, 'comandante')
        """,
        (mission["id"], refs["comandante_id"]),
    )
    _savepoint_rejects(
        bootstrapped_db,
        """
        INSERT INTO financeiro_missao_tripulantes (missao_operacional_id, tripulante_id, funcao)
        VALUES (%s, %s, 'comandante')
        """,
        (mission["id"], refs["copiloto_id"]),
    )

    _savepoint_rejects(
        bootstrapped_db,
        """
        INSERT INTO financeiro_parametros (
            tipo,
            valor,
            unidade,
            vigencia_inicio,
            vigencia_fim
        )
        VALUES ('adicional_noturno', 1.0000, 'percentual', '2026-04-30', '2026-04-01')
        """,
        (),
    )

    bootstrapped_db.execute(
        """
        INSERT INTO financeiro_competencias (competencia)
        VALUES ('2026-04')
        """,
    )
    _savepoint_rejects(
        bootstrapped_db,
        """
        INSERT INTO financeiro_competencias (competencia)
        VALUES ('2026-04')
        """,
        (),
    )


def test_finance_bootstrap_accepts_calculation_memory_and_parameters_json(bootstrapped_db):
    refs = _seed_base_rows(bootstrapped_db)
    mission = _insert_missao_operacional(bootstrapped_db, refs)

    hourly = bootstrapped_db.execute(
        """
        INSERT INTO financeiro_calculos_horarios (
            missao_operacional_id,
            tripulante_id,
            funcao,
            memoria_calculo,
            parametros_usados
        )
        VALUES (%s, %s, 'comandante', %s::jsonb, %s::jsonb)
        RETURNING org_id, memoria_calculo, parametros_usados
        """,
        (
            mission["id"],
            refs["comandante_id"],
            '{"regra":"stub_bootstrap"}',
            '{"parametro":"stub_bootstrap"}',
        ),
    ).fetchone()
    productivity = bootstrapped_db.execute(
        """
        INSERT INTO financeiro_calculos_produtividade (
            competencia,
            tripulante_id,
            funcao,
            memoria_calculo,
            parametros_usados
        )
        VALUES ('2026-04', %s, 'comandante', %s::jsonb, %s::jsonb)
        RETURNING org_id, memoria_calculo, parametros_usados
        """,
        (
            refs["comandante_id"],
            '{"regra":"stub_bootstrap"}',
            '{"parametro":"stub_bootstrap"}',
        ),
    ).fetchone()

    assert hourly["org_id"] == "default_single_tenant"
    assert productivity["org_id"] == "default_single_tenant"
    assert hourly["memoria_calculo"]["regra"] == "stub_bootstrap"
    assert hourly["parametros_usados"]["parametro"] == "stub_bootstrap"
    assert productivity["memoria_calculo"]["regra"] == "stub_bootstrap"
    assert productivity["parametros_usados"]["parametro"] == "stub_bootstrap"
