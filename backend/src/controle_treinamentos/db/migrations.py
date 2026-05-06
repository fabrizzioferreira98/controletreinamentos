"""Migracoes corretivas legadas.

Bootstrap estrutural canonico fica em `schema_bootstrap.py`.
Este modulo permanece como trilha manual/corretiva para bancos historicos.
Nao deve receber seed, import, sync operacional ou bootstrap estrutural novo.
"""

from __future__ import annotations

from flask import current_app

from .schema_bootstrap import (
    _execute_schema_statements as _execute_schema_statements_impl,
)
from .schema_bootstrap import (
    _schema_statements as _schema_statements_impl,
)
from .schema_bootstrap import (
    repair_and_validate_schema as repair_and_validate_schema_impl,
)
from .schema_bootstrap import (
    schema_consistency_report as schema_consistency_report_impl,
)

MIGRATIONS_MODULE_CLASSIFICATION = "migracao_corretiva_legada_manual"
CORRECTIVE_MIGRATION_ENTRYPOINT = "execute_corrective_migrations"
COMPAT_MIGRATION_ENTRYPOINT = "execute_migrations"


def _schema_statements(*, kind: str) -> list[str]:
    return _schema_statements_impl(kind=kind)


def _execute_schema_statements(db, *, kind: str) -> None:
    _execute_schema_statements_impl(db, kind=kind)


def schema_consistency_report(db) -> dict:
    return schema_consistency_report_impl(db)


def repair_and_validate_schema(db) -> dict:
    return repair_and_validate_schema_impl(db)


