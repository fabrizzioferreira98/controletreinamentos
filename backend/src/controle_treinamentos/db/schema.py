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
    sdea_icao_validade DATE,
    instrutor_ativo INTEGER NOT NULL DEFAULT 0,
    instrutor_inicio DATE,
    instrutor_fim DATE,
    checador_ativo INTEGER NOT NULL DEFAULT 0,
    checador_inicio DATE,
    checador_fim DATE,
    checador_carta_designacao TEXT,
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
    categoria_financeira TEXT CHECK (
        categoria_financeira IS NULL
        OR categoria_financeira IN ('a', 'b', 'turbohelice_palmas', 'nao_aplicavel')
    ),
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
    observacao TEXT,
    CONSTRAINT treinamentos_structure_no_program_fields_without_segment CHECK (
        segmento_teorico_id IS NOT NULL
        OR (
            NULLIF(TRIM(COALESCE(aeronave_modelo, '')), '') IS NULL
            AND ctac_solo_horas IS NULL
            AND ctac_voo_pic_sic_horas IS NULL
            AND ctac_voo_crew_horas IS NULL
        )
    ),
    CONSTRAINT treinamentos_structure_program_forbids_equipment CHECK (
        segmento_teorico_id IS NULL OR equipamento_id IS NULL
    )
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

CREATE TABLE IF NOT EXISTS pernoites_operacionais (
    id SERIAL PRIMARY KEY,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id) ON DELETE CASCADE,
    data_pernoite DATE NOT NULL,
    tipo_pernoite TEXT NOT NULL CHECK (tipo_pernoite IN ('cobertura_base', 'operacional_comum')),
    quantidade INTEGER NOT NULL DEFAULT 1,
    observacoes TEXT
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
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'removido')),
    enviado_por INTEGER REFERENCES usuarios (id),
    enviado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removido_por INTEGER REFERENCES usuarios (id),
    removido_em TIMESTAMP,
    motivo_status TEXT
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

CREATE TABLE IF NOT EXISTS financeiro_missoes_operacionais (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    competencia TEXT NOT NULL CHECK (competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    data_missao DATE NOT NULL,
    data_final DATE,
    cavok_numero_voo TEXT,
    contratante TEXT,
    chamado TEXT,
    aeronave_id INTEGER REFERENCES equipamentos (id),
    categoria_financeira_aeronave TEXT,
    comandante_tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id),
    copiloto_tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id),
    horario_apresentacao TIMESTAMP NOT NULL,
    horario_abandono TIMESTAMP NOT NULL,
    pos_exec_min INTEGER NOT NULL DEFAULT 0 CHECK (pos_exec_min >= 0),
    trecho TEXT,
    houve_pernoite BOOLEAN NOT NULL DEFAULT FALSE,
    quantidade_pernoites INTEGER NOT NULL DEFAULT 0 CHECK (quantidade_pernoites >= 0),
    cobertura_base BOOLEAN NOT NULL DEFAULT FALSE,
    operacao_especial TEXT,
    justificativa TEXT,
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'ativa', 'cancelada', 'recalculo_pendente')),
    observacoes TEXT,
    created_by INTEGER REFERENCES usuarios (id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES usuarios (id),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_by INTEGER REFERENCES usuarios (id),
    deleted_at TIMESTAMP,
    delete_reason TEXT,
    CONSTRAINT financeiro_missoes_operacionais_tripulantes_distintos
        CHECK (comandante_tripulante_id <> copiloto_tripulante_id),
    CONSTRAINT financeiro_missoes_operacionais_periodo_valido
        CHECK (data_final IS NULL OR data_final >= data_missao),
    CONSTRAINT financeiro_missoes_operacionais_horarios_validos
        CHECK (horario_abandono > horario_apresentacao)
);

CREATE TABLE IF NOT EXISTS financeiro_missao_tripulantes (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    missao_operacional_id BIGINT NOT NULL REFERENCES financeiro_missoes_operacionais (id) ON DELETE CASCADE,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id),
    funcao TEXT NOT NULL CHECK (funcao IN ('comandante', 'copiloto')),
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'removido', 'cancelado')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_financeiro_missao_tripulantes_org_missao_funcao
        UNIQUE (org_id, missao_operacional_id, funcao),
    CONSTRAINT uq_financeiro_missao_tripulantes_org_missao_tripulante
        UNIQUE (org_id, missao_operacional_id, tripulante_id)
);

