from __future__ import annotations

import re

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('operador', 'gestora')),
    ativo INTEGER NOT NULL DEFAULT 1,
    permissao_modulos_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS tripulantes (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    cpf TEXT NOT NULL UNIQUE,
    licenca_anac TEXT NOT NULL,
    email TEXT,
    telefone TEXT,
    base TEXT NOT NULL,
    status TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    funcao_operacional TEXT NOT NULL DEFAULT 'outro',
    categoria_operacional TEXT NOT NULL DEFAULT 'N/A',
    sdea_ativo INTEGER NOT NULL DEFAULT 0,
    instrutor_ativo INTEGER NOT NULL DEFAULT 0,
    checador_ativo INTEGER NOT NULL DEFAULT 0,
    elegivel_adicional_excepcional INTEGER NOT NULL DEFAULT 0,
    observacoes TEXT,
    foto_base64 TEXT,
    foto_storage_ref TEXT,
    foto_mime_type TEXT,
    possui_foto BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS equipamentos (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tipos_treinamento (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    codigo TEXT,
    descricao TEXT NOT NULL DEFAULT '',
    periodicidade_meses INTEGER NOT NULL,
    modalidade TEXT NOT NULL DEFAULT 'segmentado',
    periodicidade_meses_tipo INTEGER,
    exige_equipamento INTEGER NOT NULL DEFAULT 1,
    ativo INTEGER NOT NULL DEFAULT 1
);

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
);

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
);

