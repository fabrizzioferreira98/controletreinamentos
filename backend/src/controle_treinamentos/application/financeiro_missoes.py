from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from ..audit import record_audit_event
from ..contracts.financeiro import (
    FINANCE_ORG_SCOPE_DEFAULT,
    serialize_finance_mission,
    serialize_finance_mission_collection,
    serialize_finance_mission_participant,
    serialize_hourly_bonus_calculation,
)
from ..core.domain_errors import DomainConflictError, DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..financeiro_audit_events import FINANCE_AUDIT_EVENTS_BY_NAME
from ..repositories.financeiro_calculos_horarios import (
    invalidar_calculos_horarios_vigentes_da_missao,
    listar_calculos_horarios_vigentes_da_missao,
    obsoletar_calculos_vigentes_duplicados_da_missao,
    salvar_calculo_horario,
    salvar_ou_atualizar_calculo_horario_vigente,
    substituir_calculos_da_missao,
)
from ..repositories.financeiro_calculos_produtividade import (
    invalidar_calculos_produtividade_vigentes_da_competencia,
)
from ..repositories.financeiro_feriados import listar_feriados_nacionais, verificar_feriado_nacional_por_data
from ..repositories.financeiro_missoes import (
    cancel_missao_operacional as cancel_missao_operacional_row,
    cancel_missao_tripulantes,
    mission_delete_dependency_summary,
    remover_missao_tripulantes,
    replace_missao_tripulantes,
    soft_delete_missao_operacional,
)
from ..repositories.financeiro_missoes import (
    create_missao_operacional_with_tripulantes,
    fetch_competencia_financeira,
    fetch_missao_operacional,
    fetch_missao_operacional_detail,
    find_duplicate_missao_operacional,
    lock_missao_operacional,
)
from ..repositories.financeiro_missoes import (
    list_missoes_operacionais as list_missoes_operacionais_rows,
)
from ..repositories.financeiro_missoes import (
    update_missao_operacional as update_missao_operacional_row,
)
from ..repositories.financeiro_parametros import (
    listar_parametros_financeiros as listar_parametros_financeiros_rows,
)
from .financeiro_bonificacao_horaria import calcular_bonificacao_horaria


class FinanceiroDominioErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "financeiro_dominio_erro", status: int = 400):
        super().__init__(message, code=code, status=status)


class MissaoOperacionalDuplicadaErro(DomainConflictError):
    def __init__(self, message: str = "Missao operacional duplicada para a mesma identificacao."):
        super().__init__(message, code="missao_operacional_duplicada", status=409)


class CompetenciaFinanceiraFechadaErro(DomainConflictError):
    def __init__(self, competencia: str):
        super().__init__(
            f"A competencia financeira {competencia} esta fechada para mutacoes.",
            code="competencia_financeira_fechada",
            status=409,
        )


class MissaoOperacionalNaoEncontradaErro(DomainNotFoundError):
    def __init__(self, message: str = "Missao operacional nao encontrada."):
        super().__init__(message, code="missao_operacional_nao_encontrada", status=404)


class MissaoOperacionalCanceladaErro(DomainConflictError):
    def __init__(self, message: str = "Missao operacional cancelada nao pode ser recalculada."):
        super().__init__(message, code="missao_operacional_cancelada", status=409)


class MissaoOperacionalExclusaoBloqueadaErro(DomainConflictError):
    def __init__(
        self,
        message: str = "Esta missao possui calculo financeiro vinculado. Para preservar o historico, use Cancelar missao.",
        *,
        details: dict | None = None,
    ):
        super().__init__(
            message,
            code="missao_operacional_exclusao_bloqueada",
            status=409,
            details=details or {},
        )


_PREVIEW_REQUIRED_FIELDS = (
    ("competencia", "competencia"),
    ("data_missao", "data da missao"),
    ("aeronave_id", "aeronave"),
    ("categoria_financeira_aeronave", "categoria operacional"),
    ("comandante_tripulante_id", "comandante"),
    ("copiloto_tripulante_id", "copiloto"),
)


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _clean_text(value) -> str:
    return str(value or "").strip()


def _required_text(payload: dict, key: str, label: str) -> str:
    value = _clean_text(payload.get(key))
    if not value:
        raise FinanceiroDominioErro(f"{label} e obrigatorio.", code="financeiro_campo_obrigatorio")
    return value


def _optional_int(value, *, label: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise FinanceiroDominioErro(f"{label} invalido.", code="financeiro_campo_invalido") from exc


def _required_int(payload: dict, key: str, label: str) -> int:
    value = _optional_int(payload.get(key), label=label)
    if value is None:
        raise FinanceiroDominioErro(f"{label} e obrigatorio.", code="financeiro_campo_obrigatorio")
    return value


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "sim"}


def _special_operation_text(value) -> str | None:
    # TODO(financeiro): modelar operacao_especial como codigo/enum antes de validar condicoes financeiras reconhecidas.
    if isinstance(value, bool):
        return "especial" if value else None
    cleaned = _clean_text(value)
    return cleaned or None


def _parse_date_value(value, *, label: str) -> date:
    raw = _clean_text(value)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise FinanceiroDominioErro(f"{label} invalida. Use o formato YYYY-MM-DD.", code="financeiro_campo_invalido") from exc


def _parse_datetime_value(value, *, base_date: date, label: str) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, time):
        return datetime.combine(base_date, value)
    raw = _clean_text(value)
    if not raw:
        raise FinanceiroDominioErro(f"{label} e obrigatorio.", code="financeiro_campo_obrigatorio")
    try:
        if "T" not in raw and " " not in raw and "-" not in raw and ":" in raw:
            return datetime.combine(base_date, time.fromisoformat(raw))
        return datetime.fromisoformat(raw.replace(" ", "T")).replace(tzinfo=None)
    except ValueError as exc:
        raise FinanceiroDominioErro(
            f"{label} invalido. Use o formato ISO ou HH:MM.",
            code="financeiro_campo_invalido",
        ) from exc


def _parse_optional_datetime_value(value, *, base_date: date, label: str) -> datetime | None:
    if value in (None, "") or _clean_text(value) == "":
        return None
    return _parse_datetime_value(value, base_date=base_date, label=label)


def _normalize_non_negative_int(value, *, label: str, default: int = 0) -> int:
    number = _optional_int(value, label=label)
    if number is None:
        number = default
    if number < 0:
        raise FinanceiroDominioErro(f"{label} nao pode ser negativo.", code="financeiro_campo_invalido")
    return number


