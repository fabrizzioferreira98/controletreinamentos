from __future__ import annotations

import math
import os

# Pagination
DEFAULT_PAGE_SIZE = 20

# Validation limits
MAX_TEXT_LENGTH = {
    "nome": 160,
    "codigo": 80,
    "login": 80,
    "email": 160,
    "telefone": 32,
    "base": 120,
    "status": 40,
    "descricao": 4000,
    "funcao_operacional": 32,
    "categoria_operacional": 16,
    "codigo_voo": 48,
    "contratante": 120,
    "origem": 120,
    "destino": 120,
    "tipo_operacao": 80,
    "aeronave_modelo": 160,
    "modelo_segmento": 40,
    "nome_segmento": 200,
    "observacao": 2000,
    "observacoes": 2000,
    "email_destinatario": 160,
    "matricula": 32,
    "tipo_documento": 80,
    "motivo_status": 240,
}

# Upload/photo constraints
PHOTO_ALLOWED_MIME = ("image/jpeg", "image/png", "image/webp")
PHOTO_PREFIXES = (
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/png;base64,",
    "data:image/webp;base64,",
)
MAX_PHOTO_BYTES = 1 * 1024 * 1024

TRAINING_ATTACHMENT_MAX_MB = max(1, int((os.getenv("TRAINING_ATTACHMENT_MAX_MB", "20") or "20").strip()))
TRAINING_ATTACHMENT_MAX_BYTES = TRAINING_ATTACHMENT_MAX_MB * 1024 * 1024
TRAINING_ATTACHMENT_ALLOWED_MIME = {"application/pdf"}

TRIPULANTE_FILE_MAX_MB = max(1, int((os.getenv("TRIPULANTE_FILE_MAX_MB", str(TRAINING_ATTACHMENT_MAX_MB)) or str(TRAINING_ATTACHMENT_MAX_MB)).strip()))
TRIPULANTE_FILE_MAX_BYTES = TRIPULANTE_FILE_MAX_MB * 1024 * 1024
TRIPULANTE_FILE_ALLOWED_MIME = {"application/pdf"}

# Domain options
TRIPULANTE_STATUS_OPTIONS = (
    "Ativo",
    "Folga",
    "Férias",
    "Atestado",
    "Afastado",
    "Treinamento",
)
TRIPULANTE_FUNCAO_OPTIONS = ("comandante", "copiloto", "outro")
TRIPULANTE_CATEGORIA_OPTIONS = ("A", "B", "N/A")
PERNOITE_TIPO_OPTIONS = ("cobertura_base", "operacional_comum")
TRAINING_MASTER_STATUS_OPTIONS = ("Ativo", "Inativo")
TRAINING_TYPE_MODALITY_OPTIONS = ("segmentado", "direto")
TRAINING_SEGMENT_MODEL_OPTIONS = ("Gerais", "Específicos", "Especiais", "Solo e Voo", "Outros")
TRAINING_PERIODICITY_OPTIONS = (
    {"value": 12, "label": "12 meses"},
    {"value": 24, "label": "24 meses"},
    {"value": 36, "label": "36 meses"},
    {"value": 0, "label": "Sem validade"},
)

def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or str(default)).strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _resolve_minutes(minutes_env: str, seconds_env: str, default_minutes: int) -> int:
    raw_minutes = (os.getenv(minutes_env, "") or "").strip()
    if raw_minutes:
        return max(1, _env_int(minutes_env, default_minutes))
    raw_seconds = (os.getenv(seconds_env, "") or "").strip()
    if raw_seconds:
        seconds = max(1, _env_int(seconds_env, default_minutes * 60))
        return max(1, int(math.ceil(seconds / 60)))
    return max(1, int(default_minutes))


# Auth lockout (supports both *_MINUTES and legacy *_SECONDS env names).
LOGIN_ATTEMPT_WINDOW_MINUTES = _resolve_minutes(
    "LOGIN_ATTEMPT_WINDOW_MINUTES",
    "LOGIN_ATTEMPT_WINDOW_SECONDS",
    10,
)
LOGIN_MAX_ATTEMPTS = max(1, _env_int("LOGIN_MAX_ATTEMPTS", 5))
LOGIN_LOCKOUT_MINUTES = _resolve_minutes(
    "LOGIN_LOCKOUT_MINUTES",
    "LOGIN_LOCKOUT_SECONDS",
    15,
)

# UI labels
AUDIT_ENTITY_LABELS = {
    "tripulante": "Tripulante",
    "treinamento": "Treinamento",
    "equipamento": "Equipamento",
    "tipo_treinamento": "Tipo de treinamento",
    "usuario": "Usuario",
    "notificacao_email": "Notificacao de e-mail",
    "pernoite_operacional": "Pernoite operacional",
    "piloto": "Piloto",
    "documento_gerado": "Documento gerado",
    "treinamento_anexo_pdf": "Anexo PDF de treinamento",
    "tripulante_arquivo_pdf": "Documento PDF de tripulante",
    "tripulante_photo": "Foto de tripulante",
    "background_job": "Job operacional",
}
AUDIT_ACTION_LABELS = {
    "create": "Criacao",
    "update": "Atualizacao",
    "delete": "Exclusao",
    "status_change": "Mudanca de status",
    "move": "Movimentacao",
    "download": "Download",
    "document_generate": "Geracao de documento",
    "enqueue_manual": "Enfileiramento manual",
    "requeue_dead_letter": "Reprocessamento",
}

PT_BR_MONTHS = [
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]
PT_BR_WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

CONSOLIDATED_STATUS_FILTERS = (
    "sem_vencimento",
    "vencido",
    "critico_15",
    "vencer_30",
    "vencer_60",
    "vencer_90",
    "em_dia",
)
CONSOLIDATED_SORT_OPTIONS = ("criticidade", "vencimento")

# In-memory caches (single-process)
NAV_CACHE_TTL_SECONDS = 60
PANEL_CACHE_TTL_SECONDS = 45
OPTIONS_CACHE_TTL_SECONDS = 120
DASHBOARD_CACHE_TTL_SECONDS = 45