def execute_migrations(db):
    """Nome historico preservado; novas chamadas devem usar execute_corrective_migrations."""

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

    try:
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS sdea_icao_validade DATE")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS instrutor_inicio DATE")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS instrutor_fim DATE")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS checador_inicio DATE")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS checador_fim DATE")
        db.execute("ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS checador_carta_designacao TEXT")
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'tripulantes_instrutor_periodo_valido'
                ) THEN
                    ALTER TABLE tripulantes
                    ADD CONSTRAINT tripulantes_instrutor_periodo_valido
                    CHECK (instrutor_inicio IS NULL OR instrutor_fim IS NULL OR instrutor_fim >= instrutor_inicio);
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'tripulantes_checador_periodo_valido'
                ) THEN
                    ALTER TABLE tripulantes
                    ADD CONSTRAINT tripulantes_checador_periodo_valido
                    CHECK (checador_inicio IS NULL OR checador_fim IS NULL OR checador_fim >= checador_inicio);
                END IF;
            END
            $$;
            """
        )
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate tripulantes financial governance columns: {e}")
        db.conn.rollback()

    try:
        db.execute("ALTER TABLE financeiro_missoes_operacionais ADD COLUMN IF NOT EXISTS data_final DATE")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ADD COLUMN IF NOT EXISTS pos_exec_min INTEGER NOT NULL DEFAULT 0")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ADD COLUMN IF NOT EXISTS justificativa TEXT")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ALTER COLUMN horario_apresentacao DROP NOT NULL")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ALTER COLUMN horario_abandono DROP NOT NULL")
        db.execute(
            """
            UPDATE financeiro_missoes_operacionais
            SET data_final = data_missao
            WHERE data_final IS NULL
            """
        )
        db.execute(
            """
            UPDATE financeiro_missoes_operacionais
            SET pos_exec_min = 0
            WHERE pos_exec_min IS NULL OR pos_exec_min < 0
            """
        )
        db.execute("ALTER TABLE financeiro_missoes_operacionais ALTER COLUMN pos_exec_min SET DEFAULT 0")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ALTER COLUMN pos_exec_min SET NOT NULL")
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'financeiro_missoes_operacionais_periodo_valido'
                ) THEN
                    ALTER TABLE financeiro_missoes_operacionais
                    ADD CONSTRAINT financeiro_missoes_operacionais_periodo_valido
                    CHECK (data_final IS NULL OR data_final >= data_missao);
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'financeiro_missoes_operacionais_pos_exec_min_check'
                ) THEN
                    ALTER TABLE financeiro_missoes_operacionais
                    ADD CONSTRAINT financeiro_missoes_operacionais_pos_exec_min_check
                    CHECK (pos_exec_min >= 0);
                END IF;
                ALTER TABLE financeiro_missoes_operacionais
                DROP CONSTRAINT IF EXISTS financeiro_missoes_operacionais_horarios_validos;
                ALTER TABLE financeiro_missoes_operacionais
                ADD CONSTRAINT financeiro_missoes_operacionais_horarios_validos
                CHECK (
                    horario_apresentacao IS NULL
                    OR horario_abandono IS NULL
                    OR horario_abandono > horario_apresentacao
                );
            END
            $$;
            """
        )
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate financeiro_missoes_operacionais jornada gap columns: {e}")
        db.conn.rollback()

    try:
        db.execute(
            """
            ALTER TABLE financeiro_calculos_produtividade
            ADD COLUMN IF NOT EXISTS valor_pernoite_comum NUMERIC(14,2) NOT NULL DEFAULT 0
            """
        )
        db.execute(
            """
            UPDATE financeiro_calculos_produtividade
            SET valor_pernoite_comum = 0
            WHERE valor_pernoite_comum IS NULL
            """
        )
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate financeiro_calculos_produtividade valor_pernoite_comum column: {e}")
        db.conn.rollback()

    try:
        db.execute(
            """
            ALTER TABLE financeiro_calculos_horarios
            ADD COLUMN IF NOT EXISTS minutos_noturnos_reais INTEGER NOT NULL DEFAULT 0
            """
        )
        db.execute(
            """
            ALTER TABLE financeiro_calculos_horarios
            ADD COLUMN IF NOT EXISTS calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            """
        )
        db.execute(
            """
            ALTER TABLE financeiro_calculos_horarios
            ALTER COLUMN horas_noturnas_convertidas TYPE NUMERIC(10,4)
            USING horas_noturnas_convertidas::NUMERIC(10,4)
            """
        )
        db.execute(
            """
            UPDATE financeiro_calculos_horarios
            SET minutos_noturnos_reais = COALESCE(minutos_noturnos_reais, minutos_noturnos, 0)
            WHERE minutos_noturnos_reais IS NULL
               OR minutos_noturnos_reais = 0
            """
        )
        db.execute(
            """
            UPDATE financeiro_calculos_horarios
            SET calculated_at = COALESCE(calculated_at, updated_at, created_at, CURRENT_TIMESTAMP)
            WHERE calculated_at IS NULL
            """
        )
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'financeiro_calculos_horarios_minutos_noturnos_reais_check'
                ) THEN
                    ALTER TABLE financeiro_calculos_horarios
                    ADD CONSTRAINT financeiro_calculos_horarios_minutos_noturnos_reais_check
                    CHECK (minutos_noturnos_reais >= 0);
                END IF;
            END
            $$;
            """
        )
        db.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not migrate financeiro_calculos_horarios minutos_noturnos_reais column: {e}")
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
                enviado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                removido_por INTEGER REFERENCES usuarios (id),
                removido_em TIMESTAMP,
                motivo_status TEXT
            )
            """
        )
        db.execute("ALTER TABLE treinamento_anexos_pdf ADD COLUMN IF NOT EXISTS removido_por INTEGER REFERENCES usuarios (id)")
        db.execute("ALTER TABLE treinamento_anexos_pdf ADD COLUMN IF NOT EXISTS removido_em TIMESTAMP")
        db.execute("ALTER TABLE treinamento_anexos_pdf ADD COLUMN IF NOT EXISTS motivo_status TEXT")
        db.execute("UPDATE treinamento_anexos_pdf SET status = 'ativo' WHERE status IS NULL OR TRIM(status) = ''")
        db.execute(
            """
            UPDATE treinamento_anexos_pdf
            SET status = 'ativo'
            WHERE status NOT IN ('ativo', 'removido')
            """
        )
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'treinamento_anexos_pdf_status_check'
                ) THEN
                    ALTER TABLE treinamento_anexos_pdf
                    ADD CONSTRAINT treinamento_anexos_pdf_status_check
                    CHECK (status IN ('ativo', 'removido'));
                END IF;
            END
            $$;
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

    # Financeiro: garantir apenas um calculo horario vigente por missao/tripulante/funcao.
    try:
        db.execute("ALTER TABLE financeiro_missoes_operacionais ADD COLUMN IF NOT EXISTS deleted_by INTEGER REFERENCES usuarios (id)")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")
        db.execute("ALTER TABLE financeiro_missoes_operacionais ADD COLUMN IF NOT EXISTS delete_reason TEXT")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_active_org_competencia
            ON financeiro_missoes_operacionais (org_id, competencia, data_missao)
            WHERE deleted_at IS NULL
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_deleted
            ON financeiro_missoes_operacionais (org_id, deleted_at)
            WHERE deleted_at IS NOT NULL
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not migrate finance mission soft delete columns: {exc}")
        db.conn.rollback()

    # Financeiro: garantir apenas um calculo horario vigente por missao/tripulante/funcao.
    try:
        db.execute(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY org_id, missao_operacional_id, tripulante_id, funcao
                        ORDER BY updated_at DESC, created_at DESC, id DESC
                    ) AS rn
                FROM financeiro_calculos_horarios
                WHERE status <> 'obsoleto'
            )
            UPDATE financeiro_calculos_horarios ch
            SET status = 'obsoleto',
                updated_at = CURRENT_TIMESTAMP
            FROM ranked r
            WHERE ch.id = r.id
              AND r.rn > 1
            """
        )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_financeiro_calculos_horarios_current
            ON financeiro_calculos_horarios (org_id, missao_operacional_id, tripulante_id, funcao)
            WHERE status <> 'obsoleto'
            """
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Could not migrate finance hourly calculation idempotency index: {exc}")
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
        db.execute("ALTER TABLE equipamentos ADD COLUMN IF NOT EXISTS categoria_financeira TEXT")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS ativo INTEGER NOT NULL DEFAULT 1")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS codigo TEXT")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS descricao TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS modalidade TEXT NOT NULL DEFAULT 'segmentado'")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS periodicidade_meses_tipo INTEGER")
        db.execute("ALTER TABLE tipos_treinamento ADD COLUMN IF NOT EXISTS exige_equipamento INTEGER NOT NULL DEFAULT 1")
        db.execute("ALTER TABLE notificacoes_email ADD COLUMN IF NOT EXISTS ativo INTEGER NOT NULL DEFAULT 1")
        db.execute("UPDATE equipamentos SET ativo = 1 WHERE ativo IS NULL")
        db.execute(
            """
            UPDATE equipamentos
            SET categoria_financeira = NULL
            WHERE categoria_financeira IS NOT NULL AND TRIM(categoria_financeira) = ''
            """
        )
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'equipamentos_categoria_financeira_check'
                ) THEN
                    ALTER TABLE equipamentos
                    ADD CONSTRAINT equipamentos_categoria_financeira_check
                    CHECK (
                        categoria_financeira IS NULL
                        OR categoria_financeira IN ('a', 'b', 'turbohelice_palmas', 'nao_aplicavel')
                    );
                END IF;
            END $$;
            """
        )
        db.execute("UPDATE tipos_treinamento SET ativo = 1 WHERE ativo IS NULL")
        db.execute("UPDATE tipos_treinamento SET descricao = '' WHERE descricao IS NULL")
        db.execute("UPDATE tipos_treinamento SET modalidade = 'segmentado' WHERE modalidade IS NULL OR TRIM(modalidade) = ''")
        db.execute("UPDATE tipos_treinamento SET periodicidade_meses_tipo = NULL WHERE modalidade <> 'direto'")
        db.execute("UPDATE tipos_treinamento SET periodicidade_meses_tipo = COALESCE(periodicidade_meses_tipo, periodicidade_meses, 12) WHERE modalidade = 'direto'")
        db.execute("UPDATE tipos_treinamento SET periodicidade_meses = COALESCE(periodicidade_meses_tipo, periodicidade_meses, 0) WHERE modalidade = 'direto'")
        db.execute("UPDATE tipos_treinamento SET exige_equipamento = 1 WHERE exige_equipamento IS NULL")
        db.execute("UPDATE notificacoes_email SET ativo = 1 WHERE ativo IS NULL")
        db.execute(
            """
            UPDATE tipos_treinamento
            SET modalidade = 'segmentado'
            WHERE modalidade NOT IN ('segmentado', 'direto')
            """
        )
        db.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'tipos_treinamento_modalidade_check'
                ) THEN
                    ALTER TABLE tipos_treinamento
                    ADD CONSTRAINT tipos_treinamento_modalidade_check
                    CHECK (modalidade IN ('segmentado', 'direto'));
                END IF;
            END $$;
            """
        )
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
                    WHERE conname = 'treinamentos_structure_no_program_fields_without_segment'
                ) THEN
                    ALTER TABLE treinamentos
                    ADD CONSTRAINT treinamentos_structure_no_program_fields_without_segment
                    CHECK (
                        segmento_teorico_id IS NOT NULL
                        OR (
                            NULLIF(TRIM(COALESCE(aeronave_modelo, '')), '') IS NULL
                            AND ctac_solo_horas IS NULL
                            AND ctac_voo_pic_sic_horas IS NULL
                            AND ctac_voo_crew_horas IS NULL
                        )
                    ) NOT VALID;
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
                    WHERE conname = 'treinamentos_structure_program_forbids_equipment'
                ) THEN
                    ALTER TABLE treinamentos
                    ADD CONSTRAINT treinamentos_structure_program_forbids_equipment
                    CHECK (
                        segmento_teorico_id IS NULL OR equipamento_id IS NULL
                    ) NOT VALID;
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


def execute_corrective_migrations(db):
    """Nome canonico para as corretivas legadas chamadas por repair manual."""

    execute_migrations(db)