def _mission_payload(payload: dict, *, org_id: str, actor_user_id: int | None = None, require_times: bool = True) -> dict:
    comandante_id = _required_int(payload, "comandante_tripulante_id", "Comandante")
    copiloto_id = _required_int(payload, "copiloto_tripulante_id", "Copiloto")
    if comandante_id == copiloto_id:
        raise FinanceiroDominioErro(
            "Comandante e copiloto devem ser tripulantes distintos.",
            code="missao_operacional_tripulantes_iguais",
        )

    data_missao = _required_text(payload, "data_missao", "Data da missao operacional")
    data_final = _clean_text(payload.get("data_final")) or data_missao
    data_missao_date = _parse_date_value(data_missao, label="Data da missao operacional")
    data_final_date = _parse_date_value(data_final, label="Data final da missao")
    if data_final_date < data_missao_date:
        raise FinanceiroDominioErro(
            "Data final da missao nao pode ser anterior a data inicial.",
            code="missao_operacional_data_final_invalida",
        )
    parse_time = _parse_datetime_value if require_times else _parse_optional_datetime_value
    horario_apresentacao = parse_time(
        payload.get("horario_apresentacao"),
        base_date=data_missao_date,
        label="Horario de apresentacao",
    )
    horario_abandono = parse_time(
        payload.get("horario_abandono"),
        base_date=data_missao_date,
        label="Horario de abandono",
    )
    if horario_apresentacao is not None and horario_abandono is not None and horario_abandono <= horario_apresentacao:
        horario_abandono += timedelta(days=1)
    quantidade_pernoites = _normalize_non_negative_int(
        payload.get("quantidade_pernoites"),
        label="Quantidade de pernoites",
    )
    pos_exec_min = _normalize_non_negative_int(payload.get("pos_exec_min"), label="Pos execucao em minutos")
    houve_pernoite = quantidade_pernoites > 0 and _bool_value(payload.get("houve_pernoite", True))
    cobertura_base = quantidade_pernoites > 0 and _bool_value(payload.get("cobertura_base"))

    data = {
        "org_id": org_id,
        "competencia": _required_text(payload, "competencia", "Competencia"),
        "data_missao": data_missao,
        "data_final": data_final,
        "cavok_numero_voo": _clean_text(payload.get("cavok_numero_voo")) or None,
        "contratante": _clean_text(payload.get("contratante")) or None,
        "chamado": _clean_text(payload.get("chamado")) or None,
        "aeronave_id": _optional_int(payload.get("aeronave_id"), label="Aeronave"),
        "categoria_financeira_aeronave": _clean_text(payload.get("categoria_financeira_aeronave")) or None,
        "comandante_tripulante_id": comandante_id,
        "copiloto_tripulante_id": copiloto_id,
        "horario_apresentacao": horario_apresentacao.isoformat(timespec="minutes") if horario_apresentacao else None,
        "horario_abandono": horario_abandono.isoformat(timespec="minutes") if horario_abandono else None,
        "pos_exec_min": pos_exec_min,
        "trecho": _clean_text(payload.get("trecho")) or None,
        "houve_pernoite": houve_pernoite,
        "quantidade_pernoites": quantidade_pernoites,
        "cobertura_base": cobertura_base,
        "operacao_especial": _special_operation_text(payload.get("operacao_especial")),
        "justificativa": _clean_text(payload.get("justificativa")) or None,
        "status": _clean_text(payload.get("status")) or "rascunho",
        "observacoes": _clean_text(payload.get("observacoes")) or None,
        "created_by": actor_user_id,
        "updated_by": actor_user_id,
    }
    return data


def _normalize_update_times(data: dict, before_row: dict, *, require_times: bool = True) -> None:
    if "horario_apresentacao" not in data and "horario_abandono" not in data:
        return

    data_missao_raw = data.get("data_missao") or before_row["data_missao"]
    data_missao_date = _parse_date_value(data_missao_raw, label="Data da missao operacional")
    parse_time = _parse_datetime_value if require_times else _parse_optional_datetime_value
    horario_apresentacao = parse_time(
        data.get("horario_apresentacao", before_row.get("horario_apresentacao")),
        base_date=data_missao_date,
        label="Horario de apresentacao",
    )
    horario_abandono = parse_time(
        data.get("horario_abandono", before_row.get("horario_abandono")),
        base_date=data_missao_date,
        label="Horario de abandono",
    )
    if horario_apresentacao is not None and horario_abandono is not None and horario_abandono <= horario_apresentacao:
        horario_abandono += timedelta(days=1)
    if "horario_apresentacao" in data:
        data["horario_apresentacao"] = horario_apresentacao.isoformat(timespec="minutes") if horario_apresentacao else None
    if "horario_abandono" in data:
        data["horario_abandono"] = horario_abandono.isoformat(timespec="minutes") if horario_abandono else None


def _serialize_participant(row: dict) -> dict:
    payload = dict(row)
    payload["mission_id"] = payload.get("mission_id") or payload.get("missao_operacional_id")
    return serialize_finance_mission_participant(payload)


def _serialize_mission_detail(row: dict) -> dict:
    payload = serialize_finance_mission(row)
    payload["participantes"] = [_serialize_participant(item) for item in row.get("participantes", [])]
    return payload


def _serialize_hourly_calculation(row: dict) -> dict:
    payload = dict(row)
    payload["mission_id"] = payload.get("mission_id") or payload.get("missao_operacional_id")
    if "minutos_noturnos_reais" not in payload:
        payload["minutos_noturnos_reais"] = payload.get("minutos_noturnos")
    return serialize_hourly_bonus_calculation(payload)


def _preview_missing_fields(payload: dict) -> list[dict]:
    missing = []
    for key, label in _PREVIEW_REQUIRED_FIELDS:
        value = payload.get(key)
        if value in (None, "") or str(value).strip() == "":
            missing.append({"field": key, "label": label})
    return missing


def _preview_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview_pending_payload(payload: dict, missing_fields: list[dict]) -> dict:
    return {
        "status": "pendente_dados",
        "estado_calculo": "pendente",
        "base_calculo": "Bonificacao horaria operacional",
        "campos_faltantes": missing_fields,
        "pendencias": [
            {
                "code": "finance_preview_missing_field",
                "field": item["field"],
                "message": f"Informe {item['label']} para gerar a previa financeira.",
            }
            for item in missing_fields
        ],
        "inconsistencias": [],
        "horas_consideradas": {},
        "tripulantes_considerados": [],
        "valor_estimado": None,
        "calculations": [],
        "observacoes": [
            "A previa nao foi calculada porque ainda ha dados obrigatorios pendentes.",
            "Nenhum dado foi persistido.",
        ],
        "generated_at": _preview_now(),
        "input_ref": {
            "competencia": _clean_text(payload.get("competencia")),
            "data_missao": _clean_text(payload.get("data_missao")),
            "status": _clean_text(payload.get("status")) or "rascunho",
        },
    }


def _preview_issue_from_error(exc: DomainError) -> dict:
    return {
        "code": exc.code,
        "message": exc.message,
        "details": exc.details or {},
    }


def _decimal_text(value) -> str:
    try:
        return format(Decimal(str(value or "0")).quantize(Decimal("0.01")), "f")
    except Exception:
        return "0.00"


def _preview_hours_summary(calculations: list[dict]) -> dict:
    if not calculations:
        return {}
    jornada = max(int(item.get("jornada_total_minutos") or 0) for item in calculations)
    diurnos = max(int(item.get("minutos_diurnos") or 0) for item in calculations)
    periodo_noturno = max(int(item.get("minutos_noturnos_reais") or item.get("minutos_noturnos") or 0) for item in calculations)
    return {
        "jornada_total_minutos": jornada,
        "periodo_diurno_minutos": diurnos,
        "periodo_noturno_minutos": periodo_noturno,
    }


def _preview_calculation_row(calculation: dict, *, data: dict, org_id: str) -> dict:
    row = {
        **calculation,
        "id": None,
        "org_id": org_id,
        "competencia": data.get("competencia"),
        "mission_id": data.get("id"),
        "missao_operacional_id": data.get("id"),
        "data_missao": data.get("data_missao"),
        "data_final": data.get("data_final") or data.get("data_missao"),
        "cavok_numero_voo": data.get("cavok_numero_voo"),
        "contratante": data.get("contratante"),
        "chamado": data.get("chamado"),
        "aeronave_id": data.get("aeronave_id"),
        "categoria_financeira_aeronave": data.get("categoria_financeira_aeronave"),
        "pos_exec_min": data.get("pos_exec_min"),
        "justificativa": data.get("justificativa"),
        "missao_status": data.get("status"),
        "status": "estimado",
    }
    return _serialize_hourly_calculation(row)


def _changed_fields(before: dict, data: dict) -> list[str]:
    return sorted(field for field, value in data.items() if field in before and before.get(field) != value)


_MISSION_CALCULATION_IMPACT_FIELDS = {
    "competencia",
    "data_missao",
    "data_final",
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
    "status",
}


