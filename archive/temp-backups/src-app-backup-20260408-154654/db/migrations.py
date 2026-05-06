from __future__ import annotations

import re

from flask import current_app

from .schema import _REQUIRED_COLUMNS_BY_TABLE, SCHEMA, _expected_tables_from_schema
from .training_program_seed import seed_training_program_reference


def _schema_statements(*, kind: str) -> list[str]:
    if kind == "tables":
        pattern = r"(CREATE TABLE IF NOT EXISTS\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(.*?\);)"
    elif kind == "indexes":
        pattern = r"(CREATE(?: UNIQUE)? INDEX IF NOT EXISTS\s+[a-zA-Z_][a-zA-Z0-9_]*\s+ON\s+.*?;)"
    else:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported schema statement kind: {kind}")
    return [statement.strip() for statement in re.findall(pattern, SCHEMA, flags=re.DOTALL | re.IGNORECASE)]


def _execute_schema_statements(db, *, kind: str) -> None:
    for statement in _schema_statements(kind=kind):
        db.execute(statement)


def schema_consistency_report(db) -> dict:
    expected_tables = _expected_tables_from_schema()
    existing_rows = db.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        """
    ).fetchall()
    existing_tables = {row["table_name"] for row in existing_rows}
    missing_tables = sorted(set(expected_tables) - existing_tables)

    missing_columns: dict[str, list[str]] = {}
    for table_name, required_columns in _REQUIRED_COLUMNS_BY_TABLE.items():
        if table_name not in existing_tables:
            missing_columns[table_name] = list(required_columns)
            continue
        column_rows = db.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
        existing_columns = {row["column_name"] for row in column_rows}
        missing_for_table = [column for column in required_columns if column not in existing_columns]
        if missing_for_table:
            missing_columns[table_name] = missing_for_table

    return {
        "expected_tables_total": len(expected_tables),
        "existing_tables_total": len(existing_tables),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "is_consistent": not missing_tables and not missing_columns,
    }


def repair_and_validate_schema(db) -> dict:
    execute_migrations(db)
    report = schema_consistency_report(db)
    if not report["is_consistent"]:
        raise RuntimeError(
            "Banco inconsistente após migração automática. "
            f"Tabelas faltantes: {', '.join(report['missing_tables']) or 'nenhuma'}. "
            f"Colunas faltantes: {report['missing_columns'] or 'nenhuma'}."
        )
    return report
def execute_migrations(db):
    try:
        _execute_schema_statements(db, kind="tables")
        # Persist base schema early so later migration rollbacks do not drop newly created tables.
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not bootstrap base tables from schema script: {exc}")
        db.conn.rollback()

    # Keep user permission column migration isolated from other legacy migrations.
    try:
        db.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permissao_modulos_json TEXT NOT NULL DEFAULT '[]'")
        db.execute("UPDATE usuarios SET permissao_modulos_json = '[]' WHERE permissao_modulos_json IS NULL")
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate user permissions column: {e}")
        db.conn.rollback()

    try:
        db.execute("ALTER TABLE background_jobs ADD COLUMN IF NOT EXISTS origin_request_id TEXT")
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate background_jobs origin_request_id column: {e}")
        db.conn.rollback()

    # Bring older databases up to date with the current schema.
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS treinamento_anexos_pdf (
                id BIGSERIAL PRIMARY KEY,
                treinamento_id INTEGER NOT NULL REFERENCES treinamentos (id) ON DELETE CASCADE,
                nome_original TEXT NOT NULL,
                nome_interno TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT 'application/pdf',
                tamanho_bytes INTEGER NOT NULL,
                storage_ref TEXT NOT NULL DEFAULT 'db:bytea',
                arquivo_pdf BYTEA,
                arquivo_hash TEXT,
                status TEXT NOT NULL DEFAULT 'ativo',
                enviado_por INTEGER REFERENCES usuarios (id),
                enviado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_treinamento_anexos_treinamento
            ON treinamento_anexos_pdf (treinamento_id, enviado_em DESC)
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_treinamento_anexos_status
            ON treinamento_anexos_pdf (status)
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not migrate training attachments table: {exc}")
        db.conn.rollback()

    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS tripulante_arquivos_pdf (
                id BIGSERIAL PRIMARY KEY,
                tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
                tipo_documento TEXT NOT NULL DEFAULT 'geral',
                nome_original TEXT NOT NULL,
                nome_interno TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT 'application/pdf',
                tamanho_bytes INTEGER NOT NULL,
                storage_ref TEXT NOT NULL DEFAULT 'db:bytea',
                arquivo_pdf BYTEA,
                arquivo_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ativo',
                enviado_por INTEGER REFERENCES usuarios (id),
                enviado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                substitui_arquivo_id BIGINT REFERENCES tripulante_arquivos_pdf (id),
                removido_por INTEGER REFERENCES usuarios (id),
                removido_em TIMESTAMP,
                motivo_status TEXT
            )
            """
        )
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS tipo_documento TEXT NOT NULL DEFAULT 'geral'")
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ativo'")
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS arquivo_hash TEXT")
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS substitui_arquivo_id BIGINT REFERENCES tripulante_arquivos_pdf (id)")
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS removido_por INTEGER REFERENCES usuarios (id)")
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS removido_em TIMESTAMP")
        db.execute("ALTER TABLE tripulante_arquivos_pdf ADD COLUMN IF NOT EXISTS motivo_status TEXT")
        db.execute("UPDATE tripulante_arquivos_pdf SET tipo_documento = 'geral' WHERE tipo_documento IS NULL OR TRIM(tipo_documento) = ''")
        db.execute("UPDATE tripulante_arquivos_pdf SET status = 'ativo' WHERE status IS NULL OR TRIM(status) = ''")
        db.execute(
            """
            UPDATE tripulante_arquivos_pdf
            SET status = 'ativo'
            WHERE status NOT IN ('ativo', 'substituido', 'removido')
            """
        )
        db.execute(
            """
            UPDATE tripulante_arquivos_pdf
            SET arquivo_hash = md5(COALESCE(encode(arquivo_pdf, 'hex'), '') || ':' || COALESCE(nome_interno, '') || ':' || id::text)
            WHERE arquivo_hash IS NULL OR TRIM(arquivo_hash) = ''
            """
        )
        db.execute("ALTER TABLE tripulante_arquivos_pdf ALTER COLUMN arquivo_hash SET NOT NULL")
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'tripulante_arquivos_pdf_status_check'
                ) THEN
                    ALTER TABLE tripulante_arquivos_pdf
                    ADD CONSTRAINT tripulante_arquivos_pdf_status_check
                    CHECK (status IN ('ativo', 'substituido', 'removido'));
                END IF;
            END
            $$;
            """
        )
        db.execute(
            """
            WITH duplicados AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (PARTITION BY tripulante_id, arquivo_hash ORDER BY enviado_em DESC, id DESC) AS rn
                FROM tripulante_arquivos_pdf
                WHERE status = 'ativo'
                  AND arquivo_hash IS NOT NULL
                  AND TRIM(arquivo_hash) <> ''
            )
            UPDATE tripulante_arquivos_pdf t
            SET status = 'substituido',
                motivo_status = COALESCE(t.motivo_status, 'Marcado como substituído durante migração de deduplicação.')
            FROM duplicados d
            WHERE t.id = d.id
              AND d.rn > 1
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tripulante_arquivos_tripulante
            ON tripulante_arquivos_pdf (tripulante_id, enviado_em DESC)
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tripulante_arquivos_status
            ON tripulante_arquivos_pdf (status)
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tripulante_arquivos_hash_ativo
            ON tripulante_arquivos_pdf (tripulante_id, arquivo_hash)
            WHERE status = 'ativo'
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not migrate tripulante file attachments table: {exc}")
        db.conn.rollback()

    # Ensure deleting a training also cleans related notification rows.
    try:
        db.execute(
            """
            DELETE FROM notificacoes_treinamento nt
            WHERE NOT EXISTS (
                SELECT 1
                FROM treinamentos t
                WHERE t.id = nt.treinamento_id
            )
            """
        )
        db.execute(
            """
            DO $$
            DECLARE
                current_fk_name TEXT;
                current_del_type "char";
            BEGIN
                SELECT c.conname, c.confdeltype
                INTO current_fk_name, current_del_type
                FROM pg_constraint c
                JOIN pg_class tbl ON tbl.oid = c.conrelid
                JOIN pg_attribute attr ON attr.attrelid = tbl.oid AND attr.attnum = ANY(c.conkey)
                WHERE tbl.relname = 'notificacoes_treinamento'
                  AND c.contype = 'f'
                  AND attr.attname = 'treinamento_id'
                LIMIT 1;

                IF current_fk_name IS NULL THEN
                    ALTER TABLE notificacoes_treinamento
                    ADD CONSTRAINT notificacoes_treinamento_treinamento_id_fkey
                    FOREIGN KEY (treinamento_id) REFERENCES treinamentos (id) ON DELETE CASCADE;
                ELSIF current_del_type <> 'c' THEN
                    EXECUTE format('ALTER TABLE notificacoes_treinamento DROP CONSTRAINT %I', current_fk_name);
                    ALTER TABLE notificacoes_treinamento
                    ADD CONSTRAINT notificacoes_treinamento_treinamento_id_fkey
                    FOREIGN KEY (treinamento_id) REFERENCES treinamentos (id) ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not migrate notificacoes_treinamento FK to CASCADE: {exc}")
        db.conn.rollback()

    try:
        db.execute("ALTER TABLE pilotos ADD COLUMN IF NOT EXISTS tripulante_id INTEGER UNIQUE REFERENCES tripulantes (id)")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS foto_base64 TEXT")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS foto_storage_ref TEXT")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS foto_mime_type TEXT")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS possui_foto BOOLEAN NOT NULL DEFAULT FALSE")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS email TEXT")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS telefone TEXT")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS ativo INTEGER NOT NULL DEFAULT 1")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS funcao_operacional TEXT NOT NULL DEFAULT 'outro'")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS categoria_operacional TEXT NOT NULL DEFAULT 'N/A'")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS sdea_ativo INTEGER NOT NULL DEFAULT 0")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS instrutor_ativo INTEGER NOT NULL DEFAULT 0")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS checador_ativo INTEGER NOT NULL DEFAULT 0")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS elegivel_adicional_excepcional INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE INDEX IF NOT EXISTS idx_tripulantes_categoria ON tripulantes (categoria_operacional)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_tripulantes_funcao ON tripulantes (funcao_operacional)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_tripulantes_ativo ON tripulantes (ativo)")
        db.execute("ALTER TABLE equipamentos ADD COLUMN IF NOT EXISTS ativo INTEGER NOT NULL DEFAULT 1")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS ativo INTEGER NOT NULL DEFAULT 1")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS codigo TEXT")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS descricao TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS exige_equipamento INTEGER NOT NULL DEFAULT 1")
        db.execute("ALTER TABLE notificacoes_email ADD COLUMN IF NOT EXISTS ativo INTEGER NOT NULL DEFAULT 1")
        db.execute("UPDATE equipamentos SET ativo = 1 WHERE ativo IS NULL")
        db.execute("UPDATE tipos_treinamento SET ativo = 1 WHERE ativo IS NULL")
        db.execute("UPDATE tipos_treinamento SET descricao = '' WHERE descricao IS NULL")
        db.execute("UPDATE tipos_treinamento SET exige_equipamento = 1 WHERE exige_equipamento IS NULL")
        db.execute("UPDATE notificacoes_email SET ativo = 1 WHERE ativo IS NULL")
        db.execute("UPDATE tripulantes SET ativo = 1 WHERE ativo IS NULL")
        db.execute("UPDATE tripulantes SET funcao_operacional = 'outro' WHERE funcao_operacional IS NULL OR TRIM(funcao_operacional) = ''")
        db.execute("UPDATE tripulantes SET categoria_operacional = 'N/A' WHERE categoria_operacional IS NULL OR TRIM(categoria_operacional) = ''")
        db.execute(
            """
            UPDATE tripulantes
            SET funcao_operacional = 'outro'
            WHERE funcao_operacional NOT IN ('comandante', 'copiloto', 'outro')
            """
        )
        db.execute(
            """
            UPDATE tripulantes
            SET categoria_operacional = 'N/A'
            WHERE categoria_operacional NOT IN ('A', 'B', 'N/A')
            """
        )
        db.execute("UPDATE tripulantes SET sdea_ativo = 0 WHERE sdea_ativo IS NULL")
        db.execute("UPDATE tripulantes SET instrutor_ativo = 0 WHERE instrutor_ativo IS NULL")
        db.execute("UPDATE tripulantes SET checador_ativo = 0 WHERE checador_ativo IS NULL")
        db.execute("UPDATE tripulantes SET elegivel_adicional_excepcional = 0 WHERE elegivel_adicional_excepcional IS NULL")
        db.execute(
            """
            UPDATE tripulantes
            SET possui_foto = COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            )
            WHERE possui_foto IS DISTINCT FROM COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            )
            """
        )
        db.execute("ALTER TABLE tripulante_arquivos_pdf ALTER COLUMN arquivo_pdf DROP NOT NULL")
        db.execute("ALTER TABLE treinamento_anexos_pdf ALTER COLUMN arquivo_pdf DROP NOT NULL")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS segmentos_teoricos (
                id BIGSERIAL PRIMARY KEY,
                tipo_treinamento_id INTEGER NOT NULL REFERENCES tipos_treinamento (id) ON DELETE CASCADE,
                referencia_original_id INTEGER,
                modelo_segmento TEXT NOT NULL,
                nome_segmento TEXT NOT NULL,
                carga_horaria NUMERIC(10,2) NOT NULL DEFAULT 0,
                carga_teorica NUMERIC(10,2) NOT NULL DEFAULT 0,
                carga_pratica NUMERIC(10,2) NOT NULL DEFAULT 0,
                periodicidade_meses INTEGER NOT NULL DEFAULT 0,
                observacao TEXT,
                ativo INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS horas_voo_aeronave (
                id BIGSERIAL PRIMARY KEY,
                tipo_treinamento_id INTEGER NOT NULL REFERENCES tipos_treinamento (id) ON DELETE CASCADE,
                referencia_original_id INTEGER,
                aeronave_modelo TEXT NOT NULL,
                solo_horas NUMERIC(10,2) NOT NULL DEFAULT 0,
                voo_pic_sic_horas NUMERIC(10,2) NOT NULL DEFAULT 0,
                voo_crew_horas NUMERIC(10,2) NOT NULL DEFAULT 0,
                observacao TEXT,
                ativo INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        db.execute("ALTER TABLE treinamentos ADD COLUMN IF NOT EXISTS segmento_teorico_id BIGINT REFERENCES segmentos_teoricos (id)")
        db.execute("ALTER TABLE treinamentos ADD COLUMN IF NOT EXISTS aeronave_modelo TEXT")
        db.execute("ALTER TABLE treinamentos ADD COLUMN IF NOT EXISTS ctac_solo_horas NUMERIC(10,2)")
        db.execute("ALTER TABLE treinamentos ADD COLUMN IF NOT EXISTS ctac_voo_pic_sic_horas NUMERIC(10,2)")
        db.execute("ALTER TABLE treinamentos ADD COLUMN IF NOT EXISTS ctac_voo_crew_horas NUMERIC(10,2)")
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tipos_treinamento_codigo
            ON tipos_treinamento (codigo)
            WHERE codigo IS NOT NULL
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_segmentos_teoricos_tipo_nome
            ON segmentos_teoricos (tipo_treinamento_id, modelo_segmento, nome_segmento)
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_segmentos_teoricos_ref
            ON segmentos_teoricos (referencia_original_id)
            WHERE referencia_original_id IS NOT NULL
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_horas_voo_aeronave_tipo_modelo
            ON horas_voo_aeronave (tipo_treinamento_id, aeronave_modelo)
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_horas_voo_aeronave_ref
            ON horas_voo_aeronave (referencia_original_id)
            WHERE referencia_original_id IS NOT NULL
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_treinamentos_segmento_teorico_id ON treinamentos (segmento_teorico_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_treinamentos_aeronave_modelo ON treinamentos (aeronave_modelo)")
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'tripulantes_funcao_operacional_check'
                ) THEN
                    ALTER TABLE tripulantes
                    ADD CONSTRAINT tripulantes_funcao_operacional_check
                    CHECK (funcao_operacional IN ('comandante', 'copiloto', 'outro'));
                END IF;
            END $$;
            """
        )
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'tripulantes_categoria_operacional_check'
                ) THEN
                    ALTER TABLE tripulantes
                    ADD CONSTRAINT tripulantes_categoria_operacional_check
                    CHECK (categoria_operacional IN ('A', 'B', 'N/A'));
                END IF;
            END $$;
            """
        )
        db.execute(
            """
            WITH unique_tripulantes AS (
                SELECT LOWER(TRIM(nome)) AS nome_normalizado, MIN(id) AS id
                FROM tripulantes
                GROUP BY LOWER(TRIM(nome))
                HAVING COUNT(*) = 1
            )
            UPDATE pilotos p
            SET tripulante_id = ut.id
            FROM unique_tripulantes ut
            WHERE p.tripulante_id IS NULL
              AND LOWER(TRIM(p.nome)) = ut.nome_normalizado
            """
        )
        seed_training_program_reference(db)
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate active flags: {e}")
        db.conn.rollback()

    # Auto-migrate text date columns gracefully
    try:
        col_type = db.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'treinamentos' AND column_name = 'data_vencimento'").fetchone()
        if col_type and col_type["data_type"] == "text":
            db.execute('''
                ALTER TABLE treinamentos
                ALTER COLUMN data_realizacao TYPE DATE USING NULLIF(data_realizacao, '')::date,
                ALTER COLUMN data_vencimento TYPE DATE USING NULLIF(data_vencimento, '')::date;
            ''')
            current_app.logger.info("Migrated treinamentos date columns to DATE type.")
    except Exception as e:
        current_app.logger.warning(f"Could not migrate schema: {e}")
        db.conn.rollback()

    # Keep only one active adicional excepcional per tripulante/competencia.
    try:
        db.execute(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY tripulante_id, competencia
                        ORDER BY id DESC
                    ) AS rn
                FROM produtividade_adicionais_excepcionais
                WHERE ativo = TRUE
            )
            UPDATE produtividade_adicionais_excepcionais pe
            SET ativo = FALSE
            FROM ranked
            WHERE pe.id = ranked.id
              AND ranked.rn > 1
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_excepcionais_tripulante_competencia_ativo
            ON produtividade_adicionais_excepcionais (tripulante_id, competencia)
            WHERE ativo = TRUE
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not enforce adicionais excepcionais uniqueness: {exc}")
        db.conn.rollback()

    # Performance hardening: índices para filtros/listagens e consultas de apoio operacional.
    try:
        db.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tripulantes_nome_trgm
            ON tripulantes
            USING gin (LOWER(nome) gin_trgm_ops)
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tripulantes_cpf_digits
            ON tripulantes ((regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g')))
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_treinamentos_tripulante_vencimento
            ON treinamentos (tripulante_id, data_vencimento)
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_treinamentos_vencimento
            ON treinamentos (data_vencimento)
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pilotos_status_base
            ON pilotos (status, base_id)
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_historico_status_piloto_recent
            ON historico_status_piloto (piloto_id, alterado_em DESC, id DESC)
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not apply performance indexes migration: {exc}")
        db.conn.rollback()

    try:
        _execute_schema_statements(db, kind="indexes")
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not apply schema indexes bootstrap: {exc}")
        db.conn.rollback()
