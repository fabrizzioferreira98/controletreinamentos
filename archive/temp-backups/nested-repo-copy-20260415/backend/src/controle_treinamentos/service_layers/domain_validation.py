from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

from ..bases import STATUS_META
from ..constants import (
    TRIPULANTE_FILE_ALLOWED_MIME,
    TRIPULANTE_FILE_MAX_BYTES,
    TRAINING_ATTACHMENT_ALLOWED_MIME,
    TRAINING_ATTACHMENT_MAX_BYTES,
    TRIPULANTE_CATEGORIA_OPTIONS,
    TRIPULANTE_FUNCAO_OPTIONS,
    TRIPULANTE_STATUS_OPTIONS,
)
from ..core.http_utils import safe_pdf_filename
from ..db import ensure_base_exists
from ..repositories.queries import resolve_tripulante_pilot_matricula
from ..services import add_months, parse_date


def parse_tripulante_ids(raw_values):
    values = sorted({int(item) for item in raw_values if str(item).isdigit()})
    if not values:
        raise ValueError("Selecione ao menos um tripulante para a missão.")
    return values

def validate_missao_tripulantes_exist(db, tripulante_ids: list[int]):
    rows = db.execute(
        "SELECT id FROM tripulantes WHERE id = ANY(%s)",
        (tripulante_ids,),
    ).fetchall()
    found_ids = {int(row["id"]) for row in rows}
    missing = [trip_id for trip_id in tripulante_ids if trip_id not in found_ids]
    if missing:
        raise ValueError("Há tripulante(s) inválido(s) na missão selecionada.")