def _participants_by_function(mission: dict) -> dict[str, dict]:
    participants = {}
    for participant in mission.get("participantes", []):
        funcao = _clean_text(participant.get("funcao")).lower()
        if funcao not in {"comandante", "copiloto"}:
            continue
        participants[funcao] = {**participant, "funcao": funcao}
    return participants


def _participant_from_mission_field(mission: dict, *, funcao: str, field: str) -> dict | None:
    tripulante_id = _optional_int(mission.get(field), label=funcao.capitalize())
    if tripulante_id is None:
        return None
    return {
        "mission_id": mission.get("id"),
        "missao_operacional_id": mission.get("id"),
        "tripulante_id": tripulante_id,
        "funcao": funcao,
        "status": "ativo",
    }


def _required_participants(mission: dict) -> list[dict]:
    participants = _participants_by_function(mission)
    fallback_fields = {
        "comandante": "comandante_tripulante_id",
        "copiloto": "copiloto_tripulante_id",
    }
    for funcao, field in fallback_fields.items():
        if participants.get(funcao):
            continue
        fallback = _participant_from_mission_field(mission, funcao=funcao, field=field)
        if fallback:
            participants[funcao] = fallback
    missing = [funcao for funcao in ("comandante", "copiloto") if not participants.get(funcao)]
    if missing:
        raise FinanceiroDominioErro(
            "Missao operacional deve possuir comandante e copiloto para recalc.",
            code="missao_operacional_tripulantes_obrigatorios",
        )
    return [participants["comandante"], participants["copiloto"]]


def _required_parameter_specs(funcao: str) -> tuple[tuple[str, str | None, str | None], ...]:
    return (
        ("duracao_hora_noturna_minutos", None, "minutos"),
        ("periodo_diurno_inicio", None, "minutos_do_dia"),
        ("periodo_diurno_fim", None, "minutos_do_dia"),
        ("adicional_noturno", funcao, "valor"),
        ("domingo_feriado_diurno", funcao, "valor"),
        ("domingo_feriado_noturno", funcao, "valor"),
    )


def _buscar_parametros_vigentes(db, *, mission: dict, funcao: str, org_id: str) -> list[dict]:
    vigencia_em = _clean_text(mission.get("data_missao"))[:10]
    parametros = []
    for tipo, funcao_parametro, unidade in _required_parameter_specs(funcao):
        rows = listar_parametros_financeiros_rows(
            db,
            org_id=org_id,
            tipo=tipo,
            status="ativo",
            vigencia_em=vigencia_em,
            funcao=funcao_parametro,
            unidade=unidade,
            limit=1000,
            offset=0,
        )
        parametros.extend(rows)
    return parametros


def _is_feriado_nacional(db, *, mission: dict, org_id: str) -> bool:
    data_missao = _clean_text(mission.get("data_missao"))[:10]
    row = verificar_feriado_nacional_por_data(db, data=data_missao, org_id=org_id, status="ativo")
    return bool(row)


def _effective_mission_date_range(mission: dict) -> tuple[str, str]:
    data_missao = _parse_date_value(mission.get("data_missao"), label="Data da missao operacional")
    data_final = _parse_date_value(mission.get("data_final") or data_missao, label="Data final da missao")
    try:
        start_dt = _parse_datetime_value(
            mission.get("horario_apresentacao"),
            base_date=data_missao,
            label="Horario de apresentacao",
        )
        end_dt = _parse_datetime_value(
            mission.get("horario_abandono"),
            base_date=data_missao,
            label="Horario de abandono",
        )
        if _clean_text(mission.get("horario_abandono")) and len(_clean_text(mission.get("horario_abandono"))) <= 5 and data_final > data_missao:
            end_dt = datetime.combine(data_final, end_dt.time())
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        data_final = max(data_final, end_dt.date())
    except DomainError:
        pass
    return data_missao.isoformat(), data_final.isoformat()


def _feriados_nacionais_da_missao(db, *, mission: dict, org_id: str) -> list[str]:
    data_inicio, data_fim = _effective_mission_date_range(mission)
    try:
        rows = listar_feriados_nacionais(
            db,
            org_id=org_id,
            status="ativo",
            data_inicio=data_inicio,
            data_fim=data_fim,
            limit=1000,
            offset=0,
        )
    except AttributeError:
        return [data_inicio] if _is_feriado_nacional(db, mission=mission, org_id=org_id) else []
    return [_clean_text(row.get("data"))[:10] for row in rows if _clean_text(row.get("data"))]


def validar_competencia_aberta_para_mutacao(db, *, competencia: str, org_id: str | None = None) -> None:
    resolved_org_id = _resolve_org_id(org_id)
    row = fetch_competencia_financeira(db, competencia=competencia, org_id=resolved_org_id)
    if row and _clean_text(row.get("status")).lower() == "fechada":
        raise CompetenciaFinanceiraFechadaErro(competencia)


def verificar_duplicidade_missao_operacional(
    payload: dict,
    *,
    org_id: str | None = None,
    exclude_id: int | None = None,
    db=None,
) -> dict | None:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    duplicate = find_duplicate_missao_operacional(
        resolved_db,
        org_id=resolved_org_id,
        cavok_numero_voo=payload.get("cavok_numero_voo"),
        contratante=payload.get("contratante"),
        chamado=payload.get("chamado"),
        exclude_id=exclude_id,
    )
    return serialize_finance_mission(duplicate) if duplicate else None


def _ensure_no_duplicate(db, *, data: dict, exclude_id: int | None = None) -> None:
    duplicate = find_duplicate_missao_operacional(
        db,
        org_id=data["org_id"],
        cavok_numero_voo=data.get("cavok_numero_voo"),
        contratante=data.get("contratante"),
        chamado=data.get("chamado"),
        exclude_id=exclude_id,
    )
    if duplicate:
        raise MissaoOperacionalDuplicadaErro()


def _audit_payload(mission: dict, *, event_name: str, actor_user_id: int, changed_fields: list[str] | None = None, reason: str | None = None) -> dict:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    return {
        "mission": mission,
        "audit_metadata": {
            "event_name": event_name,
            "org_id": mission.get("org_id"),
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": mission.get("id"),
            "permission": event["permission"],
            "competencia": mission.get("competencia"),
            "mission_id": mission.get("id"),
            "calculation_version": (
                mission.get("calculation_version")
                or (mission.get("calculos_horarios") or [{}])[0].get("calculation_version")
            ),
            "changed_fields": changed_fields or [],
            "reason": _clean_text(reason) or None,
        },
    }


def _record_finance_mission_audit(
    db,
    *,
    event_name: str,
    mission_id: int,
    actor_user_id: int,
    before: dict | None = None,
    after: dict | None = None,
    changed_fields: list[str] | None = None,
    reason: str | None = None,
) -> None:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=mission_id,
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior=(
            _audit_payload(before, event_name=event_name, actor_user_id=actor_user_id, changed_fields=changed_fields, reason=reason)
            if before
            else None
        ),
        payload_novo=(
            _audit_payload(after, event_name=event_name, actor_user_id=actor_user_id, changed_fields=changed_fields, reason=reason)
            if after
            else None
        ),
        observacao=f"org_id={after.get('org_id') if after else before.get('org_id')}; competencia={after.get('competencia') if after else before.get('competencia')}",
    )


def _calculation_audit_payload(calculation: dict, *, event_name: str, mission: dict, actor_user_id: int, reason: str | None = None) -> dict:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    return {
        "calculation": calculation,
        "audit_metadata": {
            "event_name": event_name,
            "org_id": mission.get("org_id"),
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": calculation.get("id"),
            "permission": event["permission"],
            "competencia": mission.get("competencia"),
            "mission_id": mission.get("id"),
            "tripulante_id": calculation.get("tripulante_id"),
            "funcao": calculation.get("funcao"),
            "calculation_version": calculation.get("calculation_version"),
            "reason": _clean_text(reason) or None,
        },
    }


