from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
import json
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..audit import record_audit_event
from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from ..core.domain_errors import DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..financeiro_audit_events import FINANCE_AUDIT_EVENTS_BY_NAME
from ..repositories.financeiro_missoes import fetch_competencia_financeira
from .financeiro_jornada_query import (
    consultar_equipamento_basico as fetch_equipamento_basico,
    consultar_feriados_jornada as listar_feriados_por_datas,
    consultar_linha_jornada as fetch_linha_jornada,
    consultar_linhas_jornada as listar_linhas_jornada,
    consultar_linhas_jornada_periodo as listar_linhas_jornada_periodo,
    consultar_participacoes_produtividade_jornada as listar_participacoes_produtividade_jornada,
    consultar_produtividade_jornada as listar_produtividade_jornada,
    consultar_tripulante_basico as fetch_tripulante_basico,
    contar_linhas_jornada_recorte as contar_linhas_jornada,
    contar_linhas_jornada_periodo_recorte as contar_linhas_jornada_periodo,
)
from .financeiro_competencias import recalcular_competencia_financeira
from .financeiro_missoes import (
    atualizar_missao_operacional,
    criar_missao_operacional,
    preview_missao_operacional,
    recalcular_missao_operacional,
    validar_competencia_aberta_para_mutacao,
)

_COMPETENCIA_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_VALID_FUNCOES = {"comandante", "copiloto"}
_VALID_CATEGORIAS = {"a", "b", "turbohelice_palmas", "nao_aplicavel"}
_VALID_EXTRATO_TIPOS = {"horaria", "produtividade", "ambos"}
_MAX_EXTRATO_DAYS = 92
_PDF_EOF_MARKER = b"%%EOF"
_PDF_EOF_SCAN_BYTES = 4096
_UNPERSISTED_HOURLY_MESSAGE = (
    "Existem lançamentos sem cálculo persistido. Recalcule a grade antes de exportar o relatório financeiro."
)


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _assert_pdf_bytes_complete(content: bytes, *, code: str) -> bytes:
    data = bytes(content or b"")
    if not data:
        raise DomainError("PDF gerado vazio.", status=500, code=f"{code}_empty")
    if not data.startswith(b"%PDF"):
        raise DomainError("PDF gerado sem assinatura valida.", status=500, code=f"{code}_invalid_signature")
    if _PDF_EOF_MARKER not in data[-_PDF_EOF_SCAN_BYTES:]:
        raise DomainError("PDF gerado incompleto.", status=500, code=f"{code}_incomplete")
    return data


def _text(value, default: str = "") -> str:
    return str(value or "").strip() or default


def _optional_text(value) -> str | None:
    text = _text(value)
    return text or None