def validate_pernoite_references(db, *, tripulante_id: int, missao_id: int | None):
    tripulante = db.execute(
        "SELECT id FROM tripulantes WHERE id = %s",
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        raise ValueError("Tripulante inválido para o pernoite.")
    if missao_id is None:
        return
    missao = db.execute(
        "SELECT id FROM missoes_operacionais WHERE id = %s",
        (missao_id,),
    ).fetchone()
    if not missao:
        raise ValueError("Missão relacionada inválida.")
    vinculo = db.execute(
        "SELECT 1 FROM missao_tripulantes WHERE missao_id = %s AND tripulante_id = %s",
        (missao_id, tripulante_id),
    ).fetchone()
    if not vinculo:
        raise ValueError("O tripulante selecionado não está vinculado à missão informada.")

def _sync_auto_pernoites_for_missao(
    db,
    *,
    missao_id: int,
    tripulante_ids: list[int],
    data_pernoite: str,
    tipo_pernoite: str,
    quantidade: int,
):
    db.execute(
        """
        DELETE FROM pernoites_operacionais
        WHERE missao_id = %s
          AND observacoes LIKE '[AUTO-MISSAO]%%'
        """,
        (missao_id,),
    )
    observacao = "[AUTO-MISSAO] Gerado automaticamente no cadastro da missão."
    for tripulante_id in tripulante_ids:
        db.execute(
            """
            INSERT INTO pernoites_operacionais (
                tripulante_id, missao_id, data_pernoite, tipo_pernoite, quantidade, observacoes
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (tripulante_id, missao_id, data_pernoite, tipo_pernoite, quantidade, observacao),
        )

def find_duplicate_adicional_excepcional(
    db,
    *,
    tripulante_id: int,
    competencia: str,
    exclude_id: int | None = None,
):
    query = (
        "SELECT id FROM produtividade_adicionais_excepcionais "
        "WHERE tripulante_id = %s AND competencia = %s AND ativo = TRUE"
    )
    params: list = [tripulante_id, competencia]
    if exclude_id is not None:
        query += " AND id <> %s"
        params.append(exclude_id)
    return db.execute(query, tuple(params)).fetchone()


_TRIPULANTE_STATUS_CANONICAL_MAP = {
    "ativo": "Ativo",
    "folga": "Folga",
    "ferias": "Férias",
    "férias": "Férias",
    "atestado": "Atestado",
    "afastado": "Afastado",
    "treinamento": "Treinamento",
}


def normalize_tripulante_status(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return _TRIPULANTE_STATUS_CANONICAL_MAP.get(raw.lower())


def tripulante_status_filter_values(value: str | None) -> tuple[str, ...]:
    normalized = normalize_tripulante_status(value)
    if not normalized:
        return ()
    if normalized == "Férias":
        # Compatibilidade com registros históricos sem acento.
        return ("Férias", "Ferias")
    return (normalized,)


def validate_tripulante_status(value: str) -> str:
    normalized = normalize_tripulante_status(value)
    if normalized is None or normalized not in TRIPULANTE_STATUS_OPTIONS:
        raise ValueError("Selecione um status válido para o tripulante.")
    return normalized

def validate_tripulante_funcao(value: str) -> str:
    if value not in TRIPULANTE_FUNCAO_OPTIONS:
        raise ValueError("Selecione uma função operacional válida.")
    return value

def validate_tripulante_categoria(value: str) -> str:
    if value not in TRIPULANTE_CATEGORIA_OPTIONS:
        raise ValueError("Selecione uma categoria operacional válida.")
    return value

def _validate_pdf_upload(
    file_storage,
    *,
    max_bytes: int,
    allowed_mime: set[str],
    fallback_name: str,
):
    if file_storage is None:
        raise ValueError("Selecione um arquivo PDF para enviar.")

    raw_name = (getattr(file_storage, "filename", "") or "").strip()
    if not raw_name or not raw_name.lower().endswith(".pdf"):
        raise ValueError("Apenas arquivos PDF são permitidos.")
    original_name = safe_pdf_filename(raw_name, fallback=fallback_name)

    file_bytes = file_storage.read()
    if not file_bytes:
        raise ValueError("O arquivo enviado está vazio.")
    if len(file_bytes) > max_bytes:
        raise ValueError(f"O PDF excede o limite de {max_bytes // (1024 * 1024)} MB.")
    if not file_bytes.startswith(b"%PDF"):
        raise ValueError("Arquivo inválido. Envie um PDF válido.")
    if b"%%EOF" not in file_bytes[-4096:]:
        raise ValueError("Arquivo PDF inválido ou corrompido.")

    mime_type = (getattr(file_storage, "mimetype", "") or "").lower().strip()
    if mime_type and mime_type not in allowed_mime and mime_type != "application/octet-stream":
        raise ValueError("Tipo de arquivo inválido. Envie apenas PDF.")

    return {
        "nome_original": original_name,
        "nome_interno": f"{uuid4().hex}_{original_name}",
        "mime_type": "application/pdf",
        "tamanho_bytes": len(file_bytes),
        "arquivo_hash": hashlib.sha256(file_bytes).hexdigest(),
        "arquivo_pdf": file_bytes,
        "storage_ref": None,
    }

def validate_pdf_upload(file_storage):
    return _validate_pdf_upload(
        file_storage,
        max_bytes=TRAINING_ATTACHMENT_MAX_BYTES,
        allowed_mime=TRAINING_ATTACHMENT_ALLOWED_MIME,
        fallback_name="anexo.pdf",
    )

def validate_tripulante_file_upload(file_storage):
    return _validate_pdf_upload(
        file_storage,
        max_bytes=TRIPULANTE_FILE_MAX_BYTES,
        allowed_mime=TRIPULANTE_FILE_ALLOWED_MIME,
        fallback_name="documento_tripulante.pdf",
    )

def validate_training_references(db, tripulante_id, tipo_treinamento_id, equipamento_id, current_training=None):
    tripulante = db.execute("SELECT id FROM tripulantes WHERE id = %s", (tripulante_id,)).fetchone()
    if not tripulante:
        raise ValueError("O tripulante selecionado não existe.")

    current_tipo_id = current_training["tipo_treinamento_id"] if current_training is not None else None
    tipo = db.execute(
        "SELECT id, exige_equipamento FROM tipos_treinamento WHERE id = %s AND (ativo = 1 OR id = %s)",
        (tipo_treinamento_id, current_tipo_id or 0),
    ).fetchone()
    if not tipo:
        raise ValueError("O tipo de treinamento selecionado não existe ou está inativo.")

    if tipo["exige_equipamento"] and equipamento_id is None:
        raise ValueError("Este tipo de treinamento exige um equipamento ou aeronave vinculado.")

    if equipamento_id is not None:
        current_equipamento_id = current_training["equipamento_id"] if current_training is not None else None
        equipamento = db.execute(
            "SELECT id FROM equipamentos WHERE id = %s AND (ativo = 1 OR id = %s)",
            (equipamento_id, current_equipamento_id or 0),
        ).fetchone()
        if not equipamento:
            raise ValueError("O equipamento selecionado não existe ou está inativo.")

def training_dates_are_valid(data_realizacao, data_vencimento):
    realized = data_realizacao if isinstance(data_realizacao, date) else parse_date(data_realizacao)
    due = data_vencimento if isinstance(data_vencimento, date) else parse_date(data_vencimento)
    if realized and due and realized > due:
        return False
    return True

def resolve_due_date(db, tipo_treinamento_id, data_realizacao, provided_due_date, due_date_mode="auto"):
    mode = (due_date_mode or "auto").strip().lower()
    if mode == "manual":
        if not provided_due_date:
            raise ValueError("Informe a data de vencimento ao escolher o modo manual.")
        return provided_due_date

    if provided_due_date:
        return provided_due_date
    if not data_realizacao:
        raise ValueError("Informe a data de vencimento ou a data de realização para cálculo automático.")
    tipo = db.execute(
        "SELECT periodicidade_meses FROM tipos_treinamento WHERE id = %s",
        (tipo_treinamento_id,),
    ).fetchone()
    if not tipo or not tipo["periodicidade_meses"]:
        raise ValueError("Não foi possível calcular o vencimento porque o tipo de treinamento não possui periodicidade válida.")
    calculated_due_date = add_months(data_realizacao, int(tipo["periodicidade_meses"]))
    if not calculated_due_date:
        raise ValueError("Não foi possível calcular a data de vencimento com os dados informados.")
    return calculated_due_date

def normalize_pilot_status(value: str | None):
    raw = (value or "").strip().lower()
    if raw in STATUS_META:
        return raw
    for key, item in STATUS_META.items():
        if raw == item["label"].lower():
            return key
    return None

def sync_linked_pilot_from_tripulante(
    db,
    *,
    tripulante_id: int,
    nome: str,
    licenca_anac: str,
    base_nome: str,
    status_text: str,
    is_active: bool,
):
    linked_pilot = db.execute(
        "SELECT id, base_id, status FROM pilotos WHERE tripulante_id = %s",
        (tripulante_id,),
    ).fetchone()

    ensured_base = ensure_base_exists(db, base_nome)
    next_base_id = ensured_base["id"] if ensured_base else (linked_pilot["base_id"] if linked_pilot else None)
    mapped_base = db.execute(
        "SELECT id FROM bases WHERE ativa = TRUE AND LOWER(nome) = LOWER(%s)",
        (base_nome,),
    ).fetchone()
    if mapped_base:
        next_base_id = mapped_base["id"]

    if is_active:
        next_status = normalize_pilot_status(status_text) or (linked_pilot["status"] if linked_pilot else "ativo")
    else:
        next_status = "afastado"
    if linked_pilot:
        next_matricula = resolve_tripulante_pilot_matricula(
            db,
            tripulante_id=tripulante_id,
            licenca_anac=licenca_anac,
            current_pilot_id=linked_pilot["id"],
        )
        db.execute(
            """
            UPDATE pilotos
            SET nome = %s, matricula = %s, base_id = %s, status = %s
            WHERE id = %s
            """,
            (nome, next_matricula, next_base_id, next_status, linked_pilot["id"]),
        )
        return

    if next_base_id is None:
        return

    db.execute(
        """
        INSERT INTO pilotos (nome, matricula, tripulante_id, base_id, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (tripulante_id) DO NOTHING
        """,
        (
            nome,
            resolve_tripulante_pilot_matricula(db, tripulante_id=tripulante_id, licenca_anac=licenca_anac),
            tripulante_id,
            next_base_id,
            next_status,
        ),
    )