def _record_finance_calculation_audit(
    db,
    *,
    event_name: str,
    mission: dict,
    calculation: dict,
    actor_user_id: int,
    before: dict | None = None,
    reason: str | None = None,
) -> None:
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=int(calculation.get("id") or 0),
        acao=event_name,
        realizado_por=actor_user_id,
        payload_anterior=(
            _calculation_audit_payload(before, event_name=event_name, mission=mission, actor_user_id=actor_user_id, reason=reason)
            if before
            else None
        ),
        payload_novo=_calculation_audit_payload(
            calculation,
            event_name=event_name,
            mission=mission,
            actor_user_id=actor_user_id,
            reason=reason,
        ),
        observacao=f"org_id={mission.get('org_id')}; competencia={mission.get('competencia')}; mission_id={mission.get('id')}",
    )


def _record_finance_calculation_failure_audit(
    db,
    *,
    mission: dict | None,
    missao_operacional_id: int,
    actor_user_id: int,
    error: Exception,
) -> None:
    event = FINANCE_AUDIT_EVENTS_BY_NAME["finance.calculation.failed"]
    payload = {
        "error": {
            "code": getattr(error, "code", "unexpected"),
            "message": getattr(error, "message", str(error)),
            "type": type(error).__name__,
        },
        "audit_metadata": {
            "event_name": "finance.calculation.failed",
            "org_id": mission.get("org_id") if mission else None,
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": missao_operacional_id,
            "permission": event["permission"],
            "competencia": mission.get("competencia") if mission else None,
            "mission_id": missao_operacional_id,
            "error_code": getattr(error, "code", "unexpected"),
        },
    }
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=int(missao_operacional_id),
        acao="finance.calculation.failed",
        realizado_por=actor_user_id,
        payload_novo=payload,
        observacao=f"mission_id={missao_operacional_id}; error_code={getattr(error, 'code', 'unexpected')}",
    )


def _record_finance_mission_cancel_failure_audit(
    db,
    *,
    mission: dict | None,
    missao_operacional_id: int,
    actor_user_id: int,
    error: Exception,
    reason: str | None = None,
) -> None:
    event_name = "finance.mission.cancel.failed"
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    payload = {
        "mission": mission,
        "error": {
            "code": getattr(error, "code", "unexpected"),
            "message": getattr(error, "message", str(error)),
            "type": type(error).__name__,
        },
        "audit_metadata": {
            "event_name": event_name,
            "org_id": mission.get("org_id") if mission else None,
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": missao_operacional_id,
            "permission": event["permission"],
            "competencia": mission.get("competencia") if mission else None,
            "mission_id": missao_operacional_id,
            "error_code": getattr(error, "code", "unexpected"),
            "reason": _clean_text(reason) or None,
        },
    }
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=int(missao_operacional_id),
        acao=event_name,
        realizado_por=actor_user_id,
        payload_novo=payload,
        observacao=f"mission_id={missao_operacional_id}; error_code={getattr(error, 'code', 'unexpected')}",
    )


def _record_finance_mission_delete_failure_audit(
    db,
    *,
    mission: dict | None,
    missao_operacional_id: int,
    actor_user_id: int,
    error: Exception,
    reason: str | None = None,
) -> None:
    event_name = "finance.mission.delete.failed"
    event = FINANCE_AUDIT_EVENTS_BY_NAME[event_name]
    payload = {
        "mission": mission,
        "error": {
            "code": getattr(error, "code", "unexpected"),
            "message": getattr(error, "message", str(error)),
            "type": type(error).__name__,
        },
        "audit_metadata": {
            "event_name": event_name,
            "org_id": mission.get("org_id") if mission else None,
            "actor_user_id": actor_user_id,
            "entity_type": event["entity_type"],
            "entity_id": missao_operacional_id,
            "permission": event["permission"],
            "competencia": mission.get("competencia") if mission else None,
            "mission_id": missao_operacional_id,
            "error_code": getattr(error, "code", "unexpected"),
            "reason": _clean_text(reason) or None,
        },
    }
    record_audit_event(
        db,
        entidade=event["entity_type"],
        entidade_id=int(missao_operacional_id),
        acao=event_name,
        realizado_por=actor_user_id,
        payload_novo=payload,
        observacao=f"mission_id={missao_operacional_id}; error_code={getattr(error, 'code', 'unexpected')}",
    )


def _calculation_key(calculation: dict) -> tuple[int | None, str]:
    return (_optional_int(calculation.get("tripulante_id"), label="Tripulante"), _clean_text(calculation.get("funcao")).lower())


def _total_calculations(calculations: list[dict]) -> str:
    total = sum((Decimal(str(item.get("total") or "0")) for item in calculations), Decimal("0"))
    return _decimal_text(total)


def _mission_missing_operational_times(mission: dict) -> bool:
    return not _clean_text(mission.get("horario_apresentacao")) or not _clean_text(mission.get("horario_abandono"))


def _missing_times_zero_warning() -> dict:
    return {
        "code": "finance_hourly_missing_times_zeroed",
        "message": (
            "Lancamento salvo sem horario de apresentacao ou abandono; "
            "calculo horario vigente foi zerado."
        ),
    }


def _zero_hourly_calculation_for_missing_times(
    mission: dict,
    participant: dict,
    *,
    org_id: str,
) -> dict:
    mission_id = _optional_int(mission.get("id"), label="Missao")
    tripulante_id = _optional_int(participant.get("tripulante_id"), label="Tripulante")
    funcao = _clean_text(participant.get("funcao")).lower()
    warning = _missing_times_zero_warning()
    memory = {
        "calculation_version": "finance-hourly-v1",
        "org_id": org_id,
        "competencia": _clean_text(mission.get("competencia")),
        "source": {"type": "finance_mission_operational", "id": mission_id},
        "participant": {
            "tripulante_id": tripulante_id,
            "funcao": funcao,
        },
        "inputs": {
            "data_missao": _clean_text(mission.get("data_missao")),
            "data_final": _clean_text(mission.get("data_final") or mission.get("data_missao")),
            "horario_apresentacao": _clean_text(mission.get("horario_apresentacao")),
            "horario_abandono": _clean_text(mission.get("horario_abandono")),
            "pos_exec_min": _optional_int(mission.get("pos_exec_min"), label="Pos execucao") or 0,
        },
        "steps": [
            {
                "rule_key": "jornada_sem_horarios",
                "rule_label": "Jornada sem horarios operacionais",
                "entrada_usada": {
                    "horario_apresentacao": _clean_text(mission.get("horario_apresentacao")),
                    "horario_abandono": _clean_text(mission.get("horario_abandono")),
                },
                "parametro_usado": None,
                "formula_conceitual": "horarios ausentes => calculo horario zerado",
                "resultado_intermediario": {
                    "jornada_total_minutos": 0,
                    "minutos_diurnos": 0,
                    "minutos_noturnos": 0,
                },
                "resultado_final": {
                    "total": "0.00",
                    "jornada_total_minutos": 0,
                },
                "notes": [
                    "Quando apresentacao ou abandono ficam em branco, a linha permanece calculada com valor zero."
                ],
            }
        ],
        "warnings": [warning],
    }
    return {
        "org_id": org_id,
        "missao_operacional_id": mission_id,
        "mission_id": mission_id,
        "tripulante_id": tripulante_id,
        "funcao": funcao,
        "jornada_total_minutos": 0,
        "minutos_diurnos": 0,
        "minutos_noturnos": 0,
        "minutos_noturnos_reais": 0,
        "horas_noturnas_convertidas": "0.0000",
        "minutos_pre": 0,
        "minutos_pos": 0,
        "domingo_feriado": False,
        "valor_adicional_noturno": "0.00",
        "valor_domingo_feriado_diurno": "0.00",
        "valor_domingo_feriado_noturno": "0.00",
        "valor_pre": "0.00",
        "valor_pos": "0.00",
        "total": "0.00",
        "memoria_calculo": memory,
        "parametros_usados": [],
        "calculation_version": "finance-hourly-v1",
        "status": "calculado",
    }