CREATE TABLE IF NOT EXISTS treinamentos (
    id SERIAL PRIMARY KEY,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id),
    equipamento_id INTEGER REFERENCES equipamentos (id),
    tipo_treinamento_id INTEGER NOT NULL REFERENCES tipos_treinamento (id),
    segmento_teorico_id BIGINT REFERENCES segmentos_teoricos (id),
    aeronave_modelo TEXT,
    ctac_solo_horas NUMERIC(10,2),
    ctac_voo_pic_sic_horas NUMERIC(10,2),
    ctac_voo_crew_horas NUMERIC(10,2),
    data_realizacao DATE,
    data_vencimento DATE,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS notificacoes_email (
    id SERIAL PRIMARY KEY,
    email_destinatario TEXT NOT NULL UNIQUE,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bases (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE,
    uf TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    ativa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS pilotos (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    matricula TEXT NOT NULL UNIQUE,
    tripulante_id INTEGER UNIQUE REFERENCES tripulantes (id),
    base_id INTEGER NOT NULL REFERENCES bases (id),
    status TEXT NOT NULL CHECK (status IN ('ativo', 'folga', 'ferias', 'atestado', 'afastado', 'treinamento')),
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_status_piloto (
    id SERIAL PRIMARY KEY,
    piloto_id INTEGER NOT NULL REFERENCES pilotos (id),
    status_anterior TEXT,
    status_novo TEXT,
    base_anterior_id INTEGER REFERENCES bases (id),
    base_nova_id INTEGER REFERENCES bases (id),
    alterado_por INTEGER NOT NULL REFERENCES usuarios (id),
    alterado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS auditoria_eventos (
    id BIGSERIAL PRIMARY KEY,
    entidade TEXT NOT NULL,
    entidade_id BIGINT NOT NULL,
    acao TEXT NOT NULL,
    payload_anterior JSONB,
    payload_novo JSONB,
    realizado_por INTEGER NOT NULL REFERENCES usuarios (id),
    realizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS sistema_controle (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS notificacoes_treinamento (
    id BIGSERIAL PRIMARY KEY,
    treinamento_id INTEGER NOT NULL REFERENCES treinamentos (id) ON DELETE CASCADE,
    gatilho TEXT NOT NULL CHECK (gatilho IN ('30', '60', '90', 'vencido')),
    enviado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (treinamento_id, gatilho)
);

CREATE TABLE IF NOT EXISTS produtividade_regras (
    id SERIAL PRIMARY KEY,
    categoria_operacional TEXT NOT NULL,
    funcao_operacional TEXT NOT NULL,
    piso_minimo_mensal NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_missao NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_pernoite_cobertura NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_idioma_mensal NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_instrutor_mensal NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_checador_mensal NUMERIC(12,2) NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (categoria_operacional, funcao_operacional)
);

CREATE TABLE IF NOT EXISTS produtividade_parametros (
    chave TEXT PRIMARY KEY,
    valor_numerico NUMERIC(12,2),
    valor_texto TEXT,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS missoes_operacionais (
    id SERIAL PRIMARY KEY,
    codigo_voo TEXT NOT NULL,
    contratante TEXT NOT NULL,
    data_inicio DATE NOT NULL,
    data_fim DATE,
    origem TEXT,
    destino TEXT,
    tipo_operacao TEXT,
    conta_missao_produtividade BOOLEAN NOT NULL DEFAULT TRUE,
    observacoes TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS missao_tripulantes (
    id SERIAL PRIMARY KEY,
    missao_id INTEGER NOT NULL REFERENCES missoes_operacionais (id) ON DELETE CASCADE,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    UNIQUE (missao_id, tripulante_id)
);

CREATE TABLE IF NOT EXISTS pernoites_operacionais (
    id SERIAL PRIMARY KEY,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    missao_id INTEGER REFERENCES missoes_operacionais (id) ON DELETE SET NULL,
    data_pernoite DATE NOT NULL,
    tipo_pernoite TEXT NOT NULL CHECK (tipo_pernoite IN ('cobertura_base', 'operacional_comum')),
    quantidade INTEGER NOT NULL DEFAULT 1,
    observacoes TEXT
);

CREATE TABLE IF NOT EXISTS produtividade_adicionais_excepcionais (
    id SERIAL PRIMARY KEY,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    competencia TEXT NOT NULL,
    valor NUMERIC(12,2) NOT NULL DEFAULT 0,
    observacao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS produtividade_conferencias (
    id BIGSERIAL PRIMARY KEY,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    competencia TEXT NOT NULL,
    conferido_por INTEGER NOT NULL REFERENCES usuarios (id),
    conferido_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tripulante_id, competencia)
);

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
);

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
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'substituido', 'removido')),
    enviado_por INTEGER REFERENCES usuarios (id),
    enviado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    substitui_arquivo_id BIGINT REFERENCES tripulante_arquivos_pdf (id),
    removido_por INTEGER REFERENCES usuarios (id),
    removido_em TIMESTAMP,
    motivo_status TEXT
);

CREATE TABLE IF NOT EXISTS backups_execucoes (
    id BIGSERIAL PRIMARY KEY,
    tipo TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('sucesso', 'falha')),
    arquivo_principal TEXT,
    artefatos JSONB,
    tamanho_bytes BIGINT,
    duracao_ms INTEGER,
    mensagem TEXT,
    executado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS background_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'canceled')),
    priority INTEGER NOT NULL DEFAULT 100,
    scheduled_for TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    idempotency_key TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    locked_by TEXT,
    locked_at TIMESTAMP,
    last_error TEXT,
    requested_by INTEGER REFERENCES usuarios (id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    origin_request_id TEXT
);

CREATE TABLE IF NOT EXISTS background_job_executions (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES background_jobs (id) ON DELETE CASCADE,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    worker_id TEXT,
    error TEXT,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    duration_ms INTEGER,
    result_payload JSONB
);

CREATE TABLE IF NOT EXISTS request_error_events (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    status INTEGER NOT NULL,
    code TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT,
    path TEXT,
    endpoint TEXT,
    method TEXT,
    user_id INTEGER,
    context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tripulantes_nome ON tripulantes (nome);
CREATE INDEX IF NOT EXISTS idx_tripulantes_base ON tripulantes (base);
CREATE INDEX IF NOT EXISTS idx_tripulantes_status ON tripulantes (status);
CREATE INDEX IF NOT EXISTS idx_tripulantes_ativo_nome ON tripulantes (ativo, nome);
CREATE INDEX IF NOT EXISTS idx_tripulantes_base_status_nome ON tripulantes (base, status, nome);
CREATE INDEX IF NOT EXISTS idx_equipamentos_nome_ativo ON equipamentos (ativo, nome);
CREATE INDEX IF NOT EXISTS idx_tipos_treinamento_nome_ativo ON tipos_treinamento (ativo, nome);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tipos_treinamento_codigo ON tipos_treinamento (codigo) WHERE codigo IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_segmentos_teoricos_tipo_nome ON segmentos_teoricos (tipo_treinamento_id, modelo_segmento, nome_segmento);
CREATE UNIQUE INDEX IF NOT EXISTS uq_segmentos_teoricos_ref ON segmentos_teoricos (referencia_original_id) WHERE referencia_original_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_horas_voo_aeronave_tipo_modelo ON horas_voo_aeronave (tipo_treinamento_id, aeronave_modelo);
CREATE UNIQUE INDEX IF NOT EXISTS uq_horas_voo_aeronave_ref ON horas_voo_aeronave (referencia_original_id) WHERE referencia_original_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_treinamentos_tripulante_id ON treinamentos (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_treinamentos_equipamento_id ON treinamentos (equipamento_id);
CREATE INDEX IF NOT EXISTS idx_treinamentos_tipo_treinamento_id ON treinamentos (tipo_treinamento_id);
CREATE INDEX IF NOT EXISTS idx_treinamentos_segmento_teorico_id ON treinamentos (segmento_teorico_id);
CREATE INDEX IF NOT EXISTS idx_treinamentos_aeronave_modelo ON treinamentos (aeronave_modelo);
CREATE INDEX IF NOT EXISTS idx_treinamentos_data_vencimento ON treinamentos (data_vencimento);
CREATE INDEX IF NOT EXISTS idx_treinamentos_tripulante_data_vencimento ON treinamentos (tripulante_id, data_vencimento);
CREATE INDEX IF NOT EXISTS idx_treinamentos_tipo_data_vencimento ON treinamentos (tipo_treinamento_id, data_vencimento);
CREATE INDEX IF NOT EXISTS idx_notificacoes_email_ativo ON notificacoes_email (ativo);
CREATE INDEX IF NOT EXISTS idx_pilotos_base_id ON pilotos (base_id);
CREATE INDEX IF NOT EXISTS idx_pilotos_status ON pilotos (status);
CREATE INDEX IF NOT EXISTS idx_pilotos_base_status_nome ON pilotos (base_id, status, nome);
CREATE INDEX IF NOT EXISTS idx_historico_status_piloto_piloto_id ON historico_status_piloto (piloto_id);
CREATE INDEX IF NOT EXISTS idx_historico_status_piloto_alterado_em ON historico_status_piloto (alterado_em DESC);
CREATE INDEX IF NOT EXISTS idx_historico_status_piloto_base_anterior_id ON historico_status_piloto (base_anterior_id);
CREATE INDEX IF NOT EXISTS idx_historico_status_piloto_base_nova_id ON historico_status_piloto (base_nova_id);
CREATE INDEX IF NOT EXISTS idx_historico_status_piloto_alterado_por ON historico_status_piloto (alterado_por);
CREATE INDEX IF NOT EXISTS idx_pilotos_tripulante_id ON pilotos (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_entidade ON auditoria_eventos (entidade, entidade_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_realizado_em ON auditoria_eventos (realizado_em DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_acao ON auditoria_eventos (acao);
CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_realizado_por ON auditoria_eventos (realizado_por);
CREATE INDEX IF NOT EXISTS idx_notificacoes_treinamento_treinamento_id ON notificacoes_treinamento (treinamento_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_treinamento_enviado_em ON notificacoes_treinamento (enviado_em DESC);
CREATE INDEX IF NOT EXISTS idx_notificacoes_treinamento_treinamento_gatilho_data
ON notificacoes_treinamento (treinamento_id, gatilho, (CAST(enviado_em AS DATE)));
CREATE INDEX IF NOT EXISTS idx_missoes_data_inicio ON missoes_operacionais (data_inicio);
CREATE INDEX IF NOT EXISTS idx_missoes_data_inicio_id_desc ON missoes_operacionais (data_inicio DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_missoes_conta_prod ON missoes_operacionais (conta_missao_produtividade);
CREATE INDEX IF NOT EXISTS idx_missoes_codigo_voo_lower ON missoes_operacionais (LOWER(codigo_voo));
CREATE INDEX IF NOT EXISTS idx_missoes_tipo_operacao_lower ON missoes_operacionais (LOWER(tipo_operacao));
CREATE INDEX IF NOT EXISTS idx_missoes_contratante_lower ON missoes_operacionais (LOWER(contratante));
CREATE INDEX IF NOT EXISTS idx_missao_tripulantes_tripulante ON missao_tripulantes (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_pernoites_data_tipo ON pernoites_operacionais (data_pernoite, tipo_pernoite);
CREATE INDEX IF NOT EXISTS idx_pernoites_tripulante ON pernoites_operacionais (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_tripulantes_base_lower ON tripulantes (LOWER(base));
CREATE INDEX IF NOT EXISTS idx_excepcionais_competencia ON produtividade_adicionais_excepcionais (competencia);
CREATE INDEX IF NOT EXISTS idx_excepcionais_tripulante ON produtividade_adicionais_excepcionais (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_produtividade_conferencias_competencia ON produtividade_conferencias (competencia, conferido_em DESC);
CREATE INDEX IF NOT EXISTS idx_produtividade_conferencias_tripulante ON produtividade_conferencias (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_treinamento_anexos_treinamento ON treinamento_anexos_pdf (treinamento_id, enviado_em DESC);
CREATE INDEX IF NOT EXISTS idx_treinamento_anexos_status ON treinamento_anexos_pdf (status);
CREATE INDEX IF NOT EXISTS idx_tripulante_arquivos_tripulante ON tripulante_arquivos_pdf (tripulante_id, enviado_em DESC);
CREATE INDEX IF NOT EXISTS idx_tripulante_arquivos_status ON tripulante_arquivos_pdf (status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tripulante_arquivos_hash_ativo
ON tripulante_arquivos_pdf (tripulante_id, arquivo_hash)
WHERE status = 'ativo';
CREATE INDEX IF NOT EXISTS idx_backups_exec_status ON backups_execucoes (status, executado_em DESC);
CREATE INDEX IF NOT EXISTS idx_backups_exec_em ON backups_execucoes (executado_em DESC);
CREATE INDEX IF NOT EXISTS idx_treinamentos_data_venc_tripulante ON treinamentos (data_vencimento, tripulante_id);
CREATE INDEX IF NOT EXISTS idx_background_jobs_status_schedule ON background_jobs (status, scheduled_for, priority, id);
CREATE INDEX IF NOT EXISTS idx_background_jobs_requested_by ON background_jobs (requested_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_background_jobs_created ON background_jobs (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_idempotency
ON background_jobs (idempotency_key)
WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_background_job_executions_job ON background_job_executions (job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_request_error_events_captured_at ON request_error_events (captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_request_error_events_status_code ON request_error_events (status, code, captured_at DESC);
"""


def _expected_tables_from_schema() -> list[str]:
    return sorted(set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", SCHEMA)))


_REQUIRED_COLUMNS_BY_TABLE = {
    "usuarios": ["id", "nome", "login", "email", "senha_hash", "perfil", "ativo", "permissao_modulos_json"],
    "tripulantes": [
        "id",
        "nome",
        "cpf",
        "licenca_anac",
        "email",
        "telefone",
        "base",
        "status",
        "ativo",
        "funcao_operacional",
        "categoria_operacional",
        "sdea_ativo",
        "instrutor_ativo",
        "checador_ativo",
        "elegivel_adicional_excepcional",
        "observacoes",
        "foto_base64",
        "foto_storage_ref",
        "foto_mime_type",
        "possui_foto",
    ],
    "tipos_treinamento": [
        "id",
        "nome",
        "codigo",
        "descricao",
        "periodicidade_meses",
        "modalidade",
        "periodicidade_meses_tipo",
        "exige_equipamento",
        "ativo",
    ],
    "segmentos_teoricos": [
        "id",
        "tipo_treinamento_id",
        "referencia_original_id",
        "modelo_segmento",
        "nome_segmento",
        "carga_horaria",
        "carga_teorica",
        "carga_pratica",
        "periodicidade_meses",
        "observacao",
        "ativo",
    ],
    "horas_voo_aeronave": [
        "id",
        "tipo_treinamento_id",
        "referencia_original_id",
        "aeronave_modelo",
        "solo_horas",
        "voo_pic_sic_horas",
        "voo_crew_horas",
        "observacao",
        "ativo",
    ],
    "treinamentos": [
        "id",
        "tripulante_id",
        "equipamento_id",
        "tipo_treinamento_id",
        "segmento_teorico_id",
        "aeronave_modelo",
        "ctac_solo_horas",
        "ctac_voo_pic_sic_horas",
        "ctac_voo_crew_horas",
        "data_realizacao",
        "data_vencimento",
        "observacao",
    ],
    "missoes_operacionais": [
        "id",
        "codigo_voo",
        "contratante",
        "data_inicio",
        "data_fim",
        "origem",
        "destino",
        "tipo_operacao",
        "conta_missao_produtividade",
        "observacoes",
        "criado_em",
    ],
    "pernoites_operacionais": ["id", "tripulante_id", "missao_id", "data_pernoite", "tipo_pernoite", "quantidade", "observacoes"],
    "treinamento_anexos_pdf": [
        "id",
        "treinamento_id",
        "nome_original",
        "nome_interno",
        "mime_type",
        "tamanho_bytes",
        "storage_ref",
        "arquivo_pdf",
        "arquivo_hash",
        "status",
        "enviado_por",
        "enviado_em",
    ],
    "tripulante_arquivos_pdf": [
        "id",
        "tripulante_id",
        "tipo_documento",
        "nome_original",
        "nome_interno",
        "mime_type",
        "tamanho_bytes",
        "storage_ref",
        "arquivo_pdf",
        "arquivo_hash",
        "status",
        "enviado_por",
        "enviado_em",
        "substitui_arquivo_id",
        "removido_por",
        "removido_em",
        "motivo_status",
    ],
    "backups_execucoes": ["id", "tipo", "status", "arquivo_principal", "artefatos", "tamanho_bytes", "duracao_ms", "mensagem", "executado_em"],
    "background_jobs": [
        "id",
        "job_type",
        "payload",
        "status",
        "priority",
        "scheduled_for",
        "idempotency_key",
        "attempts",
        "max_attempts",
        "locked_by",
        "locked_at",
        "last_error",
        "requested_by",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "origin_request_id",
    ],
    "background_job_executions": [
        "id",
        "job_id",
        "attempt",
        "status",
        "worker_id",
        "error",
        "started_at",
        "finished_at",
        "duration_ms",
        "result_payload",
    ],
    "request_error_events": [
        "id",
        "request_id",
        "status",
        "code",
        "error_type",
        "error_message",
        "path",
        "endpoint",
        "method",
        "user_id",
        "context_json",
        "captured_at",
    ],
}