CREATE TABLE IF NOT EXISTS financeiro_parametros (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    tipo TEXT NOT NULL,
    funcao TEXT,
    categoria TEXT,
    valor NUMERIC(14,4) NOT NULL,
    unidade TEXT NOT NULL,
    vigencia_inicio DATE NOT NULL,
    vigencia_fim DATE,
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo', 'substituido')),
    motivo TEXT,
    created_by INTEGER REFERENCES usuarios (id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES usuarios (id),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT financeiro_parametros_vigencia_valida
        CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)
);

CREATE TABLE IF NOT EXISTS financeiro_feriados (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    data DATE NOT NULL,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('nacional', 'estadual', 'municipal', 'operacional')),
    localidade TEXT,
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo')),
    created_by INTEGER REFERENCES usuarios (id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES usuarios (id),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS financeiro_competencias (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    competencia TEXT NOT NULL CHECK (competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    status TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta', 'em_conferencia', 'fechada', 'reaberta')),
    totals_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    fechamento_snapshot JSONB,
    closed_by INTEGER REFERENCES usuarios (id),
    closed_at TIMESTAMP,
    reopen_reason TEXT,
    reopened_by INTEGER REFERENCES usuarios (id),
    reopened_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_financeiro_competencias_org_competencia UNIQUE (org_id, competencia)
);

CREATE TABLE IF NOT EXISTS financeiro_calculos_horarios (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    missao_operacional_id BIGINT NOT NULL REFERENCES financeiro_missoes_operacionais (id) ON DELETE CASCADE,
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id),
    funcao TEXT NOT NULL CHECK (funcao IN ('comandante', 'copiloto')),
    jornada_total_minutos INTEGER NOT NULL DEFAULT 0 CHECK (jornada_total_minutos >= 0),
    minutos_diurnos INTEGER NOT NULL DEFAULT 0 CHECK (minutos_diurnos >= 0),
    minutos_noturnos INTEGER NOT NULL DEFAULT 0 CHECK (minutos_noturnos >= 0),
    minutos_noturnos_reais INTEGER NOT NULL DEFAULT 0 CHECK (minutos_noturnos_reais >= 0),
    horas_noturnas_convertidas NUMERIC(10,4) NOT NULL DEFAULT 0,
    minutos_pre INTEGER NOT NULL DEFAULT 0 CHECK (minutos_pre >= 0),
    minutos_pos INTEGER NOT NULL DEFAULT 0 CHECK (minutos_pos >= 0),
    domingo_feriado BOOLEAN NOT NULL DEFAULT FALSE,
    valor_adicional_noturno NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_domingo_feriado_diurno NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_domingo_feriado_noturno NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_pre NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_pos NUMERIC(14,2) NOT NULL DEFAULT 0,
    total NUMERIC(14,2) NOT NULL DEFAULT 0,
    memoria_calculo JSONB NOT NULL DEFAULT '{}'::jsonb,
    parametros_usados JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculation_version TEXT NOT NULL DEFAULT 'v1',
    status TEXT NOT NULL DEFAULT 'calculado' CHECK (status IN ('calculado', 'recalculo_pendente', 'obsoleto')),
    calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS financeiro_calculos_produtividade (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    competencia TEXT NOT NULL CHECK (competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    tripulante_id INTEGER NOT NULL REFERENCES tripulantes (id),
    funcao TEXT NOT NULL CHECK (funcao IN ('comandante', 'copiloto')),
    categoria_aplicavel TEXT,
    valor_icao NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_instrutor NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_checador NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_missoes_categoria_a NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_missoes_categoria_b NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_cobertura_base NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_pernoite_comum NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_excecao_palmas NUMERIC(14,2) NOT NULL DEFAULT 0,
    produtividade_calculada NUMERIC(14,2) NOT NULL DEFAULT 0,
    garantia_minima NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_devido NUMERIC(14,2) NOT NULL DEFAULT 0,
    memoria_calculo JSONB NOT NULL DEFAULT '{}'::jsonb,
    parametros_usados JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculation_version TEXT NOT NULL DEFAULT 'v1',
    status TEXT NOT NULL DEFAULT 'calculado' CHECK (status IN ('calculado', 'recalculo_pendente', 'obsoleto')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_financeiro_calculos_produtividade_org_comp_trip_funcao
        UNIQUE (org_id, competencia, tripulante_id, funcao)
);

CREATE TABLE IF NOT EXISTS financeiro_divergencias (
    id BIGSERIAL PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'default_single_tenant',
    competencia TEXT CHECK (competencia IS NULL OR competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    entidade_tipo TEXT NOT NULL,
    entidade_id BIGINT,
    severidade TEXT NOT NULL CHECK (severidade IN ('bloqueante', 'alta', 'media', 'informativa')),
    codigo TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta', 'resolvida', 'ignorada')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_by INTEGER REFERENCES usuarios (id),
    resolved_at TIMESTAMP
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
CREATE INDEX IF NOT EXISTS idx_pernoites_data_tipo ON pernoites_operacionais (data_pernoite, tipo_pernoite);
CREATE INDEX IF NOT EXISTS idx_pernoites_tripulante ON pernoites_operacionais (tripulante_id);
CREATE INDEX IF NOT EXISTS idx_tripulantes_base_lower ON tripulantes (LOWER(base));
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
CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_org_competencia
ON financeiro_missoes_operacionais (org_id, competencia, data_missao);
CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_org_status
ON financeiro_missoes_operacionais (org_id, status);
CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_comandante
ON financeiro_missoes_operacionais (org_id, comandante_tripulante_id, competencia);
CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_copiloto
ON financeiro_missoes_operacionais (org_id, copiloto_tripulante_id, competencia);
CREATE INDEX IF NOT EXISTS idx_financeiro_missao_tripulantes_org_missao
ON financeiro_missao_tripulantes (org_id, missao_operacional_id);
CREATE INDEX IF NOT EXISTS idx_financeiro_missao_tripulantes_org_tripulante
ON financeiro_missao_tripulantes (org_id, tripulante_id, funcao);
CREATE INDEX IF NOT EXISTS idx_financeiro_missao_tripulantes_org_status
ON financeiro_missao_tripulantes (org_id, status);
CREATE INDEX IF NOT EXISTS idx_financeiro_parametros_org_tipo_vigencia
ON financeiro_parametros (org_id, tipo, funcao, categoria, vigencia_inicio, vigencia_fim);
CREATE INDEX IF NOT EXISTS idx_financeiro_parametros_org_status
ON financeiro_parametros (org_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financeiro_feriados_org_data_tipo_localidade
ON financeiro_feriados (org_id, data, tipo, COALESCE(localidade, ''));
CREATE INDEX IF NOT EXISTS idx_financeiro_feriados_org_data
ON financeiro_feriados (org_id, data);
CREATE INDEX IF NOT EXISTS idx_financeiro_feriados_org_status
ON financeiro_feriados (org_id, status);
CREATE INDEX IF NOT EXISTS idx_financeiro_competencias_org_status
ON financeiro_competencias (org_id, status, competencia);
CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_active_org_competencia
ON financeiro_missoes_operacionais (org_id, competencia, data_missao)
WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_financeiro_missoes_operacionais_deleted
ON financeiro_missoes_operacionais (org_id, deleted_at)
WHERE deleted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_financeiro_calculos_horarios_org_missao_tripulante_funcao
ON financeiro_calculos_horarios (org_id, missao_operacional_id, tripulante_id, funcao);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financeiro_calculos_horarios_current
ON financeiro_calculos_horarios (org_id, missao_operacional_id, tripulante_id, funcao)
WHERE status <> 'obsoleto';
CREATE INDEX IF NOT EXISTS idx_financeiro_calculos_horarios_org_status
ON financeiro_calculos_horarios (org_id, status);
CREATE INDEX IF NOT EXISTS idx_financeiro_calculos_produtividade_org_comp_trip_funcao
ON financeiro_calculos_produtividade (org_id, competencia, tripulante_id, funcao);
CREATE INDEX IF NOT EXISTS idx_financeiro_calculos_produtividade_org_status
ON financeiro_calculos_produtividade (org_id, status);
CREATE INDEX IF NOT EXISTS idx_financeiro_divergencias_org_competencia_status
ON financeiro_divergencias (org_id, competencia, status);
CREATE INDEX IF NOT EXISTS idx_financeiro_divergencias_org_severidade
ON financeiro_divergencias (org_id, severidade, created_at DESC);
"""


def _expected_tables_from_schema() -> list[str]:
    return sorted(set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", SCHEMA)))


_REQUIRED_COLUMNS_BY_TABLE = {
    "usuarios": ["id", "nome", "login", "email", "senha_hash", "perfil", "ativo", "permissao_modulos_json"],
    "equipamentos": [
        "id",
        "nome",
        "tipo",
        "categoria_financeira",
        "ativo",
    ],
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
        "sdea_icao_validade",
        "instrutor_ativo",
        "instrutor_inicio",
        "instrutor_fim",
        "checador_ativo",
        "checador_inicio",
        "checador_fim",
        "checador_carta_designacao",
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
    "pernoites_operacionais": ["id", "tripulante_id", "data_pernoite", "tipo_pernoite", "quantidade", "observacoes"],
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
        "removido_por",
        "removido_em",
        "motivo_status",
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
    "financeiro_missoes_operacionais": [
        "id",
        "org_id",
        "competencia",
        "data_missao",
        "data_final",
        "cavok_numero_voo",
        "contratante",
        "chamado",
        "aeronave_id",
        "categoria_financeira_aeronave",
        "comandante_tripulante_id",
        "copiloto_tripulante_id",
        "horario_apresentacao",
        "horario_abandono",
        "pos_exec_min",
        "trecho",
        "houve_pernoite",
        "quantidade_pernoites",
        "cobertura_base",
        "operacao_especial",
        "justificativa",
        "status",
        "observacoes",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
        "deleted_by",
        "deleted_at",
        "delete_reason",
    ],
    "financeiro_missao_tripulantes": [
        "id",
        "org_id",
        "missao_operacional_id",
        "tripulante_id",
        "funcao",
        "status",
        "created_at",
    ],
    "financeiro_parametros": [
        "id",
        "org_id",
        "tipo",
        "funcao",
        "categoria",
        "valor",
        "unidade",
        "vigencia_inicio",
        "vigencia_fim",
        "status",
        "motivo",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    ],
    "financeiro_feriados": [
        "id",
        "org_id",
        "data",
        "nome",
        "tipo",
        "localidade",
        "status",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    ],
    "financeiro_competencias": [
        "id",
        "org_id",
        "competencia",
        "status",
        "totals_snapshot",
        "fechamento_snapshot",
        "closed_by",
        "closed_at",
        "reopen_reason",
        "reopened_by",
        "reopened_at",
        "created_at",
        "updated_at",
    ],
    "financeiro_calculos_horarios": [
        "id",
        "org_id",
        "missao_operacional_id",
        "tripulante_id",
        "funcao",
        "jornada_total_minutos",
        "minutos_diurnos",
        "minutos_noturnos",
        "minutos_noturnos_reais",
        "horas_noturnas_convertidas",
        "minutos_pre",
        "minutos_pos",
        "domingo_feriado",
        "valor_adicional_noturno",
        "valor_domingo_feriado_diurno",
        "valor_domingo_feriado_noturno",
        "valor_pre",
        "valor_pos",
        "total",
        "memoria_calculo",
        "parametros_usados",
        "calculation_version",
        "status",
        "calculated_at",
        "created_at",
        "updated_at",
    ],
    "financeiro_calculos_produtividade": [
        "id",
        "org_id",
        "competencia",
        "tripulante_id",
        "funcao",
        "categoria_aplicavel",
        "valor_icao",
        "valor_instrutor",
        "valor_checador",
        "valor_missoes_categoria_a",
        "valor_missoes_categoria_b",
        "valor_cobertura_base",
        "valor_pernoite_comum",
        "valor_excecao_palmas",
        "produtividade_calculada",
        "garantia_minima",
        "total_devido",
        "memoria_calculo",
        "parametros_usados",
        "calculation_version",
        "status",
        "created_at",
        "updated_at",
    ],
    "financeiro_divergencias": [
        "id",
        "org_id",
        "competencia",
        "entidade_tipo",
        "entidade_id",
        "severidade",
        "codigo",
        "mensagem",
        "detalhes",
        "status",
        "created_at",
        "resolved_by",
        "resolved_at",
    ],
}