def _affected_calculation_payload(calculation: dict) -> dict:
    return {
        "id": calculation.get("id"),
        "mission_id": calculation.get("mission_id") or calculation.get("missao_operacional_id"),
        "tripulante_id": calculation.get("tripulante_id"),
        "funcao": calculation.get("funcao"),
        "status": calculation.get("status") or "calculado",
        "action": calculation.get("persistence_action") or "updated",
    }


def criar_missao_operacional(
    payload: dict,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
    require_times: bool = True,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    data = _mission_payload(payload, org_id=resolved_org_id, actor_user_id=actor_user_id, require_times=require_times)

    try:
        validar_competencia_aberta_para_mutacao(resolved_db, competencia=data["competencia"], org_id=resolved_org_id)
        _ensure_no_duplicate(resolved_db, data=data)
        created = create_missao_operacional_with_tripulantes(resolved_db, data=data, org_id=resolved_org_id)
        detail = fetch_missao_operacional_detail(resolved_db, missao_operacional_id=created["id"], org_id=resolved_org_id) or created
        serialized = _serialize_mission_detail(detail)
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.created",
            mission_id=created["id"],
            actor_user_id=actor_user_id,
            after=serialized,
        )
        resolved_db.commit()
        return serialized
    except DomainError:
        resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        raise DomainError(
            "Nao foi possivel criar a missao operacional.",
            status=500,
            code="missao_operacional_create_failed",
        ) from exc