def _int(value, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _bool(value, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "sim", "yes", "on"}


def _decimal(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _decimal_unquantized(value) -> Decimal:
    return Decimal(str(value or "0"))


def _money(value) -> str:
    return format(_decimal(value), "f")


def _pdf_money(value) -> str:
    amount = _decimal(value)
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _iso_date(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def _iso_datetime(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _text(value)


def _normalize_competencia(value) -> str:
    competencia = _text(value)
    if not _COMPETENCIA_RE.match(competencia):
        raise DomainValidationError(
            "Competencia invalida. Use o formato YYYY-MM.",
            code="finance_journey_invalid_competencia",
            details={"field": "competencia"},
        )
    return competencia


def _parse_iso_date(value, *, label: str) -> date:
    raw = _text(value)
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise DomainValidationError(
            f"{label} invalida. Use o formato YYYY-MM-DD.",
            code="finance_journey_extract_invalid_date",
            details={"field": label, "value": raw, "expected_format": "YYYY-MM-DD"},
        ) from exc


def _normalize_funcao(value: str | None) -> str | None:
    funcao = _text(value).lower()
    if not funcao:
        return None
    aliases = {
        "cmt": "comandante",
        "comandante": "comandante",
        "cop": "copiloto",
        "copiloto": "copiloto",
    }
    normalized = aliases.get(funcao, funcao)
    if normalized not in _VALID_FUNCOES:
        raise DomainValidationError(
            "Funcao operacional invalida.",
            code="finance_journey_invalid_funcao",
            details={"field": "funcao", "allowed": sorted(_VALID_FUNCOES)},
        )
    return normalized


def _ensure_date_inside_competencia(data_missao: str, competencia: str) -> None:
    if not data_missao.startswith(f"{competencia}-"):
        raise DomainValidationError(
            "Data da linha deve pertencer a competencia informada.",
            code="finance_journey_date_outside_competencia",
            details={"field": "data", "competencia": competencia, "data": data_missao},
        )


def _line_missing_fields(payload: dict) -> list[str]:
    required = {
        "competencia": payload.get("competencia"),
        "data": payload.get("data") or payload.get("data_missao"),
        "tripulante_id": payload.get("tripulante_id"),
        "funcao": payload.get("funcao"),
        "aeronave_id": payload.get("aeronave_id"),
    }
    return [key for key, value in required.items() if value in (None, "")]


def _optional_payload_text(payload: dict, keys: tuple[str, ...], *, existing: dict | None = None, existing_key: str) -> str | None:
    for key in keys:
        if key in payload:
            value = _text(payload.get(key))
            return value or None
    if existing is not None:
        value = _text(existing.get(existing_key))
        return value or None
    return None


def _category_from_payload(payload: dict, equipamento: dict | None = None, existing: dict | None = None) -> str:
    raw = _text(
        payload.get("categoria_financeira_aeronave")
        or payload.get("categoria_operacional")
        or payload.get("tipo")
        or (existing or {}).get("categoria_financeira_aeronave")
        or (equipamento or {}).get("categoria_financeira")
    ).lower()
    if raw in {"vd", "vn", "normal"} and _text((equipamento or {}).get("categoria_financeira")):
        raw = _text((equipamento or {}).get("categoria_financeira")).lower()
    aliases = {
        "vd": "nao_aplicavel",
        "vn": "nao_aplicavel",
        "normal": "nao_aplicavel",
        "categoria a": "a",
        "categoria b": "b",
        "palmas turboelice": "turbohelice_palmas",
        "palmas turboélice": "turbohelice_palmas",
    }
    category = aliases.get(raw, raw)
    if category in _VALID_CATEGORIAS:
        return category
    if not category:
        raise DomainValidationError(
            "Categoria operacional e obrigatoria para criar a linha.",
            code="finance_journey_category_required",
            details={"field": "categoria_financeira_aeronave"},
        )
    raise DomainValidationError(
        "Categoria operacional invalida.",
        code="finance_journey_invalid_category",
        details={"field": "categoria_financeira_aeronave", "value": raw},
    )


def _validate_write_references(db, *, tripulante_id: int, aeronave_id: int) -> tuple[dict, dict]:
    tripulante = fetch_tripulante_basico(db, tripulante_id=tripulante_id)
    if not tripulante or not bool(tripulante.get("ativo")):
        raise DomainValidationError(
            "Tripulante inexistente ou inativo.",
            code="finance_journey_invalid_tripulante",
            details={"field": "tripulante_id", "tripulante_id": tripulante_id},
        )
    equipamento = fetch_equipamento_basico(db, aeronave_id=aeronave_id)
    if not equipamento or not bool(equipamento.get("ativo")):
        raise DomainValidationError(
            "Aeronave/equipamento inexistente ou inativo.",
            code="finance_journey_invalid_aeronave",
            details={"field": "aeronave_id", "aeronave_id": aeronave_id},
        )
    return tripulante, equipamento


def _row_status(row: dict) -> str:
    if _text(row.get("missao_status")).lower() == "cancelada":
        return "cancelada"
    if _text(row.get("linha_status")).lower() != "ativo":
        return _text(row.get("linha_status")).lower()
    return _text(row.get("calculo_status")) or "pendente"


def _is_hourly_line_payable(line: dict) -> bool:
    status = _text(line.get("calculation_status") or line.get("status")).lower()
    return status == "calculado" and not line.get("erros")


def _unpersisted_hourly_lines(lines: list[dict]) -> list[dict]:
    pending = []
    for line in lines:
        if _is_hourly_line_payable(line):
            continue
        status = _text(line.get("calculation_status") or line.get("status")).lower()
        if status in {"cancelada", "cancelado", "excluida", "excluída", "excluido", "obsoleto"}:
            continue
        pending.append(line)
    return pending


def _assert_no_unpersisted_hourly_lines(lines: list[dict], *, filters: dict) -> None:
    pending = _unpersisted_hourly_lines(lines)
    if not pending:
        return
    raise DomainValidationError(
        _UNPERSISTED_HOURLY_MESSAGE,
        code="finance_hourly_unpersisted_lines",
        status=409,
        details={
            "filters": filters,
            "pending_count": len(pending),
            "pending_lines": [
                {
                    "linha_id": item.get("linha_id") or item.get("id"),
                    "missao_operacional_id": item.get("missao_operacional_id"),
                    "tripulante_id": item.get("tripulante_id"),
                    "funcao": item.get("funcao"),
                    "status": item.get("calculation_status") or item.get("status"),
                }
                for item in pending[:20]
            ],
        },
    )


def _line_errors_and_warnings(row: dict) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    if _text(row.get("missao_status")).lower() == "cancelada":
        warnings.append({"code": "mission_cancelled", "message": "Missao operacional cancelada."})
    if not row.get("calculo_horario_id"):
        warnings.append({"code": "calculation_pending", "message": "Linha ainda sem calculo horario vigente."})
    if _text(row.get("operacao_especial")):
        warnings.append({"code": "special_condition", "message": "Linha possui condicao operacional especial."})
    if _tipo_pernoite(row) == "pernoite_comum":
        warnings.append(
            {
                "code": "pernoite_comum_sem_cobertura",
                "message": (
                    "Pernoite comum sem cobertura: aplica valor somente a partir do segundo pernoite "
                    "quando houver parametro financeiro vigente."
                ),
            }
        )
    return errors, warnings


def _tipo_pernoite(row: dict) -> str:
    quantidade = _int(row.get("quantidade_pernoites"))
    if quantidade <= 0:
        return "sem_pernoite"
    if _bool(row.get("cobertura_base")):
        return "cobertura_base"
    return "pernoite_comum"


def _hora_reduzida_minutos(row: dict) -> int:
    if row.get("hora_reduzida_minutos") not in (None, ""):
        return _int(row.get("hora_reduzida_minutos"))
    converted_hours = row.get("horas_noturnas_convertidas")
    if converted_hours in (None, ""):
        return 0
    return int((_decimal_unquantized(converted_hours) * Decimal("60")).quantize(Decimal("1")))


def _serialize_line(row: dict, *, competencia_fechada: bool = False) -> dict:
    errors, warnings = _line_errors_and_warnings(row)
    jornada_total = _int(row.get("jornada_total_minutos"))
    minutos_pre = _int(row.get("minutos_pre"))
    minutos_pos = _int(row.get("pos_exec_min") if row.get("pos_exec_min") not in (None, "") else row.get("minutos_pos"))
    valor_domingo_diurno = _decimal(row.get("valor_domingo_feriado_diurno"))
    valor_domingo_noturno = _decimal(row.get("valor_domingo_feriado_noturno"))
    status = _row_status(row)
    payable = status == "calculado"
    total = _decimal(row.get("calculo_total")) if payable else Decimal("0")
    if not payable:
        valor_domingo_diurno = Decimal("0")
        valor_domingo_noturno = Decimal("0")
    valor_normal = max(Decimal("0"), total - valor_domingo_diurno - valor_domingo_noturno)
    editable = (not competencia_fechada) and status != "cancelada"
    return {
        "id": _int(row.get("linha_id")),
        "linha_id": _int(row.get("linha_id")),
        "missao_operacional_id": _int(row.get("missao_operacional_id")),
        "competencia": _text(row.get("competencia")),
        "data": _iso_date(row.get("data_missao")),
        "data_missao": _iso_date(row.get("data_missao")),
        "data_final": _iso_date(row.get("data_final") or row.get("data_missao")),
        "tripulante_id": _int(row.get("linha_tripulante_id")),
        "tripulante": {
            "id": _int(row.get("linha_tripulante_id")),
            "nome": _text(row.get("tripulante_nome")),
            "cpf": _text(row.get("tripulante_cpf")),
            "licenca_anac": _text(row.get("tripulante_licenca_anac")),
            "funcao_operacional": _text(row.get("tripulante_funcao_operacional")),
            "categoria_operacional": _text(row.get("tripulante_categoria_operacional")),
        },
        "funcao": _text(row.get("linha_funcao")),
        "aeronave_id": _int(row.get("aeronave_id")),
        "comandante_tripulante_id": _int(row.get("comandante_tripulante_id")),
        "copiloto_tripulante_id": _int(row.get("copiloto_tripulante_id")),
        "aeronave": {
            "id": _int(row.get("aeronave_id")),
            "nome": _text(row.get("aeronave_nome")),
            "tipo": _text(row.get("aeronave_tipo")),
            "categoria_financeira": _text(row.get("aeronave_categoria_financeira")),
        },
        "relatorio_voo": _text(row.get("cavok_numero_voo")),
        "numero_db": _text(row.get("chamado")),
        "contratante": _text(row.get("contratante")),
        "trecho": _text(row.get("trecho")),
        "hora_apresentacao": _text(row.get("horario_apresentacao")),
        "hora_abandono": _text(row.get("horario_abandono")),
        "pos_exec_min": minutos_pos,
        "houve_pernoite": _bool(row.get("houve_pernoite")),
        "quantidade_pernoites": _int(row.get("quantidade_pernoites")),
        "cobertura_base": _bool(row.get("cobertura_base")),
        "tipo_pernoite": _tipo_pernoite(row),
        "pernoites_remuneraveis": (
            max(0, _int(row.get("quantidade_pernoites")) - 1)
            if _tipo_pernoite(row) == "pernoite_comum"
            else 0
        ),
        "operacao_especial": _text(row.get("operacao_especial")),
        "justificativa": _text(row.get("justificativa")),
        "observacao": _text(row.get("observacoes")),
        "tipo": _text(row.get("categoria_financeira_aeronave")),
        "jornada_total_minutos": jornada_total,
        "minutos_diurnos": _int(row.get("minutos_diurnos")),
        "minutos_noturnos": _int(row.get("minutos_noturnos_reais") or row.get("minutos_noturnos")),
        "horas_noturnas_convertidas": _text(row.get("horas_noturnas_convertidas") or "0.0000"),
        "hora_reduzida_minutos": _hora_reduzida_minutos(row),
        "pre_calculo_min": minutos_pre,
        "pos_calculo_min": minutos_pos,
        "valor_normal": _money(valor_normal),
        "valor_diurno": _money(valor_domingo_diurno),
        "valor_noturno": _money(_decimal(row.get("valor_adicional_noturno")) + valor_domingo_noturno),
        "valor_diurno_domingo_feriado": _money(valor_domingo_diurno),
        "valor_noturno_domingo_feriado": _money(valor_domingo_noturno),
        "total": _money(total),
        "status": status,
        "calculation_status": _text(row.get("calculo_status")) or "pendente",
        "calculation_version": _text(row.get("calculation_version")),
        "calculated_at": _iso_datetime(row.get("calculated_at")),
        "erros": errors,
        "avisos": warnings,
        "pode_editar": editable,
        "pode_recalcular": editable and status != "pendente",
    }


def _period_status(db, *, competencia: str, org_id: str) -> dict:
    period = fetch_competencia_financeira(db, competencia=competencia, org_id=org_id)
    return dict(period) if period else {"competencia": competencia, "org_id": org_id, "status": "aberta"}


def _indicator_values(lines: list[dict], productivity_rows: list[dict], feriados: set[str]) -> dict:
    payable_hourly_lines = [line for line in lines if _is_hourly_line_payable(line)]
    total_horario = sum((_decimal(item.get("total")) for item in payable_hourly_lines), Decimal("0"))
    payable_productivity_rows = [row for row in productivity_rows if _productivity_payable(row)]
    produtividade_total = sum((_decimal(row.get("total_devido")) for row in payable_productivity_rows), Decimal("0"))
    hora_reduzida_minutos = sum(_hora_reduzida_minutos(item) for item in payable_hourly_lines)
    valor_diurno = sum((_decimal(item.get("valor_diurno_domingo_feriado")) for item in payable_hourly_lines), Decimal("0"))
    valor_noturno = sum((_decimal(item.get("valor_noturno_domingo_feriado")) for item in payable_hourly_lines), Decimal("0"))
    total_geral = total_horario + produtividade_total
    return {
        "total_geral": _money(total_geral),
        "quantidade_linhas": len(lines),
        "linhas_calculadas": len(payable_hourly_lines),
        "linhas_pendentes_calculo": len(_unpersisted_hourly_lines(lines)),
        "hora_reduzida_total": round(hora_reduzida_minutos / 60, 2),
        "hora_reduzida_total_minutos": hora_reduzida_minutos,
        "excecoes": sum(1 for item in lines if item.get("erros") or item.get("avisos") or item.get("justificativa")),
        "alertas_descanso": sum(1 for item in lines if _int(item.get("pos_exec_min")) > 0),
        "domingos": sum(1 for item in lines if _is_sunday(item.get("data"))),
        "feriados": sum(1 for item in lines if item.get("data") in feriados),
        "valor_normal": _money(total_horario - valor_diurno - valor_noturno),
        "valor_diurno_domingo_feriado": _money(valor_diurno),
        "valor_noturno_domingo_feriado": _money(valor_noturno),
        "produtividade_total": _money(produtividade_total),
        "resultado_atual": _money(total_geral),
    }


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _memory_messages(memory: dict, *keys: str) -> list[dict]:
    messages: list[dict] = []
    for key in keys:
        raw_items = memory.get(key) or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if isinstance(item, dict):
                text = _text(item.get("message") or item.get("mensagem") or item.get("code") or item.get("codigo"))
                code = _text(item.get("code") or item.get("codigo") or key)
            else:
                text = _text(item)
                code = key
            if text:
                messages.append({"code": code, "message": text})
    return messages


def _productivity_status(row: dict) -> str:
    return _text(row.get("status"), "calculado").lower()


def _productivity_payable(row: dict) -> bool:
    return _productivity_status(row) not in {
        "obsoleto",
        "recalculo_pendente",
        "cancelado",
        "cancelada",
        "bloqueado",
        "bloqueada",
        "erro",
    }


def _productivity_special_conditions(participations: list[dict]) -> list[dict]:
    seen: set[tuple[str, int | None]] = set()
    conditions: list[dict] = []
    for item in participations:
        text = _text(item.get("operacao_especial"))
        if not text:
            continue
        key = (text.lower(), item.get("tripulante_id"))
        if key in seen:
            continue
        seen.add(key)
        conditions.append(
            {
                "tripulante_id": item.get("tripulante_id"),
                "tripulante_nome": _text(item.get("tripulante_nome")),
                "funcao": _text(item.get("funcao")),
                "missao_operacional_id": item.get("missao_operacional_id"),
                "condicao_operacional_especial": text,
            }
        )
    return conditions


def consolidar_produtividade_jornada(
    *,
    competencia: str,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    actor_user_id: int = 0,
    org_id: str | None = None,
    db=None,
) -> dict:
    del actor_user_id
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    validated_competencia = _normalize_competencia(competencia)
    normalized_funcao = _normalize_funcao(funcao)
    period = _period_status(resolved_db, competencia=validated_competencia, org_id=resolved_org_id)
    calculations = listar_produtividade_jornada(
        resolved_db,
        competencia=validated_competencia,
        org_id=resolved_org_id,
        funcao=normalized_funcao,
        tripulante_id=tripulante_id,
    )
    active_calculations = [row for row in calculations if _productivity_status(row) != "obsoleto"]
    payable_calculations = [row for row in active_calculations if _productivity_payable(row)]
    participations = [
        item
        for item in listar_participacoes_produtividade_jornada(
            resolved_db,
            competencia=validated_competencia,
            org_id=resolved_org_id,
            funcao=normalized_funcao,
            tripulante_id=tripulante_id,
        )
        if _text(item.get("missao_status")).lower() != "cancelada"
        and _text(item.get("participante_status"), "ativo").lower() == "ativo"
    ]

    alerts: list[dict] = []
    blocks: list[dict] = []
    blocked_calculations_count = 0
    by_tripulante: dict[int, dict] = {}
    by_funcao: dict[str, dict] = {}

    for row in active_calculations:
        memory = _json_dict(row.get("memoria_calculo"))
        row_alerts = _memory_messages(memory, "alertas", "avisos", "warnings", "pendencias")
        row_blocks = _memory_messages(memory, "bloqueios", "inconsistencias", "errors")
        tripulante_key = _int(row.get("tripulante_id"))
        funcao_key = _text(row.get("funcao"), "operacional")
        total = _decimal(row.get("total_devido")) if _productivity_payable(row) else Decimal("0")
        produtividade = _decimal(row.get("produtividade_calculada")) if _productivity_payable(row) else Decimal("0")

        trip_item = by_tripulante.setdefault(
            tripulante_key,
            {
                "tripulante_id": tripulante_key,
                "tripulante_nome": _text(row.get("tripulante_nome")) or f"ID {tripulante_key}",
                "funcoes": set(),
                "calculos": 0,
                "missões_consideradas": 0,
                "missoes_consideradas": 0,
                "missões_bloqueadas": 0,
                "missoes_bloqueadas": 0,
                "excecoes": 0,
                "alertas": 0,
                "valor_pernoite_comum": Decimal("0"),
                "produtividade_calculada": Decimal("0"),
                "total_devido": Decimal("0"),
            },
        )
        trip_item["funcoes"].add(funcao_key)
        trip_item["calculos"] += 1
        trip_item["alertas"] += len(row_alerts)
        trip_item["excecoes"] += _int(row.get("valor_excecao_palmas") and Decimal(str(row.get("valor_excecao_palmas"))) > 0)
        trip_item["valor_pernoite_comum"] += _decimal(row.get("valor_pernoite_comum")) if _productivity_payable(row) else Decimal("0")
        trip_item["produtividade_calculada"] += produtividade
        trip_item["total_devido"] += total
        is_blocked = not _productivity_payable(row) or bool(row_blocks)
        if is_blocked:
            blocked_calculations_count += 1
            trip_item["missoes_bloqueadas"] += 1
            trip_item["missões_bloqueadas"] += 1

        func_item = by_funcao.setdefault(
            funcao_key,
            {
                "funcao": funcao_key,
                "tripulantes": set(),
                "calculos": 0,
                "missões_consideradas": 0,
                "missoes_consideradas": 0,
                "missões_bloqueadas": 0,
                "missoes_bloqueadas": 0,
                "excecoes": 0,
                "alertas": 0,
                "valor_pernoite_comum": Decimal("0"),
                "total_devido": Decimal("0"),
            },
        )
        func_item["tripulantes"].add(tripulante_key)
        func_item["calculos"] += 1
        func_item["alertas"] += len(row_alerts)
        func_item["excecoes"] += _int(row.get("valor_excecao_palmas") and Decimal(str(row.get("valor_excecao_palmas"))) > 0)
        func_item["valor_pernoite_comum"] += _decimal(row.get("valor_pernoite_comum")) if _productivity_payable(row) else Decimal("0")
        func_item["total_devido"] += total
        if is_blocked:
            func_item["missoes_bloqueadas"] += 1
            func_item["missões_bloqueadas"] += 1

        for item in row_alerts:
            alerts.append({**item, "tripulante_id": tripulante_key, "funcao": funcao_key})
        for item in row_blocks:
            blocks.append({**item, "tripulante_id": tripulante_key, "funcao": funcao_key})

    missions_by_tripulante: dict[int, int] = {}
    missions_by_funcao: dict[str, int] = {}
    for item in participations:
        tripulante_key = _int(item.get("tripulante_id"))
        funcao_key = _text(item.get("funcao"), "operacional")
        missions_by_tripulante[tripulante_key] = missions_by_tripulante.get(tripulante_key, 0) + 1
        missions_by_funcao[funcao_key] = missions_by_funcao.get(funcao_key, 0) + 1

    for tripulante_key, total_missions in missions_by_tripulante.items():
        if tripulante_key in by_tripulante:
            by_tripulante[tripulante_key]["missoes_consideradas"] = total_missions
            by_tripulante[tripulante_key]["missões_consideradas"] = total_missions
    for funcao_key, total_missions in missions_by_funcao.items():
        if funcao_key in by_funcao:
            by_funcao[funcao_key]["missoes_consideradas"] = total_missions
            by_funcao[funcao_key]["missões_consideradas"] = total_missions

    conditions = _productivity_special_conditions(participations)
    total_due = sum((_decimal(row.get("total_devido")) for row in payable_calculations), Decimal("0"))
    productivity_total = sum((_decimal(row.get("produtividade_calculada")) for row in payable_calculations), Decimal("0"))

    def serialize_trip(item: dict) -> dict:
        return {
            **item,
            "funcoes": sorted(item["funcoes"]),
            "produtividade_calculada": _money(item["produtividade_calculada"]),
            "valor_pernoite_comum": _money(item["valor_pernoite_comum"]),
            "total_devido": _money(item["total_devido"]),
            "total_a_pagar": _money(item["total_devido"]),
        }

    def serialize_func(item: dict) -> dict:
        return {
            **item,
            "tripulantes": len(item["tripulantes"]),
            "valor_pernoite_comum": _money(item["valor_pernoite_comum"]),
            "total_devido": _money(item["total_devido"]),
            "total_a_pagar": _money(item["total_devido"]),
        }

    return {
        "contexto": {
            "competencia": validated_competencia,
            "funcao_operacional": normalized_funcao or "todos",
            "tripulante_id": tripulante_id,
            "status_competencia": _text(period.get("status")) or "aberta",
            "org_scope": resolved_org_id,
        },
        "indicadores": {
            "total_geral": _money(total_due),
            "total_a_pagar": _money(total_due),
            "produtividade_calculada": _money(productivity_total),
            "tripulantes": len(by_tripulante),
            "funcoes": len(by_funcao),
            "calculos": len(active_calculations),
            "missões_consideradas": len(participations),
            "missoes_consideradas": len(participations),
            "missões_bloqueadas": blocked_calculations_count,
            "missoes_bloqueadas": blocked_calculations_count,
            "excecoes": sum(1 for row in active_calculations if _decimal(row.get("valor_excecao_palmas")) > 0),
            "alertas": len(alerts),
            "condicoes_especiais": len(conditions),
            "valor_pernoite_comum": _money(
                sum((_decimal(row.get("valor_pernoite_comum")) for row in payable_calculations), Decimal("0"))
            ),
        },
        "linhas_por_tripulante": sorted(
            (serialize_trip(item) for item in by_tripulante.values()),
            key=lambda item: item["tripulante_nome"],
        ),
        "totais_por_funcao": sorted(
            (serialize_func(item) for item in by_funcao.values()),
            key=lambda item: item["funcao"],
        ),
        "alertas": alerts,
        "bloqueios": blocks,
        "condicoes_especiais": conditions,
        "filters": {
            "competencia": validated_competencia,
            "funcao": normalized_funcao,
            "tripulante_id": tripulante_id,
        },
    }


def _period_competences(start: date, end: date) -> list[str]:
    current = date(start.year, start.month, 1)
    final = date(end.year, end.month, 1)
    values: list[str] = []
    while current <= final:
        values.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return values


def _competence_fully_covered(competencia: str, start: date, end: date) -> bool:
    year, month = [int(part) for part in competencia.split("-")]
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return start <= first and end >= last


def _extract_line_from_hourly(line: dict) -> dict:
    payable = _is_hourly_line_payable(line)
    return {
        "tipo": "horaria",
        "id": line.get("id"),
        "data": line.get("data"),
        "data_final": line.get("data_final") or line.get("data"),
        "competencia": line.get("competencia"),
        "tripulante_id": line.get("tripulante_id"),
        "tripulante_nome": (line.get("tripulante") or {}).get("nome"),
        "funcao": line.get("funcao"),
        "descricao": line.get("relatorio_voo") or line.get("trecho") or f"Missao {line.get('missao_operacional_id')}",
        "trecho": line.get("trecho"),
        "justificativa": line.get("justificativa"),
        "status": line.get("calculation_status") or line.get("status"),
        "valor_total": line.get("total") if payable else "0.00",
        "alertas": line.get("avisos") or [],
        "erros": line.get("erros") or [],
        "fonte": "bonificacao_horaria_vigente" if payable else "bonificacao_horaria_pendente",
    }


def _extract_productivity_lines(
    *,
    start: date,
    end: date,
    org_id: str,
    funcao: str | None,
    tripulante_id: int | None,
    db,
) -> tuple[list[dict], list[dict]]:
    lines: list[dict] = []
    alerts: list[dict] = []
    for competencia in _period_competences(start, end):
        if not _competence_fully_covered(competencia, start, end):
            alerts.append(
                {
                    "code": "produtividade_periodo_parcial",
                    "message": (
                        f"Produtividade da competencia {competencia} nao foi somada porque "
                        "o recorte nao cobre o mes inteiro."
                    ),
                    "competencia": competencia,
                }
            )
            continue
        consolidated = consolidar_produtividade_jornada(
            competencia=competencia,
            funcao=funcao,
            tripulante_id=tripulante_id,
            org_id=org_id,
            db=db,
        )
        alerts.extend(consolidated.get("alertas") or [])
        alerts.extend(consolidated.get("bloqueios") or [])
        for item in consolidated.get("linhas_por_tripulante") or []:
            lines.append(
                {
                    "tipo": "produtividade",
                    "id": f"{competencia}:{item.get('tripulante_id')}:{','.join(item.get('funcoes') or [])}",
                    "data": f"{competencia}-01",
                    "competencia": competencia,
                    "tripulante_id": item.get("tripulante_id"),
                    "tripulante_nome": item.get("tripulante_nome"),
                    "funcao": ", ".join(item.get("funcoes") or []),
                    "descricao": f"Produtividade {competencia}",
                    "trecho": "",
                    "status": "calculado",
                    "valor_total": item.get("total_a_pagar") or item.get("total_devido") or "0.00",
                    "alertas": [],
                    "erros": [],
                    "fonte": "produtividade_vigente_competencia_fechada_no_recorte",
                }
            )
    return lines, alerts


def gerar_extrato_periodo_jornada(
    *,
    data_inicio: str,
    data_fim: str,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    tipo: str | None = None,
    actor_user_id: int = 0,
    org_id: str | None = None,
    db=None,
) -> dict:
    del actor_user_id
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    start = _parse_iso_date(data_inicio, label="data_inicio")
    end = _parse_iso_date(data_fim, label="data_fim")
    if start > end:
        raise DomainValidationError(
            "Data inicial nao pode ser maior que data final.",
            code="finance_journey_extract_invalid_period",
            details={"data_inicio": start.isoformat(), "data_fim": end.isoformat()},
        )
    interval_days = (end - start).days + 1
    if interval_days > _MAX_EXTRATO_DAYS:
        raise DomainValidationError(
            f"Intervalo maximo do extrato e de {_MAX_EXTRATO_DAYS} dias.",
            code="finance_journey_extract_period_too_large",
            details={"max_days": _MAX_EXTRATO_DAYS, "days": interval_days},
        )
    normalized_funcao = _normalize_funcao(funcao)
    normalized_tipo = _text(tipo or "ambos").lower()
    if normalized_tipo not in _VALID_EXTRATO_TIPOS:
        raise DomainValidationError(
            "Tipo de extrato invalido.",
            code="finance_journey_extract_invalid_type",
            details={"field": "tipo", "allowed": sorted(_VALID_EXTRATO_TIPOS)},
        )

    lines: list[dict] = []
    alerts: list[dict] = []
    if normalized_tipo in {"horaria", "ambos"}:
        rows = listar_linhas_jornada_periodo(
            resolved_db,
            data_inicio=start.isoformat(),
            data_fim=end.isoformat(),
            org_id=resolved_org_id,
            funcao=normalized_funcao,
            tripulante_id=tripulante_id,
            limit=5000,
            offset=0,
        )
        hourly_lines = [_serialize_line(row) for row in rows]
        lines.extend(_extract_line_from_hourly(line) for line in hourly_lines)
        for line in hourly_lines:
            alerts.extend(line.get("avisos") or [])
            alerts.extend(line.get("erros") or [])

    if normalized_tipo in {"produtividade", "ambos"}:
        productivity_lines, productivity_alerts = _extract_productivity_lines(
            start=start,
            end=end,
            org_id=resolved_org_id,
            funcao=normalized_funcao,
            tripulante_id=tripulante_id,
            db=resolved_db,
        )
        lines.extend(productivity_lines)
        alerts.extend(productivity_alerts)

    subtotal_horaria = sum((_decimal(item.get("valor_total")) for item in lines if item.get("tipo") == "horaria"), Decimal("0"))
    subtotal_produtividade = sum((_decimal(item.get("valor_total")) for item in lines if item.get("tipo") == "produtividade"), Decimal("0"))
    total_geral = subtotal_horaria + subtotal_produtividade

    return {
        "contexto": {
            "data_inicio": start.isoformat(),
            "data_fim": end.isoformat(),
            "dias": interval_days,
            "tripulante_id": tripulante_id,
            "funcao": normalized_funcao,
            "tipo": normalized_tipo,
            "org_scope": resolved_org_id,
        },
        "linhas": sorted(lines, key=lambda item: (item.get("data") or "", item.get("tripulante_nome") or "")),
        "subtotais": {
            "horaria": _money(subtotal_horaria),
            "produtividade": _money(subtotal_produtividade),
        },
        "total_geral": _money(total_geral),
        "alertas": alerts,
        "filters": {
            "data_inicio": start.isoformat(),
            "data_fim": end.isoformat(),
            "tripulante_id": tripulante_id,
            "funcao": normalized_funcao,
            "tipo": normalized_tipo,
        },
    }


def _is_sunday(value: str | None) -> bool:
    if not value:
        return False
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().weekday() == 6
    except ValueError:
        return False


def _audit(
    db,
    *,
    event_name: str,
    actor_user_id: int,
    entity_id: int,
    competencia: str,
    before=None,
    after=None,
    filters: dict | None = None,
    record_count: int | None = None,
    reason: str | None = None,
):
    event = FINANCE_AUDIT_EVENTS_BY_NAME.get(event_name, {})
    metadata = {
        "event_name": event_name,
        "org_id": (after or before or {}).get("org_id") or FINANCE_ORG_SCOPE_DEFAULT,
        "request_id": "",
        "correlation_id": "",
        "actor_user_id": actor_user_id,
        "entity_type": event.get("entity_type") or "finance_journey_grid",
        "entity_id": entity_id,
        "permission": event.get("permission") or "finance:bonuses:read",
        "source_endpoint": "",
        "competencia": competencia,
        "linha_id": entity_id,
        "mission_id": (after or before or {}).get("missao_operacional_id"),
        "filters": filters or {},
        "record_count": record_count if record_count is not None else 0,
        "reason": reason,
        "format": "json",
    }
    record_audit_event(
        db,
        entidade=event.get("entity_type") or "finance_journey_grid",
        entidade_id=int(entity_id or 0),
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior=before,
        payload_novo={"metadata": metadata, "data": after} if after is not None else {"metadata": metadata},
        observacao=f"competencia={competencia}; event={event_name}",
    )


def listar_grade_jornada(
    *,
    competencia: str,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 1000,
    offset: int = 0,
    actor_user_id: int = 0,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    validated_competencia = _normalize_competencia(competencia)
    normalized_funcao = _normalize_funcao(funcao)
    period = _period_status(resolved_db, competencia=validated_competencia, org_id=resolved_org_id)
    competencia_fechada = _text(period.get("status")).lower() == "fechada"
    rows = listar_linhas_jornada(
        resolved_db,
        competencia=validated_competencia,
        org_id=resolved_org_id,
        funcao=normalized_funcao,
        tripulante_id=tripulante_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    lines = [_serialize_line(row, competencia_fechada=competencia_fechada) for row in rows]
    datas = sorted({line["data"] for line in lines if line.get("data")})
    feriados_rows = listar_feriados_por_datas(resolved_db, org_id=resolved_org_id, datas=datas)
    feriados = {_iso_date(row.get("data")) for row in feriados_rows}
    productivity_rows = listar_produtividade_jornada(
        resolved_db,
        competencia=validated_competencia,
        org_id=resolved_org_id,
        funcao=normalized_funcao,
        tripulante_id=tripulante_id,
    )
    total = contar_linhas_jornada(
        resolved_db,
        competencia=validated_competencia,
        org_id=resolved_org_id,
        funcao=normalized_funcao,
        tripulante_id=tripulante_id,
        status=status,
    )
    filters = {
        "competencia": validated_competencia,
        "funcao": normalized_funcao,
        "tripulante_id": tripulante_id,
        "status": status,
    }
    if actor_user_id:
        _audit(
            resolved_db,
            event_name="finance.journey_grid.generated",
            actor_user_id=actor_user_id,
            entity_id=0,
            competencia=validated_competencia,
            after={"org_id": resolved_org_id, "indicadores": _indicator_values(lines, productivity_rows, feriados)},
            filters=filters,
            record_count=len(lines),
        )
        resolved_db.commit()
    return {
        "contexto": {
            "competencia": validated_competencia,
            "funcao_operacional": normalized_funcao or "todos",
            "tripulante_id": tripulante_id,
            "tripulantes": len({line["tripulante_id"] for line in lines if line.get("tripulante_id")}),
            "status_competencia": _text(period.get("status")) or "aberta",
            "competencia_fechada": competencia_fechada,
            "resultado_atual": _indicator_values(lines, productivity_rows, feriados)["resultado_atual"],
        },
        "indicadores": _indicator_values(lines, productivity_rows, feriados),
        "linhas": lines,
        "produtividade": productivity_rows,
        "permissoes": {
            "pode_editar": not competencia_fechada,
            "pode_recalcular": not competencia_fechada,
            "pode_exportar": True,
        },
        "status_competencia": _text(period.get("status")) or "aberta",
        "pagination": {
            "page": int(page),
            "page_size": int(limit),
            "total": total,
            "offset": int(offset),
        },
        "filters": filters,
    }


def _mission_payload_from_journey(
    payload: dict,
    *,
    org_id: str,
    actor_user_id: int,
    existing: dict | None = None,
    db=None,
) -> dict:
    missing = _line_missing_fields(payload) if existing is None else []
    if missing:
        raise DomainValidationError(
            "Campos obrigatorios ausentes para criar a linha.",
            code="finance_journey_required_fields",
            details={"missing_fields": missing},
        )
    competencia = _normalize_competencia(payload.get("competencia") or (existing or {}).get("competencia"))
    data_missao = _text(payload.get("data") or payload.get("data_missao") or (existing or {}).get("data_missao"))
    _ensure_date_inside_competencia(data_missao, competencia)
    data_final = _text(payload.get("data_final") or (existing or {}).get("data_final") or data_missao)
    if _parse_iso_date(data_final, label="data_final") < _parse_iso_date(data_missao, label="data_missao"):
        raise DomainValidationError(
            "Data final da missao nao pode ser anterior a data inicial.",
            code="finance_journey_invalid_data_final",
            details={"field": "data_final", "data": data_missao, "data_final": data_final},
        )
    funcao = _normalize_funcao(payload.get("funcao") or (existing or {}).get("linha_funcao"))
    tripulante_id = _int(payload.get("tripulante_id") or (existing or {}).get("linha_tripulante_id"))
    aeronave_id = _int(payload.get("aeronave_id") or (existing or {}).get("aeronave_id"))
    _, equipamento = _validate_write_references(_resolve_db(db), tripulante_id=tripulante_id, aeronave_id=aeronave_id)
    comandante_id = _int(payload.get("comandante_tripulante_id") or (existing or {}).get("comandante_tripulante_id"))
    copiloto_id = _int(payload.get("copiloto_tripulante_id") or (existing or {}).get("copiloto_tripulante_id"))
    if funcao == "comandante":
        comandante_id = tripulante_id
        copiloto_id = copiloto_id or _int(payload.get("counterpart_tripulante_id"))
    elif funcao == "copiloto":
        copiloto_id = tripulante_id
        comandante_id = comandante_id or _int(payload.get("counterpart_tripulante_id"))
    if not comandante_id or not copiloto_id:
        raise DomainValidationError(
            "A linha de jornada usa a missao operacional como base e exige comandante e copiloto para persistir.",
            code="finance_journey_crew_pair_required",
            details={"fields": ["comandante_tripulante_id", "copiloto_tripulante_id"]},
        )
    pos_exec_min = _int(payload.get("pos_exec_min") if "pos_exec_min" in payload else (existing or {}).get("pos_exec_min"))
    if pos_exec_min < 0:
        raise DomainValidationError(
            "Pos execucao em minutos nao pode ser negativo.",
            code="finance_journey_invalid_pos_exec_min",
            details={"field": "pos_exec_min"},
        )
    quantidade_pernoites = _int(
        payload.get("quantidade_pernoites")
        if "quantidade_pernoites" in payload
        else (existing or {}).get("quantidade_pernoites")
    )
    if quantidade_pernoites < 0:
        raise DomainValidationError(
            "Quantidade de pernoites nao pode ser negativa.",
            code="finance_journey_invalid_quantidade_pernoites",
            details={"field": "quantidade_pernoites"},
        )
    cobertura_base = quantidade_pernoites > 0 and _bool(
        payload.get("cobertura_base"),
        default=_bool((existing or {}).get("cobertura_base")),
    )
    return {
        "org_id": org_id,
        "competencia": competencia,
        "data_missao": data_missao,
        "data_final": data_final,
        "cavok_numero_voo": _text(payload.get("relatorio_voo") or payload.get("cavok_numero_voo") or (existing or {}).get("cavok_numero_voo")),
        "contratante": _optional_text(
            payload.get("contratante") if "contratante" in payload else (existing or {}).get("contratante")
        ),
        "chamado": _optional_text(payload.get("numero_db") or payload.get("chamado") or (existing or {}).get("chamado")),
        "aeronave_id": aeronave_id,
        "categoria_financeira_aeronave": _category_from_payload(payload, equipamento, existing),
        "comandante_tripulante_id": comandante_id,
        "copiloto_tripulante_id": copiloto_id,
        "horario_apresentacao": _optional_payload_text(
            payload,
            ("hora_apresentacao", "apresentacao", "horario_apresentacao"),
            existing=existing,
            existing_key="horario_apresentacao",
        ),
        "horario_abandono": _optional_payload_text(
            payload,
            ("hora_abandono", "abandono", "horario_abandono"),
            existing=existing,
            existing_key="horario_abandono",
        ),
        "pos_exec_min": pos_exec_min,
        "trecho": _optional_text(payload.get("trecho") if "trecho" in payload else (existing or {}).get("trecho")),
        "houve_pernoite": quantidade_pernoites > 0,
        "quantidade_pernoites": quantidade_pernoites,
        "cobertura_base": cobertura_base,
        "operacao_especial": _optional_text(
            payload.get("operacao_especial")
            if "operacao_especial" in payload
            else (existing or {}).get("operacao_especial")
        ),
        "justificativa": _optional_text(
            payload.get("justificativa")
            if "justificativa" in payload
            else (existing or {}).get("justificativa")
        ),
        "status": _text(payload.get("status") or (existing or {}).get("missao_status"), "ativa"),
        "observacoes": _optional_text(
            payload.get("observacao")
            if "observacao" in payload
            else payload.get("observacoes")
            if "observacoes" in payload
            else (existing or {}).get("observacoes")
        ),
        "created_by": actor_user_id,
        "updated_by": actor_user_id,
    }


def _recalculate_after_journey_save(
    mission_id: int,
    *,
    actor_user_id: int,
    org_id: str,
    db,
) -> dict:
    if not mission_id:
        return {"status": "pendente", "message": "Missao operacional ainda sem identificador para recalculo."}
    try:
        recalculation = {
            "status": "calculado",
            **recalcular_missao_operacional(
                mission_id,
                actor_user_id=actor_user_id,
                org_id=org_id,
                db=db,
            ),
        }
        competence = _text(recalculation.get("competence") or recalculation.get("competencia"))
        if not competence:
            return {
                **recalculation,
                "productivity_status": "pendente",
                "productivity_error": {
                    "code": "finance_journey_productivity_competence_missing",
                    "message": "Competencia ausente para recalculo automatico de produtividade.",
                },
            }
        try:
            productivity_result = recalcular_competencia_financeira(
                competence,
                actor_user_id=actor_user_id,
                org_id=org_id,
                db=db,
            )
        except DomainError as exc:
            return {
                **recalculation,
                "productivity_status": "pendente",
                "productivity_error": {
                    "code": exc.code,
                    "message": exc.message,
                    "status": exc.status,
                    "details": exc.details,
                },
            }
        return {
            **recalculation,
            "productivity_status": "calculado",
            "productivity_recalculation": {
                "totals": productivity_result.get("totals") or {},
                "items_count": len(productivity_result.get("items") or []),
            },
        }
    except DomainError as exc:
        return {
            "status": "pendente",
            "error": {
                "code": exc.code,
                "message": exc.message,
                "status": exc.status,
                "details": exc.details,
            },
        }


def criar_linha_jornada(payload: dict, *, actor_user_id: int, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    data = _mission_payload_from_journey(payload, org_id=resolved_org_id, actor_user_id=actor_user_id, db=resolved_db)
    validar_competencia_aberta_para_mutacao(resolved_db, competencia=data["competencia"], org_id=resolved_org_id)
    mission = criar_missao_operacional(
        data,
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
        require_times=False,
    )
    recalculation = _recalculate_after_journey_save(
        _int(mission.get("id")),
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    funcao = _normalize_funcao(payload.get("funcao")) or "comandante"
    linha_tripulante_id = data["comandante_tripulante_id"] if funcao == "comandante" else data["copiloto_tripulante_id"]
    rows = listar_linhas_jornada(
        resolved_db,
        competencia=data["competencia"],
        org_id=resolved_org_id,
        funcao=funcao,
        tripulante_id=linha_tripulante_id,
        limit=10,
        offset=0,
    )
    row = next((item for item in rows if _int(item.get("missao_operacional_id")) == _int(mission.get("id"))), None)
    if not row:
        raise DomainNotFoundError("Linha de jornada criada nao encontrada.", code="finance_journey_line_not_found")
    line = _serialize_line(row)
    _audit(
        resolved_db,
        event_name="finance.journey_line.created",
        actor_user_id=actor_user_id,
        entity_id=line["id"],
        competencia=data["competencia"],
        after={**line, "org_id": resolved_org_id},
        record_count=1,
    )
    resolved_db.commit()
    return {"linha": line, "mission": mission, "recalculation": recalculation}


def atualizar_linha_jornada(linha_id: int, payload: dict, *, actor_user_id: int, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    before_row = fetch_linha_jornada(resolved_db, linha_id=int(linha_id), org_id=resolved_org_id)
    if not before_row:
        raise DomainNotFoundError("Linha de jornada nao encontrada.", code="finance_journey_line_not_found")
    requested_tripulante_id = _int(payload.get("tripulante_id")) if "tripulante_id" in payload else 0
    requested_funcao = _normalize_funcao(payload.get("funcao")) if "funcao" in payload and payload.get("funcao") else None
    current_tripulante_id = _int(before_row.get("linha_tripulante_id"))
    current_funcao = _normalize_funcao(before_row.get("linha_funcao"))
    if (requested_tripulante_id and requested_tripulante_id != current_tripulante_id) or (
        requested_funcao and requested_funcao != current_funcao
    ):
        raise DomainValidationError(
            "Alteracao de tripulante ou funcao exige recriacao controlada da missao operacional.",
            code="finance_journey_crew_change_not_supported",
            details={"fields": ["tripulante_id", "funcao"]},
        )
    validar_competencia_aberta_para_mutacao(
        resolved_db,
        competencia=_text(before_row.get("competencia")),
        org_id=resolved_org_id,
    )
    data = _mission_payload_from_journey(
        payload,
        org_id=resolved_org_id,
        actor_user_id=actor_user_id,
        existing=before_row,
        db=resolved_db,
    )
    mission = atualizar_missao_operacional(
        _int(before_row.get("missao_operacional_id")),
        data,
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
        require_times=False,
    )
    recalculation = _recalculate_after_journey_save(
        _int(before_row.get("missao_operacional_id")),
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    after_row = fetch_linha_jornada(resolved_db, linha_id=int(linha_id), org_id=resolved_org_id)
    line = _serialize_line(after_row or before_row)
    _audit(
        resolved_db,
        event_name="finance.journey_line.updated",
        actor_user_id=actor_user_id,
        entity_id=line["id"],
        competencia=line["competencia"],
        before={**_serialize_line(before_row), "org_id": resolved_org_id},
        after={**line, "org_id": resolved_org_id},
        record_count=1,
    )
    resolved_db.commit()
    return {"linha": line, "mission": mission, "recalculation": recalculation}


def preview_linha_jornada(payload: dict, *, org_id: str | None = None, db=None) -> dict:
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    missing = _line_missing_fields(payload)
    if missing:
        return {
            "estado": "pendente_dados",
            "status": "pendente_dados",
            "pendencias": [{"field": field, "message": "Campo obrigatorio para preview."} for field in missing],
            "preview": None,
        }
    funcao = _normalize_funcao(payload.get("funcao"))
    counterpart_fields = (
        ["copiloto_tripulante_id", "counterpart_tripulante_id"]
        if funcao == "comandante"
        else ["comandante_tripulante_id", "counterpart_tripulante_id"]
    )
    if not any(payload.get(field) for field in counterpart_fields):
        return {
            "estado": "pendente_dados",
            "status": "pendente_dados",
            "pendencias": [
                {
                    "field": "tripulacao",
                    "message": "Informe a dupla da missao para o preview financeiro completo.",
                }
            ],
            "preview": None,
        }
    data = _mission_payload_from_journey(payload, org_id=resolved_org_id, actor_user_id=0, db=db)
    return preview_missao_operacional(data, org_id=resolved_org_id, db=db)


def recalcular_linha_jornada(linha_id: int, *, actor_user_id: int, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    row = fetch_linha_jornada(resolved_db, linha_id=int(linha_id), org_id=resolved_org_id)
    if not row:
        raise DomainNotFoundError("Linha de jornada nao encontrada.", code="finance_journey_line_not_found")
    if _text(row.get("missao_status")).lower() == "cancelada":
        raise DomainValidationError(
            "Linha vinculada a missao cancelada nao pode ser recalculada.",
            code="finance_journey_cancelled_line_recalculation_blocked",
            status=409,
        )
    validar_competencia_aberta_para_mutacao(resolved_db, competencia=_text(row.get("competencia")), org_id=resolved_org_id)
    result = recalcular_missao_operacional(
        _int(row.get("missao_operacional_id")),
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    after_row = fetch_linha_jornada(resolved_db, linha_id=int(linha_id), org_id=resolved_org_id)
    line = _serialize_line(after_row or row)
    _audit(
        resolved_db,
        event_name="finance.journey_line.recalculated",
        actor_user_id=actor_user_id,
        entity_id=line["id"],
        competencia=line["competencia"],
        before={**_serialize_line(row), "org_id": resolved_org_id},
        after={**line, "org_id": resolved_org_id},
        record_count=1,
    )
    resolved_db.commit()
    return {"linha": line, "recalculation": result}


def recalcular_grade_jornada(payload: dict, *, actor_user_id: int, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    competencia = _normalize_competencia(payload.get("competencia"))
    funcao = _normalize_funcao(payload.get("funcao"))
    tripulante_id = _int(payload.get("tripulante_id")) or None
    validar_competencia_aberta_para_mutacao(resolved_db, competencia=competencia, org_id=resolved_org_id)
    rows = listar_linhas_jornada(
        resolved_db,
        competencia=competencia,
        org_id=resolved_org_id,
        funcao=funcao,
        tripulante_id=tripulante_id,
        limit=5000,
        offset=0,
    )
    mission_ids = sorted({_int(row.get("missao_operacional_id")) for row in rows if _int(row.get("missao_operacional_id"))})
    mission_results = []
    for mission_id in mission_ids:
        mission_results.append(
            recalcular_missao_operacional(
                mission_id,
                actor_user_id=actor_user_id,
                org_id=resolved_org_id,
                db=resolved_db,
            )
        )
    period_result = recalcular_competencia_financeira(
        competencia,
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    grade = listar_grade_jornada(
        competencia=competencia,
        funcao=funcao,
        tripulante_id=tripulante_id,
        actor_user_id=0,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    _audit(
        resolved_db,
        event_name="finance.journey_grid.recalculated",
        actor_user_id=actor_user_id,
        entity_id=0,
        competencia=competencia,
        after={"org_id": resolved_org_id, "mission_count": len(mission_ids), "indicadores": grade["indicadores"]},
        filters={"competencia": competencia, "funcao": funcao, "tripulante_id": tripulante_id},
        record_count=len(grade["linhas"]),
    )
    resolved_db.commit()
    return {
        **grade,
        "recalculation": {
            "mission_count": len(mission_ids),
            "missions": mission_results,
            "period": period_result,
        },
    }


def _pdf_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "JornadaPdfTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
        ),
        "subtitle": ParagraphStyle(
            "JornadaPdfSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748b"),
        ),
        "section": ParagraphStyle(
            "JornadaPdfSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=5,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "JornadaPdfBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8,
            textColor=colors.HexColor("#172033"),
            alignment=TA_LEFT,
        ),
        "body_center": ParagraphStyle(
            "JornadaPdfBodyCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8,
            textColor=colors.HexColor("#172033"),
            alignment=TA_CENTER,
        ),
        "body_right": ParagraphStyle(
            "JornadaPdfBodyRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8,
            textColor=colors.HexColor("#172033"),
            alignment=TA_RIGHT,
        ),
    }


def _pdf_cell(value, style):
    return Paragraph(escape(_text(value, "-")).replace("\n", "<br/>"), style)


def _pdf_table(rows, widths, *, header=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d4deea")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]
    if header:
        style.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(style))
    return table


def _pdf_page_footer(title: str):
    def _draw(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(9 * mm, 6 * mm, "Documento gerado pelo sistema")
        canvas.drawCentredString(landscape(A4)[0] / 2, 6 * mm, title)
        canvas.drawRightString(landscape(A4)[0] - 9 * mm, 6 * mm, f"Pagina {document.page}")
        canvas.restoreState()

    return _draw


def _grade_line_alerts(line: dict) -> str:
    messages = []
    for item in (line.get("avisos") or []) + (line.get("erros") or []):
        if isinstance(item, dict):
            text = _text(item.get("message") or item.get("code"))
            if text:
                messages.append(text)
    return "; ".join(messages)


def _grade_summary_rows(lines: list[dict], *, group: str) -> list[list[str]]:
    summary: dict[str, dict] = {}
    for line in [item for item in lines if _is_hourly_line_payable(item)]:
        tripulante = line.get("tripulante") or {}
        key = _text(line.get("funcao"), "Nao informado") if group == "funcao" else _text(tripulante.get("nome"), "Nao informado")
        item = summary.setdefault(key, {"linhas": 0, "minutos": 0, "total": Decimal("0")})
        item["linhas"] += 1
        item["minutos"] += _int(line.get("pos_calculo_min"))
        item["total"] += _decimal(line.get("total"))
    rows = [["Grupo", "Linhas", "Horas pos calculo", "Total"]]
    for key, item in sorted(summary.items(), key=lambda entry: entry[0]):
        rows.append([key, str(item["linhas"]), f"{round(item['minutos'] / 60, 2)} h", _pdf_money(item["total"])])
    if len(rows) == 1:
        rows.append(["-", "0", "0 h", _pdf_money(0)])
    return rows


def _build_grade_jornada_pdf_legacy(*, grade: dict, filters: dict, actor_user_id: int, request_id: str, correlation_id: str) -> bytes:
    styles = _pdf_styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=9 * mm,
        rightMargin=9 * mm,
        title=f"Lancamentos de Jornada {filters.get('competencia')}",
        author="Treinamentos Brasil Vida",
        subject="Grade mensal de lancamentos de jornada",
    )
    context = grade.get("contexto") or {}
    indicators = grade.get("indicadores") or {}
    story = [
        Paragraph("Treinamentos Brasil Vida", styles["subtitle"]),
        Paragraph("Lançamentos de Jornada", styles["title"]),
        Paragraph(
            "Recorte: competencia {competencia}; funcao {funcao}; tripulante {tripulante}; status {status}. Emitido por usuario {user}. request_id={request}; correlation_id={corr}.".format(
                competencia=_text(filters.get("competencia")),
                funcao=_text(filters.get("funcao"), "Todos"),
                tripulante=_text(filters.get("tripulante_id"), "Todos"),
                status=_text(filters.get("status"), "ativos/vigentes"),
                user=actor_user_id or "-",
                request=_text(request_id, "-"),
                corr=_text(correlation_id, "-"),
            ),
            styles["subtitle"],
        ),
        Spacer(1, 3 * mm),
        Paragraph("Contexto da grade mensal", styles["section"]),
        _pdf_table(
            [
                ["Competencia", "Funcao operacional", "Tripulantes", "Resultado atual", "Status competencia"],
                [
                    _text(context.get("competencia") or filters.get("competencia")),
                    _text(context.get("funcao_operacional") or filters.get("funcao"), "Todos"),
                    _text(context.get("tripulantes"), "0"),
                    _pdf_money(context.get("resultado_atual") or indicators.get("resultado_atual")),
                    _text(context.get("status_competencia"), "aberta"),
                ],
            ],
            [34 * mm, 42 * mm, 28 * mm, 36 * mm, 38 * mm],
        ),
        Spacer(1, 2 * mm),
        Paragraph("Indicadores financeiros", styles["section"]),
        _pdf_table(
            [
                ["Total geral", "Linhas", "Hora reduzida", "Excecoes", "Alertas descanso", "Domingos", "Feriados", "Valor normal"],
                [
                    _pdf_money(indicators.get("total_geral")),
                    str(indicators.get("quantidade_linhas") or 0),
                    f"{indicators.get('hora_reduzida_total') or 0} h",
                    str(indicators.get("excecoes") or 0),
                    str(indicators.get("alertas_descanso") or 0),
                    str(indicators.get("domingos") or 0),
                    str(indicators.get("feriados") or 0),
                    _pdf_money(indicators.get("valor_normal")),
                ],
            ],
            [30 * mm, 20 * mm, 28 * mm, 22 * mm, 30 * mm, 22 * mm, 22 * mm, 32 * mm],
        ),
        Spacer(1, 2 * mm),
        Paragraph("Linhas do recorte", styles["section"]),
    ]
    rows = [["Data", "Tripulante / funcao", "Voo / trecho", "Jornada", "Calculo", "Valores", "Status / avisos"]]
    for line in (grade.get("linhas") or [])[:180]:
        tripulante = line.get("tripulante") or {}
        aeronave = line.get("aeronave") or {}
        avisos = "; ".join(_text(item.get("message") or item.get("code")) for item in (line.get("avisos") or []) if isinstance(item, dict))
        erros = "; ".join(_text(item.get("message") or item.get("code")) for item in (line.get("erros") or []) if isinstance(item, dict))
        rows.append(
            [
                "\n".join(
                    [
                        _text(line.get("data")),
                        f"Fim {_text(line.get('data_final') or line.get('data'))}",
                    ]
                ),
                f"{_text(tripulante.get('nome'))}\n{_text(line.get('funcao'))}",
                f"{_text(line.get('relatorio_voo'))}\n{_text(line.get('trecho'))}\n{_text(aeronave.get('nome'))}",
                "\n".join(
                    [
                        f"Apres. {_text(line.get('hora_apresentacao'))}",
                        f"Aband. {_text(line.get('hora_abandono'))}",
                        f"Pos exec. {_text(line.get('pos_exec_min'), '0')} min",
                        f"Pernoite {_text(line.get('tipo_pernoite'), 'sem_pernoite')} ({_text(line.get('quantidade_pernoites'), '0')})",
                    ]
                ),
                f"Diurna {_text(line.get('minutos_diurnos'), '0')} min\nNoturna {_text(line.get('minutos_noturnos'), '0')} min\nPre {_text(line.get('pre_calculo_min'), '0')} / Pos {_text(line.get('pos_calculo_min'), '0')}",
                f"Normal {_pdf_money(line.get('valor_normal'))}\nDiurno {_pdf_money(line.get('valor_diurno'))}\nNoturno {_pdf_money(line.get('valor_noturno'))}\nTotal {_pdf_money(line.get('total'))}",
                f"{_text(line.get('status'))} / {_text(line.get('calculation_status'))}\n{_text(avisos or erros, '-')}",
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Nenhuma linha no recorte.", "-", "-", "-", "-", "-"])
    story.append(
        _pdf_table(
            [[_pdf_cell(cell, styles["body"]) for cell in row] for row in rows],
            [20 * mm, 40 * mm, 42 * mm, 40 * mm, 45 * mm, 42 * mm, 42 * mm],
        )
    )
    document.build(story)
    value = buffer.getvalue()
    buffer.close()
    return value


def _build_grade_jornada_pdf(*, grade: dict, filters: dict, actor_user_id: int, request_id: str, correlation_id: str) -> bytes:
    styles = _pdf_styles()
    buffer = BytesIO()
    emitted_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=9 * mm,
        rightMargin=9 * mm,
        title=f"Lancamentos de Jornada {filters.get('competencia')}",
        author="Treinamentos Brasil Vida",
        subject="Grade mensal de lancamentos de jornada",
    )
    context = grade.get("contexto") or {}
    indicators = grade.get("indicadores") or {}
    lines = grade.get("linhas") or []
    story = [
        Paragraph("Treinamentos Brasil Vida", styles["subtitle"]),
        Paragraph("Lancamentos de Jornada", styles["title"]),
        Paragraph(
            "Competencia {competencia}; funcao {funcao}; tripulante {tripulante}; status {status}; emissao {emissao}; usuario {user}; request_id={request}; correlation_id={corr}.".format(
                competencia=_text(filters.get("competencia")),
                funcao=_text(filters.get("funcao"), "Todos"),
                tripulante=_text(filters.get("tripulante_id"), "Todos"),
                status=_text(filters.get("status"), "ativos/vigentes"),
                emissao=emitted_at,
                user=actor_user_id or "-",
                request=_text(request_id, "-"),
                corr=_text(correlation_id, "-"),
            ),
            styles["subtitle"],
        ),
        Spacer(1, 3 * mm),
        Paragraph("Contexto da grade mensal", styles["section"]),
        _pdf_table(
            [
                ["Competencia", "Funcao operacional", "Tripulantes", "Resultado atual", "Status competencia", "Emissao"],
                [
                    _text(context.get("competencia") or filters.get("competencia")),
                    _text(context.get("funcao_operacional") or filters.get("funcao"), "Todos"),
                    _text(context.get("tripulantes"), "0"),
                    _pdf_money(context.get("resultado_atual") or indicators.get("resultado_atual")),
                    _text(context.get("status_competencia"), "aberta"),
                    emitted_at,
                ],
            ],
            [30 * mm, 38 * mm, 24 * mm, 34 * mm, 34 * mm, 34 * mm],
        ),
        Spacer(1, 2 * mm),
        Paragraph("Indicadores financeiros", styles["section"]),
        _pdf_table(
            [
                ["Total geral", "Linhas", "Hora reduzida", "Excecoes", "Alertas descanso", "Domingos", "Feriados", "Valor normal"],
                [
                    _pdf_money(indicators.get("total_geral")),
                    str(indicators.get("quantidade_linhas") or 0),
                    f"{indicators.get('hora_reduzida_total') or 0} h",
                    str(indicators.get("excecoes") or 0),
                    str(indicators.get("alertas_descanso") or 0),
                    str(indicators.get("domingos") or 0),
                    str(indicators.get("feriados") or 0),
                    _pdf_money(indicators.get("valor_normal")),
                ],
            ],
            [30 * mm, 20 * mm, 28 * mm, 22 * mm, 30 * mm, 22 * mm, 22 * mm, 32 * mm],
        ),
        Spacer(1, 2 * mm),
        Paragraph("Linhas do recorte", styles["section"]),
    ]
    rows = [[
        "Data",
        "Tripulante",
        "Funcao",
        "Aeronave",
        "Rel. voo",
        "DB",
        "Trecho",
        "Jornada",
        "Horas",
        "Valores",
        "Total",
        "Status",
    ]]
    for line in lines[:220]:
        tripulante = line.get("tripulante") or {}
        aeronave = line.get("aeronave") or {}
        rows.append(
            [
                _text(line.get("data")),
                _text(tripulante.get("nome")),
                _text(line.get("funcao")),
                _text(aeronave.get("nome")),
                _text(line.get("relatorio_voo")),
                _text(line.get("numero_db")),
                _text(line.get("trecho")),
                f"Apres. {_text(line.get('hora_apresentacao'))}\nAband. {_text(line.get('hora_abandono'))}\nPos exec. {_text(line.get('pos_exec_min'), '0')} min",
                f"D {_text(line.get('minutos_diurnos'), '0')}\nN {_text(line.get('minutos_noturnos'), '0')}\nPre {_text(line.get('pre_calculo_min'), '0')}\nPos {_text(line.get('pos_calculo_min'), '0')}",
                f"Normal {_pdf_money(line.get('valor_normal'))}\nDiurno {_pdf_money(line.get('valor_diurno'))}\nNoturno {_pdf_money(line.get('valor_noturno'))}",
                _pdf_money(line.get("total")),
                "\n".join(
                    [
                        _text(line.get("status")),
                        _text(line.get("calculation_status")),
                        f"Cond. {_text(line.get('operacao_especial'), '-')}",
                        f"Justif. {_text(line.get('justificativa'), '-')}",
                        _text(_grade_line_alerts(line), "-"),
                    ]
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Nenhuma linha no recorte.", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"])
    story.append(
        _pdf_table(
            [[_pdf_cell(cell, styles["body"]) for cell in row] for row in rows],
            [18 * mm, 30 * mm, 19 * mm, 22 * mm, 19 * mm, 14 * mm, 22 * mm, 28 * mm, 26 * mm, 28 * mm, 22 * mm, 22 * mm],
        )
    )
    story.extend(
        [
            Spacer(1, 3 * mm),
            Paragraph("Resumo final", styles["section"]),
            _pdf_table(
                [[_pdf_cell(cell, styles["body"]) for cell in row] for row in _grade_summary_rows(lines, group="funcao")],
                [80 * mm, 26 * mm, 40 * mm, 40 * mm],
            ),
            Spacer(1, 2 * mm),
            _pdf_table(
                [[_pdf_cell(cell, styles["body"]) for cell in row] for row in _grade_summary_rows(lines, group="tripulante")],
                [80 * mm, 26 * mm, 40 * mm, 40 * mm],
            ),
            Spacer(1, 2 * mm),
            _pdf_table(
                [
                    ["Total a pagar", "Linhas exportadas", "Documento"],
                    [_pdf_money(indicators.get("total_geral")), str(len(lines)), "Fechamento do recorte atual da grade"],
                ],
                [45 * mm, 35 * mm, 95 * mm],
            ),
        ]
    )
    footer = _pdf_page_footer("Lancamentos de Jornada")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    value = buffer.getvalue()
    buffer.close()
    return value


def _filename_filter_suffix(*, funcao: str | None, tripulante_id: int | None, status: str | None) -> str:
    parts = []
    if funcao:
        parts.append(str(funcao).strip().lower())
    if tripulante_id:
        parts.append(f"tripulante-{int(tripulante_id)}")
    if status:
        parts.append(str(status).strip().lower())
    return f"-{'-'.join(parts)}" if parts else ""


def exportar_grade_jornada_pdf(
    *,
    competencia: str,
    funcao: str | None = None,
    tripulante_id: int | None = None,
    status: str | None = None,
    actor_user_id: int,
    org_id: str | None = None,
    request_id: str = "",
    correlation_id: str = "",
    source_endpoint: str = "/api/v1/financeiro/lancamentos-jornada.pdf",
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    validated_competencia = _normalize_competencia(competencia)
    normalized_funcao = _normalize_funcao(funcao)
    grade = listar_grade_jornada(
        competencia=validated_competencia,
        funcao=normalized_funcao,
        tripulante_id=tripulante_id,
        status=status,
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    filters = {
        "competencia": validated_competencia,
        "funcao": normalized_funcao,
        "tripulante_id": tripulante_id,
        "status": status,
    }
    _assert_no_unpersisted_hourly_lines(grade.get("linhas") or [], filters=filters)
    pdf_bytes = _build_grade_jornada_pdf(
        grade=grade,
        filters=filters,
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    pdf_bytes = _assert_pdf_bytes_complete(pdf_bytes, code="finance_journey_grid_pdf")
    filename = f"lancamentos-jornada-{validated_competencia}{_filename_filter_suffix(funcao=normalized_funcao, tripulante_id=tripulante_id, status=status)}.pdf"
    _audit(
        resolved_db,
        event_name="finance.journey_grid.exported",
        actor_user_id=actor_user_id,
        entity_id=0,
        competencia=validated_competencia,
        after={
            "org_id": resolved_org_id,
            "filename": filename,
            "mimetype": "application/pdf",
            "source_endpoint": source_endpoint,
            "pdf_bytes": len(pdf_bytes),
            "indicadores": grade.get("indicadores"),
        },
        filters=filters,
        record_count=len(grade.get("linhas") or []),
    )
    resolved_db.commit()
    return {
        "content": pdf_bytes,
        "filename": filename,
        "mimetype": "application/pdf",
        "metadata": {
            "filters": filters,
            "record_count": len(grade.get("linhas") or []),
            "indicadores": grade.get("indicadores"),
        },
    }


def _build_extrato_periodo_pdf(*, extrato: dict, actor_user_id: int, request_id: str, correlation_id: str) -> bytes:
    styles = _pdf_styles()
    buffer = BytesIO()
    context = extrato.get("contexto") or {}
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=9 * mm,
        rightMargin=9 * mm,
        title="Extrato por periodo",
        author="Treinamentos Brasil Vida",
        subject="Extrato financeiro por periodo",
    )
    story = [
        Paragraph("Treinamentos Brasil Vida", styles["subtitle"]),
        Paragraph("Extrato por período", styles["title"]),
        Paragraph(
            "Recorte: {inicio} a {fim}; tipo {tipo}; funcao {funcao}; tripulante {tripulante}. Emitido por usuario {user}. request_id={request}; correlation_id={corr}.".format(
                inicio=_text(context.get("data_inicio")),
                fim=_text(context.get("data_fim")),
                tipo=_text(context.get("tipo"), "ambos"),
                funcao=_text(context.get("funcao"), "Todos"),
                tripulante=_text(context.get("tripulante_id"), "Todos"),
                user=actor_user_id or "-",
                request=_text(request_id, "-"),
                corr=_text(correlation_id, "-"),
            ),
            styles["subtitle"],
        ),
        Spacer(1, 3 * mm),
        Paragraph("Totais", styles["section"]),
        _pdf_table(
            [
                ["Bonificacao horaria", "Produtividade", "Total geral", "Linhas", "Alertas"],
                [
                    _pdf_money((extrato.get("subtotais") or {}).get("horaria")),
                    _pdf_money((extrato.get("subtotais") or {}).get("produtividade")),
                    _pdf_money(extrato.get("total_geral")),
                    str(len(extrato.get("linhas") or [])),
                    str(len(extrato.get("alertas") or [])),
                ],
            ],
            [42 * mm, 42 * mm, 42 * mm, 28 * mm, 28 * mm],
        ),
        Spacer(1, 3 * mm),
        Paragraph("Linhas do extrato", styles["section"]),
    ]
    rows = [["Data", "Tipo", "Tripulante / funcao", "Descricao", "Status", "Valor", "Alertas"]]
    for line in (extrato.get("linhas") or [])[:220]:
        line_alerts = "; ".join(
            _text(item.get("message") or item.get("code"))
            for item in ((line.get("alertas") or []) + (line.get("erros") or []))
            if isinstance(item, dict)
        )
        rows.append(
            [
                _text(line.get("data")),
                _text(line.get("tipo")),
                f"{_text(line.get('tripulante_nome'))}\n{_text(line.get('funcao'))}",
                f"{_text(line.get('descricao'))}\n{_text(line.get('trecho'))}",
                _text(line.get("status")),
                _pdf_money(line.get("valor_total")),
                _text(line_alerts, "-"),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "-", "Nenhuma linha no periodo.", "-", "-", "-", "-"])
    story.append(
        _pdf_table(
            [[_pdf_cell(cell, styles["body"]) for cell in row] for row in rows],
            [22 * mm, 28 * mm, 46 * mm, 66 * mm, 30 * mm, 30 * mm, 48 * mm],
        )
    )
    if extrato.get("alertas"):
        story.extend([Spacer(1, 3 * mm), Paragraph("Alertas do recorte", styles["section"])])
        story.append(
            _pdf_table(
                [["Codigo", "Mensagem"]]
                + [[_text(item.get("code")), _text(item.get("message"))] for item in extrato.get("alertas") or []],
                [50 * mm, 210 * mm],
            )
        )
    document.build(story)
    value = buffer.getvalue()
    buffer.close()
    return value


def exportar_extrato_periodo_pdf(
    *,
    data_inicio: str,
    data_fim: str,
    tripulante_id: int | None = None,
    funcao: str | None = None,
    tipo: str | None = None,
    actor_user_id: int,
    org_id: str | None = None,
    request_id: str = "",
    correlation_id: str = "",
    source_endpoint: str = "/api/v1/financeiro/extrato-periodo.pdf",
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    extrato = gerar_extrato_periodo_jornada(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tripulante_id=tripulante_id,
        funcao=funcao,
        tipo=tipo,
        actor_user_id=actor_user_id,
        org_id=resolved_org_id,
        db=resolved_db,
    )
    _assert_no_unpersisted_hourly_lines(
        [line for line in extrato.get("linhas") or [] if line.get("tipo") == "horaria"],
        filters=extrato.get("filters") or {},
    )
    pdf_bytes = _build_extrato_periodo_pdf(
        extrato=extrato,
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    pdf_bytes = _assert_pdf_bytes_complete(pdf_bytes, code="finance_period_extract_pdf")
    filters = extrato.get("filters") or {}
    filename = f"extrato-periodo-{filters.get('data_inicio')}-{filters.get('data_fim')}.pdf"
    _audit(
        resolved_db,
        event_name="finance.extract.period.generated",
        actor_user_id=actor_user_id,
        entity_id=0,
        competencia=_text(filters.get("data_inicio"))[:7] or "periodo",
        after={
            "org_id": resolved_org_id,
            "filename": filename,
            "mimetype": "application/pdf",
            "source_endpoint": source_endpoint,
            "pdf_bytes": len(pdf_bytes),
            "subtotais": extrato.get("subtotais"),
            "total_geral": extrato.get("total_geral"),
        },
        filters=filters,
        record_count=len(extrato.get("linhas") or []),
    )
    resolved_db.commit()
    return {
        "content": pdf_bytes,
        "filename": filename,
        "mimetype": "application/pdf",
        "metadata": {
            "filters": filters,
            "record_count": len(extrato.get("linhas") or []),
            "subtotais": extrato.get("subtotais"),
            "total_geral": extrato.get("total_geral"),
        },
    }