def listar_missoes_operacionais(
    *,
    competencia: str,
    org_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    rows = list_missoes_operacionais_rows(
        resolved_db,
        competencia=competencia,
        org_id=resolved_org_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return serialize_finance_mission_collection(items=rows, page=page, offset=offset, total=len(rows))


def detalhar_missao_operacional(missao_operacional_id: int, *, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    detail = fetch_missao_operacional_detail(resolved_db, missao_operacional_id=missao_operacional_id, org_id=resolved_org_id)
    if not detail:
        raise MissaoOperacionalNaoEncontradaErro()
    return _serialize_mission_detail(detail)


def preview_missao_operacional(payload: dict, *, org_id: str | None = None, db=None) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    missing_fields = _preview_missing_fields(payload)
    if missing_fields:
        return _preview_pending_payload(payload, missing_fields)

    try:
        data = _mission_payload(payload, org_id=resolved_org_id, actor_user_id=None, require_times=False)
        data["id"] = _optional_int(payload.get("id"), label="Missao") if payload.get("id") not in (None, "") else None
        participantes = _required_participants(data)
        if _mission_missing_operational_times(data):
            raw_calculations = [
                _zero_hourly_calculation_for_missing_times(
                    data,
                    participante,
                    org_id=resolved_org_id,
                )
                for participante in participantes
            ]
            calculations = [
                _preview_calculation_row(calculation, data=data, org_id=resolved_org_id)
                for calculation in raw_calculations
            ]
            warning = _missing_times_zero_warning()
            return {
                "status": "disponivel",
                "estado_calculo": "estimado",
                "base_calculo": "Bonificacao horaria operacional",
                "campos_faltantes": [],
                "pendencias": [],
                "inconsistencias": [],
                "warnings": [warning],
                "horas_consideradas": _preview_hours_summary(raw_calculations),
                "tripulantes_considerados": [
                    {"tripulante_id": item["tripulante_id"], "funcao": item["funcao"]}
                    for item in participantes
                ],
                "valor_estimado": "0.00",
                "calculations": calculations,
                "observacoes": [
                    "Estimativa operacional zerada porque apresentacao ou abandono nao foram informados.",
                    "O backend continua sendo a fonte de verdade ao salvar ou recalcular.",
                ],
                "generated_at": _preview_now(),
                "input_ref": {
                    "competencia": data.get("competencia"),
                    "data_missao": data.get("data_missao"),
                    "status": data.get("status"),
                    "categoria_financeira_aeronave": data.get("categoria_financeira_aeronave"),
                },
            }
        feriados = _feriados_nacionais_da_missao(resolved_db, mission=data, org_id=resolved_org_id)
        calculations = []
        raw_calculations = []
        for participante in participantes:
            parametros = _buscar_parametros_vigentes(
                resolved_db,
                mission=data,
                funcao=participante["funcao"],
                org_id=resolved_org_id,
            )
            calculation = calcular_bonificacao_horaria(
                missao_operacional=data,
                participante={
                    "mission_id": data.get("id"),
                    "tripulante_id": participante["tripulante_id"],
                    "funcao": participante["funcao"],
                },
                parametros_vigentes=parametros,
                feriados=feriados,
            )
            raw_calculations.append(calculation)
            calculations.append(_preview_calculation_row(calculation, data=data, org_id=resolved_org_id))

        total = sum((Decimal(str(item.get("total") or "0")) for item in raw_calculations), Decimal("0"))
        return {
            "status": "disponivel",
            "estado_calculo": "estimado",
            "base_calculo": "Bonificacao horaria operacional",
            "campos_faltantes": [],
            "pendencias": [],
            "inconsistencias": [],
            "horas_consideradas": _preview_hours_summary(raw_calculations),
            "tripulantes_considerados": [
                {"tripulante_id": item["tripulante_id"], "funcao": item["funcao"]}
                for item in participantes
            ],
            "valor_estimado": _decimal_text(total),
            "calculations": calculations,
            "observacoes": [
                "Estimativa operacional calculada sem persistencia.",
                "O backend continua sendo a fonte de verdade ao salvar ou recalcular.",
            ],
            "generated_at": _preview_now(),
            "input_ref": {
                "competencia": data.get("competencia"),
                "data_missao": data.get("data_missao"),
                "status": data.get("status"),
                "categoria_financeira_aeronave": data.get("categoria_financeira_aeronave"),
            },
        }
    except DomainError as exc:
        return {
            "status": "bloqueada",
            "estado_calculo": "bloqueado",
            "base_calculo": "Bonificacao horaria operacional",
            "campos_faltantes": [],
            "pendencias": [],
            "inconsistencias": [_preview_issue_from_error(exc)],
            "horas_consideradas": {},
            "tripulantes_considerados": [],
            "valor_estimado": None,
            "calculations": [],
            "observacoes": [
                "A previa foi bloqueada por inconsistencias nos dados ou parametros financeiros.",
                "Nenhum dado foi persistido.",
            ],
            "generated_at": _preview_now(),
            "input_ref": {
                "competencia": _clean_text(payload.get("competencia")),
                "data_missao": _clean_text(payload.get("data_missao")),
                "status": _clean_text(payload.get("status")) or "rascunho",
            },
        }


def atualizar_missao_operacional(
    missao_operacional_id: int,
    payload: dict,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
    require_times: bool = True,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id or payload.get("org_id"))
    before_row = fetch_missao_operacional(resolved_db, missao_operacional_id=missao_operacional_id, org_id=resolved_org_id)
    if not before_row:
        raise MissaoOperacionalNaoEncontradaErro()

    data = dict(payload)
    data["org_id"] = resolved_org_id
    if "data_missao" in data or "data_final" in data:
        data_missao_raw = data.get("data_missao") or before_row["data_missao"]
        data_final_raw = data.get("data_final") or before_row.get("data_final") or data_missao_raw
        data_missao_date = _parse_date_value(data_missao_raw, label="Data da missao operacional")
        data_final_date = _parse_date_value(data_final_raw, label="Data final da missao")
        if data_final_date < data_missao_date:
            raise FinanceiroDominioErro(
                "Data final da missao nao pode ser anterior a data inicial.",
                code="missao_operacional_data_final_invalida",
            )
        data["data_final"] = data_final_date.isoformat()
    _normalize_update_times(data, before_row, require_times=require_times)
    if "pos_exec_min" in data:
        data["pos_exec_min"] = _normalize_non_negative_int(data.get("pos_exec_min"), label="Pos execucao em minutos")
    if "quantidade_pernoites" in data or "cobertura_base" in data or "houve_pernoite" in data:
        quantidade_pernoites = _normalize_non_negative_int(
            data.get("quantidade_pernoites", before_row.get("quantidade_pernoites")),
            label="Quantidade de pernoites",
        )
        data["quantidade_pernoites"] = quantidade_pernoites
        data["houve_pernoite"] = quantidade_pernoites > 0 and _bool_value(data.get("houve_pernoite", True))
        data["cobertura_base"] = quantidade_pernoites > 0 and _bool_value(data.get("cobertura_base", before_row.get("cobertura_base")))
    if "operacao_especial" in data:
        data["operacao_especial"] = _special_operation_text(data.get("operacao_especial"))
    if "justificativa" in data:
        data["justificativa"] = _clean_text(data.get("justificativa")) or None
    if "observacoes" in data:
        data["observacoes"] = _clean_text(data.get("observacoes")) or None
    if "comandante_tripulante_id" in data or "copiloto_tripulante_id" in data:
        comandante_id = int(data.get("comandante_tripulante_id") or before_row["comandante_tripulante_id"])
        copiloto_id = int(data.get("copiloto_tripulante_id") or before_row["copiloto_tripulante_id"])
        if comandante_id == copiloto_id:
            raise FinanceiroDominioErro(
                "Comandante e copiloto devem ser tripulantes distintos.",
                code="missao_operacional_tripulantes_iguais",
            )

    target_competencia = _clean_text(data.get("competencia")) or before_row["competencia"]
    data["updated_by"] = actor_user_id
    duplicate_data = {**dict(before_row), **data, "competencia": target_competencia, "org_id": resolved_org_id}

    try:
        validar_competencia_aberta_para_mutacao(
            resolved_db,
            competencia=before_row["competencia"],
            org_id=resolved_org_id,
        )
        if target_competencia != before_row["competencia"]:
            validar_competencia_aberta_para_mutacao(resolved_db, competencia=target_competencia, org_id=resolved_org_id)
        _ensure_no_duplicate(resolved_db, data=duplicate_data, exclude_id=missao_operacional_id)
        crew_changed = (
            ("comandante_tripulante_id" in data and int(data["comandante_tripulante_id"]) != int(before_row["comandante_tripulante_id"]))
            or ("copiloto_tripulante_id" in data and int(data["copiloto_tripulante_id"]) != int(before_row["copiloto_tripulante_id"]))
        )
        updated = update_missao_operacional_row(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            data=data,
            org_id=resolved_org_id,
        )
        if not updated:
            raise MissaoOperacionalNaoEncontradaErro()
        if crew_changed:
            replace_missao_tripulantes(
                resolved_db,
                missao_operacional_id=missao_operacional_id,
                comandante_tripulante_id=int(updated["comandante_tripulante_id"]),
                copiloto_tripulante_id=int(updated["copiloto_tripulante_id"]),
                org_id=resolved_org_id,
            )
        detail = fetch_missao_operacional_detail(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        ) or updated
        before = serialize_finance_mission(before_row)
        after = _serialize_mission_detail(detail)
        changed = _changed_fields(dict(before_row), data)
        invalidated_calculations = []
        invalidated_productivity = []
        if any(field in _MISSION_CALCULATION_IMPACT_FIELDS for field in changed):
            invalidated_calculations = invalidar_calculos_horarios_vigentes_da_missao(
                resolved_db,
                missao_operacional_id=missao_operacional_id,
                org_id=resolved_org_id,
            )
            for calculation in invalidated_calculations:
                _record_finance_calculation_audit(
                    resolved_db,
                    event_name="finance.calculation.superseded",
                    mission=after,
                    calculation=calculation,
                    actor_user_id=actor_user_id,
                    before={**calculation, "status": calculation.get("previous_status") or "calculado"},
                    reason="missao operacional alterada; relatorio fica pendente ate novo recalculo",
                )
            impacted_competences = {
                value
                for value in (before_row.get("competencia"), updated.get("competencia"))
                if value
            }
            for impacted_competence in impacted_competences:
                invalidated_productivity.extend(
                    invalidar_calculos_produtividade_vigentes_da_competencia(
                        resolved_db,
                        competencia=impacted_competence,
                        org_id=resolved_org_id,
                    )
                )
            for calculation in invalidated_productivity:
                _record_finance_calculation_audit(
                    resolved_db,
                    event_name="finance.calculation.superseded",
                    mission=after,
                    calculation=calculation,
                    actor_user_id=actor_user_id,
                    before={**calculation, "status": calculation.get("previous_status") or "calculado"},
                    reason="produtividade da competencia invalidada por alteracao de missao operacional",
                )
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.updated",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            changed_fields=(
                changed
                + (["calculos_horarios"] if invalidated_calculations else [])
                + (["calculos_produtividade"] if invalidated_productivity else [])
            ),
            reason=payload.get("motivo") or payload.get("reason"),
        )
        resolved_db.commit()
        return after
    except DomainError:
        resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        raise DomainError(
            "Nao foi possivel atualizar a missao operacional.",
            status=500,
            code="missao_operacional_update_failed",
        ) from exc


def cancelar_missao_operacional(
    missao_operacional_id: int,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    motivo: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    before_row = fetch_missao_operacional(resolved_db, missao_operacional_id=missao_operacional_id, org_id=resolved_org_id)
    if not before_row:
        raise MissaoOperacionalNaoEncontradaErro()
    mission_for_failure = serialize_finance_mission(before_row)

    try:
        locked = lock_missao_operacional(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        if not locked:
            raise MissaoOperacionalNaoEncontradaErro()
        before_row = locked
        mission_for_failure = serialize_finance_mission(before_row)
        if _clean_text(before_row.get("status")).lower() == "cancelada":
            detail = fetch_missao_operacional_detail(
                resolved_db,
                missao_operacional_id=missao_operacional_id,
                org_id=resolved_org_id,
            ) or before_row
            after = _serialize_mission_detail(detail)
            resolved_db.commit()
            return {
                "mission": after,
                "mission_id": missao_operacional_id,
                "competence": after.get("competencia"),
                "calculation_status": "cancelada",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "affected_calculations": [],
                "warnings": [
                    {
                        "code": "finance_mission_already_cancelled",
                        "message": "Missao operacional ja estava cancelada; nenhuma alteracao adicional foi aplicada.",
                    }
                ],
                "errors": [],
                "current_result": {"status": "cancelada", "calculations": []},
                "audit_event_id": None,
                "action": "already_cancelled",
            }

        validar_competencia_aberta_para_mutacao(
            resolved_db,
            competencia=before_row["competencia"],
            org_id=resolved_org_id,
        )
        before = serialize_finance_mission(before_row)
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.cancel.requested",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=before,
            changed_fields=["status", "calculos_horarios", "calculos_produtividade"],
            reason=motivo or "solicitacao de cancelamento de missao operacional",
        )
        cancelled = cancel_missao_operacional_row(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
            updated_by=actor_user_id,
        )
        if not cancelled:
            raise MissaoOperacionalNaoEncontradaErro()
        cancel_missao_tripulantes(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        invalidated_calculations = invalidar_calculos_horarios_vigentes_da_missao(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        invalidated_productivity = invalidar_calculos_produtividade_vigentes_da_competencia(
            resolved_db,
            competencia=before_row["competencia"],
            org_id=resolved_org_id,
        )
        detail = fetch_missao_operacional_detail(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        ) or cancelled
        after = _serialize_mission_detail(detail)
        affected_calculations = []
        for invalidated in invalidated_calculations:
            previous_status = invalidated.pop("previous_status", None)
            calculation = {**invalidated, "persistence_action": "invalidated"}
            affected_calculations.append(_affected_calculation_payload(calculation))
            _record_finance_calculation_audit(
                resolved_db,
                event_name="finance.calculation.invalidated_by_mission_cancel",
                mission={**before_row, "id": missao_operacional_id},
                calculation=calculation,
                actor_user_id=actor_user_id,
                before={**calculation, "status": previous_status or "calculado"},
                reason=motivo or "cancelamento de missao operacional invalidou calculo vigente",
            )
        for invalidated in invalidated_productivity:
            previous_status = invalidated.pop("previous_status", None)
            calculation = {**invalidated, "persistence_action": "invalidated"}
            affected_calculations.append(_affected_calculation_payload(calculation))
            _record_finance_calculation_audit(
                resolved_db,
                event_name="finance.calculation.invalidated_by_mission_cancel",
                mission={**before_row, "id": missao_operacional_id},
                calculation=calculation,
                actor_user_id=actor_user_id,
                before={**calculation, "status": previous_status or "calculado"},
                reason=motivo or "cancelamento de missao operacional invalidou produtividade vigente",
            )
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.cancelled",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            changed_fields=["status", "participantes", "calculos_horarios", "calculos_produtividade"],
            reason=motivo,
        )
        resolved_db.commit()
        warnings = []
        if invalidated_calculations:
            warnings.append(
                {
                    "code": "finance_calculation_invalidated_by_mission_cancel",
                    "message": (
                        f"{len(invalidated_calculations)} calculo(s) horario(s) vigente(s) "
                        "foram marcados como obsoletos pelo cancelamento da missao."
                    ),
                }
            )
        if invalidated_productivity:
            warnings.append(
                {
                    "code": "finance_productivity_invalidated_by_mission_cancel",
                    "message": (
                        f"{len(invalidated_productivity)} calculo(s) de produtividade vigente(s) "
                        "foram marcados como obsoletos pelo cancelamento da missao."
                    ),
                }
            )
        return {
            "mission": after,
            "mission_id": missao_operacional_id,
            "competence": after.get("competencia"),
            "calculation_status": "cancelada",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "affected_calculations": affected_calculations,
            "warnings": warnings,
            "errors": [],
            "current_result": {"status": "cancelada", "calculations": []},
            "audit_event_id": None,
            "action": "cancelled",
        }
    except DomainError as exc:
        resolved_db.conn.rollback()
        try:
            _record_finance_mission_cancel_failure_audit(
                resolved_db,
                mission=mission_for_failure,
                missao_operacional_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                error=exc,
                reason=motivo,
            )
            resolved_db.commit()
        except Exception:
            resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        failure = DomainError(
            "Nao foi possivel cancelar a missao operacional.",
            status=500,
            code="missao_operacional_cancel_failed",
        )
        try:
            _record_finance_mission_cancel_failure_audit(
                resolved_db,
                mission=mission_for_failure,
                missao_operacional_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                error=failure,
                reason=motivo,
            )
            resolved_db.commit()
        except Exception:
            resolved_db.conn.rollback()
        raise failure from exc


def _delete_dependency_total(summary: dict) -> int:
    return sum(int(summary.get(key) or 0) for key in ("calculos_horarios", "calculos_produtividade", "divergencias"))


def _delete_blocked_error(summary: dict, *, status: str | None = None) -> MissaoOperacionalExclusaoBloqueadaErro:
    details = {
        "dependencies": {
            "calculos_horarios": int(summary.get("calculos_horarios") or 0),
            "calculos_produtividade": int(summary.get("calculos_produtividade") or 0),
            "divergencias": int(summary.get("divergencias") or 0),
        },
        "recommended_action": "cancel_mission",
    }
    if status:
        details["status"] = status
    if status == "cancelada":
        return MissaoOperacionalExclusaoBloqueadaErro(
            "Esta missao ja foi cancelada por processo financeiro. Para preservar a rastreabilidade, mantenha o registro cancelado.",
            details=details,
        )
    return MissaoOperacionalExclusaoBloqueadaErro(details=details)


def excluir_missao_operacional(
    missao_operacional_id: int,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    motivo: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    before_row = fetch_missao_operacional(
        resolved_db,
        missao_operacional_id=missao_operacional_id,
        org_id=resolved_org_id,
        include_deleted=True,
    )
    if not before_row:
        raise MissaoOperacionalNaoEncontradaErro()
    mission_for_failure = serialize_finance_mission(before_row)
    if before_row.get("deleted_at"):
        detail = fetch_missao_operacional_detail(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
            include_deleted=True,
        ) or before_row
        mission = _serialize_mission_detail(detail)
        resolved_db.commit()
        return {
            "mission": mission,
            "mission_id": missao_operacional_id,
            "competence": mission.get("competencia"),
            "deleted": True,
            "deleted_at": mission.get("deleted_at"),
            "affected_dependencies": {"participantes": 0, "calculos_horarios": 0, "calculos_produtividade": 0, "divergencias": 0},
            "warnings": [
                {
                    "code": "finance_mission_already_deleted",
                    "message": "Missao operacional ja estava excluida; nenhuma alteracao adicional foi aplicada.",
                }
            ],
            "errors": [],
            "current_result": {"status": "excluida", "active": False},
            "audit_event_id": None,
            "action": "already_deleted",
        }

    try:
        locked = lock_missao_operacional(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
            include_deleted=True,
        )
        if not locked:
            raise MissaoOperacionalNaoEncontradaErro()
        before_row = locked
        mission_for_failure = serialize_finance_mission(before_row)
        if before_row.get("deleted_at"):
            detail = fetch_missao_operacional_detail(
                resolved_db,
                missao_operacional_id=missao_operacional_id,
                org_id=resolved_org_id,
                include_deleted=True,
            ) or before_row
            mission = _serialize_mission_detail(detail)
            resolved_db.commit()
            return {
                "mission": mission,
                "mission_id": missao_operacional_id,
                "competence": mission.get("competencia"),
                "deleted": True,
                "deleted_at": mission.get("deleted_at"),
                "affected_dependencies": {"participantes": 0, "calculos_horarios": 0, "calculos_produtividade": 0, "divergencias": 0},
                "warnings": [
                    {
                        "code": "finance_mission_already_deleted",
                        "message": "Missao operacional ja estava excluida; nenhuma alteracao adicional foi aplicada.",
                    }
                ],
                "errors": [],
                "current_result": {"status": "excluida", "active": False},
                "audit_event_id": None,
                "action": "already_deleted",
            }

        validar_competencia_aberta_para_mutacao(
            resolved_db,
            competencia=before_row["competencia"],
            org_id=resolved_org_id,
        )
        detail_before = fetch_missao_operacional_detail(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        ) or before_row
        before = _serialize_mission_detail(detail_before)
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.delete.requested",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=before,
            changed_fields=["deleted_at", "participantes"],
            reason=motivo or "solicitacao de exclusao definitiva de missao operacional",
        )

        dependency_summary = mission_delete_dependency_summary(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            competencia=before_row["competencia"],
            org_id=resolved_org_id,
        )
        status = _clean_text(before_row.get("status")).lower()
        blocked_error = None
        if status == "cancelada":
            blocked_error = _delete_blocked_error(dependency_summary, status=status)
        elif _delete_dependency_total(dependency_summary) > 0:
            blocked_error = _delete_blocked_error(dependency_summary, status=status)
        if blocked_error:
            _record_finance_mission_audit(
                resolved_db,
                event_name="finance.mission.delete.blocked",
                mission_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                before=before,
                changed_fields=[],
                reason=motivo or blocked_error.message,
            )
            resolved_db.commit()
            raise blocked_error

        removed_participants = remover_missao_tripulantes(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        deleted = soft_delete_missao_operacional(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
            deleted_by=actor_user_id,
            delete_reason=_clean_text(motivo) or "exclusao solicitada pela tela financeira",
        )
        if not deleted:
            raise MissaoOperacionalNaoEncontradaErro()
        detail_after = fetch_missao_operacional_detail(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
            include_deleted=True,
        ) or deleted
        after = _serialize_mission_detail(detail_after)
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.deleted",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            changed_fields=["deleted_at", "deleted_by", "delete_reason", "participantes"],
            reason=motivo,
        )
        resolved_db.commit()
        return {
            "mission": after,
            "mission_id": missao_operacional_id,
            "competence": after.get("competencia"),
            "deleted": True,
            "deleted_at": after.get("deleted_at"),
            "affected_dependencies": {
                "participantes": len(removed_participants),
                "calculos_horarios": 0,
                "calculos_produtividade": 0,
                "divergencias": 0,
            },
            "warnings": [],
            "errors": [],
            "current_result": {"status": "excluida", "active": False},
            "audit_event_id": None,
            "action": "deleted",
        }
    except MissaoOperacionalExclusaoBloqueadaErro:
        raise
    except DomainError as exc:
        resolved_db.conn.rollback()
        try:
            _record_finance_mission_delete_failure_audit(
                resolved_db,
                mission=mission_for_failure,
                missao_operacional_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                error=exc,
                reason=motivo,
            )
            resolved_db.commit()
        except Exception:
            resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        failure = DomainError(
            "Nao foi possivel excluir a missao operacional.",
            status=500,
            code="missao_operacional_delete_failed",
        )
        try:
            _record_finance_mission_delete_failure_audit(
                resolved_db,
                mission=mission_for_failure,
                missao_operacional_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                error=failure,
                reason=motivo,
            )
            resolved_db.commit()
        except Exception:
            resolved_db.conn.rollback()
        raise failure from exc


def recalcular_missao_operacional(
    missao_operacional_id: int,
    *,
    actor_user_id: int,
    org_id: str | None = None,
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    mission = fetch_missao_operacional_detail(
        resolved_db,
        missao_operacional_id=missao_operacional_id,
        org_id=resolved_org_id,
    )
    if not mission:
        raise MissaoOperacionalNaoEncontradaErro()
    if _clean_text(mission.get("status")).lower() == "cancelada":
        raise MissaoOperacionalCanceladaErro()

    try:
        locked = lock_missao_operacional(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        if not locked:
            raise MissaoOperacionalNaoEncontradaErro()
        mission = fetch_missao_operacional_detail(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        ) or {**mission, **locked}
        if _clean_text(mission.get("status")).lower() == "cancelada":
            raise MissaoOperacionalCanceladaErro()
        validar_competencia_aberta_para_mutacao(
            resolved_db,
            competencia=mission["competencia"],
            org_id=resolved_org_id,
        )
        serialized_mission = _serialize_mission_detail(mission)
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.recalculation.requested",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=serialized_mission,
            changed_fields=["calculos_horarios"],
            reason="solicitacao de recalculo de missao operacional",
        )
        superseded_duplicates = obsoletar_calculos_vigentes_duplicados_da_missao(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        for superseded in superseded_duplicates:
            _record_finance_calculation_audit(
                resolved_db,
                event_name="finance.calculation.superseded",
                mission=mission,
                calculation=superseded,
                actor_user_id=actor_user_id,
                before={**superseded, "status": "calculado"},
                reason="duplicidade vigente regularizada antes do recalculo",
            )

        current_before = listar_calculos_horarios_vigentes_da_missao(
            resolved_db,
            missao_operacional_id=missao_operacional_id,
            org_id=resolved_org_id,
        )
        before_by_key = {_calculation_key(row): row for row in current_before}
        participantes = _required_participants(mission)
        missing_operational_times = _mission_missing_operational_times(mission)
        warnings = []
        if missing_operational_times:
            warnings.append(_missing_times_zero_warning())
        feriados = (
            []
            if missing_operational_times
            else _feriados_nacionais_da_missao(resolved_db, mission=mission, org_id=resolved_org_id)
        )
        saved_calculations = []
        affected_calculations = []
        for participante in participantes:
            if missing_operational_times:
                calculation = _zero_hourly_calculation_for_missing_times(
                    mission,
                    participante,
                    org_id=resolved_org_id,
                )
            else:
                parametros = _buscar_parametros_vigentes(
                    resolved_db,
                    mission=mission,
                    funcao=participante["funcao"],
                    org_id=resolved_org_id,
                )
                calculation = calcular_bonificacao_horaria(
                    missao_operacional=mission,
                    participante={
                        "mission_id": missao_operacional_id,
                        "tripulante_id": participante["tripulante_id"],
                        "funcao": participante["funcao"],
                    },
                    parametros_vigentes=parametros,
                    feriados=feriados,
                )
                calculation["org_id"] = resolved_org_id
                calculation["missao_operacional_id"] = missao_operacional_id
            saved = salvar_ou_atualizar_calculo_horario_vigente(
                resolved_db,
                data=calculation,
                org_id=resolved_org_id,
            )
            saved["minutos_noturnos_reais"] = saved.get("minutos_noturnos_reais") or saved.get("minutos_noturnos")
            serialized_calculation = _serialize_hourly_calculation(saved)
            saved_calculations.append(serialized_calculation)
            affected_calculations.append(_affected_calculation_payload(saved))
            before = before_by_key.get(_calculation_key(saved))
            _record_finance_calculation_audit(
                resolved_db,
                event_name="finance.calculation.updated" if before else "finance.hourly_bonus.calculated",
                mission=mission,
                calculation=saved,
                actor_user_id=actor_user_id,
                before=before,
                reason="recalculo idempotente de missao operacional",
            )

        after = {
            **serialized_mission,
            "calculos_horarios": saved_calculations,
        }
        _record_finance_mission_audit(
            resolved_db,
            event_name="finance.mission.recalculated",
            mission_id=missao_operacional_id,
            actor_user_id=actor_user_id,
            before=serialized_mission,
            after=after,
            changed_fields=["calculos_horarios"],
            reason="recalculo de bonificacao horaria",
        )
        resolved_db.commit()
        recalculated_at = datetime.now(timezone.utc).isoformat()
        if superseded_duplicates:
            warnings.append(
                {
                    "code": "finance_calculation_duplicates_superseded",
                    "message": (
                        f"{len(superseded_duplicates)} calculo(s) vigente(s) duplicado(s) "
                        "foram marcados como obsoletos antes do recalculo."
                    ),
                }
            )
        return {
            "mission": serialized_mission,
            "calculations": saved_calculations,
            "mission_id": missao_operacional_id,
            "competence": mission["competencia"],
            "calculation_status": "calculado",
            "recalculated_at": recalculated_at,
            "affected_calculations": affected_calculations,
            "warnings": warnings,
            "errors": [],
            "current_result": {
                "total": _total_calculations(saved_calculations),
                "calculations": saved_calculations,
            },
            "audit_event_id": None,
        }
    except DomainError as exc:
        resolved_db.conn.rollback()
        try:
            _record_finance_calculation_failure_audit(
                resolved_db,
                mission=mission,
                missao_operacional_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                error=exc,
            )
            resolved_db.commit()
        except Exception:
            resolved_db.conn.rollback()
        raise
    except Exception as exc:
        resolved_db.conn.rollback()
        failure = DomainError(
            "Nao foi possivel recalcular a missao operacional.",
            status=500,
            code="missao_operacional_recalculate_failed",
        )
        try:
            _record_finance_calculation_failure_audit(
                resolved_db,
                mission=mission,
                missao_operacional_id=missao_operacional_id,
                actor_user_id=actor_user_id,
                error=failure,
            )
            resolved_db.commit()
        except Exception:
            resolved_db.conn.rollback()
        raise failure from exc
