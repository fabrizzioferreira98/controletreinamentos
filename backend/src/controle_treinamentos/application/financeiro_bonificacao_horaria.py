from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from ..contracts.financeiro import FINANCE_CREW_FUNCTIONS, FINANCE_ORG_SCOPE_DEFAULT
from ..core.domain_errors import DomainValidationError
from .financeiro_governanca_parametros import (
    classificacao_governanca_parametro,
    detectar_divergencias_ativas,
    detectar_sobreposicoes_ativas,
    parametro_elegivel_fechamento_real,
)

CALCULATION_VERSION = "finance-hourly-v1"
STANDARD_HOUR_MINUTES = Decimal("60")
DUTY_LIMIT_MINUTES = 630
MONEY_QUANTIZER = Decimal("0.01")
NIGHT_HOUR_QUANTIZER = Decimal("0.0001")
MONETARY_PARAMETER_UNIT = "valor"
NIGHT_DURATION_UNIT = "minutos"
DAY_PERIOD_UNIT = "minutos_do_dia"

REQUIRED_PARAMETER_TYPES = (
    "duracao_hora_noturna_minutos",
    "periodo_diurno_inicio",
    "periodo_diurno_fim",
    "adicional_noturno",
    "domingo_feriado_diurno",
    "domingo_feriado_noturno",
)

HOURLY_PARAMETER_RULES: dict[str, dict[str, Any]] = {
    "duracao_hora_noturna_minutos": {
        "unidade": NIGHT_DURATION_UNIT,
        "funcao_mode": "none",
        "categorias": {None},
    },
    "periodo_diurno_inicio": {
        "unidade": DAY_PERIOD_UNIT,
        "funcao_mode": "none",
        "categorias": {None},
    },
    "periodo_diurno_fim": {
        "unidade": DAY_PERIOD_UNIT,
        "funcao_mode": "none",
        "categorias": {None},
    },
    "adicional_noturno": {
        "unidade": MONETARY_PARAMETER_UNIT,
        "funcao_mode": "crew",
        "categorias": {None},
    },
    "domingo_feriado_diurno": {
        "unidade": MONETARY_PARAMETER_UNIT,
        "funcao_mode": "crew",
        "categorias": {None},
    },
    "domingo_feriado_noturno": {
        "unidade": MONETARY_PARAMETER_UNIT,
        "funcao_mode": "crew",
        "categorias": {None},
    },
}


class BonificacaoHorariaInvalidaErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "bonificacao_horaria_invalida"):
        super().__init__(message, code=code, status=400)


class ParametroBonificacaoHorariaAusenteErro(BonificacaoHorariaInvalidaErro):
    def __init__(self, tipo: str, *, funcao: str | None = None):
        suffix = f" para {funcao}" if funcao else ""
        super().__init__(
            f"Parametro financeiro obrigatorio ausente: {tipo}{suffix}.",
            code="bonificacao_horaria_parametro_ausente",
        )


class ParametroBonificacaoHorariaAmbiguoErro(BonificacaoHorariaInvalidaErro):
    def __init__(self, tipo: str, *, funcao: str | None = None, unidade: str | None = None):
        suffix_parts = []
        if funcao:
            suffix_parts.append(f"funcao={funcao}")
        if unidade:
            suffix_parts.append(f"unidade={unidade}")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        super().__init__(
            f"Parametro financeiro ambiguo para bonificacao horaria: {tipo}{suffix}.",
            code="bonificacao_horaria_parametro_ambiguo",
        )


class ParametroBonificacaoHorariaNaoElegivelErro(BonificacaoHorariaInvalidaErro):
    def __init__(self, *, blocking_parameters: list[dict], real_closure: bool):
        context = "fechamento real" if real_closure else "calculo horario"
        super().__init__(
            f"Motor de bonificacao horaria bloqueado: parametros nao elegiveis recebidos para {context}.",
            code="bonificacao_horaria_parametro_nao_elegivel",
        )
        self.details = {
            "real_closure": bool(real_closure),
            "blocking_parameters": blocking_parameters,
            "next_action": (
                "Corrigir cadastro de parametros (unidade, vigencia, classificacao, overlap/divergencia, BRL/QA) "
                "antes de recalcular."
            ),
        }


def calcular_bonificacao_horaria(
    *,
    missao_operacional: dict[str, Any],
    participante: dict[str, Any],
    parametros_vigentes: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    domingo_feriado: bool = False,
    feriado: bool = False,
    feriados: list[Any] | tuple[Any, ...] | set[Any] | None = None,
    real_closure: bool = False,
    release_environment: str = "hml",
    calculation_version: str = CALCULATION_VERSION,
) -> dict[str, Any]:
    """Calcula bonificacao horaria sem acessar Flask, banco, repository ou audit log."""
    funcao = _resolve_funcao(participante)
    tripulante_id = _resolve_int(participante.get("tripulante_id"))
    data_missao = _parse_date(missao_operacional.get("data_missao"))
    data_final = _parse_optional_date(missao_operacional.get("data_final")) or data_missao
    if data_final < data_missao:
        raise BonificacaoHorariaInvalidaErro(
            "Data final da missao nao pode ser anterior a data inicial.",
            code="bonificacao_horaria_data_final_invalida",
        )
    parametros_pool = _normalize_parameter_pool(parametros_vigentes)
    _validate_parameter_pool(
        parametros_pool,
        reference_date=data_missao,
        supported_types=REQUIRED_PARAMETER_TYPES,
        real_closure=real_closure,
        release_environment=release_environment,
    )
    horario_apresentacao, horario_abandono = _resolve_journey_interval(
        missao_operacional,
        data_missao=data_missao,
        data_final=data_final,
    )

    jornada_total_minutos = _minutes_between(horario_apresentacao, horario_abandono)
    if jornada_total_minutos <= 0:
        raise BonificacaoHorariaInvalidaErro(
            "Horario de abandono deve ser posterior ao horario de apresentacao.",
            code="bonificacao_horaria_jornada_invalida",
        )

    parametros = _resolve_required_parameters(parametros_pool, funcao=funcao)
    duracao_hora_noturna = _parameter_decimal(parametros["duracao_hora_noturna_minutos"])
    if duracao_hora_noturna <= 0:
        raise BonificacaoHorariaInvalidaErro(
            "Duracao da hora noturna deve ser maior que zero.",
            code="bonificacao_horaria_duracao_noturna_invalida",
        )
    periodo_diurno_inicio = _parameter_time(parametros["periodo_diurno_inicio"])
    periodo_diurno_fim = _parameter_time(parametros["periodo_diurno_fim"])

    feriados_set = _normalize_holiday_dates(feriados, feriado=bool(feriado), data_missao=data_missao)
    calendar_breakdown = _split_calendar_interval(
        horario_apresentacao,
        horario_abandono,
        periodo_diurno_inicio=periodo_diurno_inicio,
        periodo_diurno_fim=periodo_diurno_fim,
        feriados=feriados_set,
    )
    minutos_diurnos = calendar_breakdown["minutos_diurnos"]
    minutos_noturnos_reais = calendar_breakdown["minutos_noturnos_reais"]
    minutos_pos_exec = _resolve_int(missao_operacional.get("pos_exec_min")) or 0
    if minutos_pos_exec < 0:
        raise BonificacaoHorariaInvalidaErro(
            "Pos execucao em minutos nao pode ser negativo.",
            code="bonificacao_horaria_pos_exec_min_invalido",
        )
    duty_limit_at = horario_apresentacao + timedelta(minutes=DUTY_LIMIT_MINUTES)
    duty_effective_end = horario_abandono + timedelta(minutes=minutos_pos_exec)
    minutos_pos = max(_minutes_between(duty_limit_at, duty_effective_end), 0) if duty_effective_end > duty_limit_at else 0
    pos_breakdown = _split_calendar_interval(
        duty_limit_at,
        duty_effective_end,
        periodo_diurno_inicio=periodo_diurno_inicio,
        periodo_diurno_fim=periodo_diurno_fim,
        feriados=feriados_set,
    ) if minutos_pos else _empty_calendar_breakdown()

    normal_night_hours = _decimal(minutes=calendar_breakdown["normal_minutos_noturnos"]) / duracao_hora_noturna
    special_night_hours = _decimal(minutes=calendar_breakdown["especial_minutos_noturnos"]) / duracao_hora_noturna
    special_day_hours = _decimal(minutes=calendar_breakdown["especial_minutos_diurnos"]) / STANDARD_HOUR_MINUTES
    horas_noturnas_precisas = normal_night_hours + special_night_hours
    normal_pos_minutes = pos_breakdown["normal_minutos_diurnos"] + pos_breakdown["normal_minutos_noturnos"]
    special_pos_minutes = pos_breakdown["especial_minutos_diurnos"] + pos_breakdown["especial_minutos_noturnos"]
    normal_pos_hours = _decimal(minutes=normal_pos_minutes) / duracao_hora_noturna
    special_pos_hours = _decimal(minutes=special_pos_minutes) / duracao_hora_noturna
    horas_pos_precisas = normal_pos_hours + special_pos_hours
    horas_noturnas_remuneraveis_precisas = horas_noturnas_precisas + horas_pos_precisas
    horas_noturnas_convertidas = horas_noturnas_remuneraveis_precisas.quantize(NIGHT_HOUR_QUANTIZER, rounding=ROUND_HALF_UP)
    horas_diurnas_padrao = _decimal(minutes=minutos_diurnos) / STANDARD_HOUR_MINUTES

    domingo = bool(calendar_breakdown["tem_domingo"])
    has_special_calendar = bool(domingo_feriado or calendar_breakdown["tem_especial"])
    valor_adicional_noturno = _money(normal_night_hours * _parameter_decimal(parametros["adicional_noturno"]))
    valor_domingo_feriado_diurno = _money(special_day_hours * _parameter_decimal(parametros["domingo_feriado_diurno"]))
    valor_domingo_feriado_noturno = _money(
        special_night_hours * _parameter_decimal(parametros["domingo_feriado_noturno"])
    )

    minutos_pre = 0
    valor_pre = Decimal("0.00")
    valor_pos = _money(
        (normal_pos_hours * _parameter_decimal(parametros["adicional_noturno"]))
        + (special_pos_hours * _parameter_decimal(parametros["domingo_feriado_noturno"]))
    )
    total = _money(
        valor_adicional_noturno
        + valor_domingo_feriado_diurno
        + valor_domingo_feriado_noturno
        + valor_pre
        + valor_pos
    )
    parametros_usados = [_parameter_reference(parametros[tipo]) for tipo in REQUIRED_PARAMETER_TYPES]
    memoria_calculo = _build_memory(
        missao_operacional=missao_operacional,
        participante=participante,
        funcao=funcao,
        tripulante_id=tripulante_id,
        data_missao=data_missao,
        horario_apresentacao=horario_apresentacao,
        horario_abandono=horario_abandono,
        jornada_total_minutos=jornada_total_minutos,
        minutos_diurnos=minutos_diurnos,
        minutos_noturnos_reais=minutos_noturnos_reais,
        horas_noturnas_convertidas=horas_noturnas_convertidas,
        horas_diurnas_padrao=horas_diurnas_padrao,
        minutos_pre=minutos_pre,
        minutos_pos=minutos_pos,
        pos_exec_min=minutos_pos_exec,
        domingo=domingo,
        feriado=bool(calendar_breakdown["tem_feriado"] or feriado),
        domingo_feriado=has_special_calendar,
        calendar_breakdown=calendar_breakdown,
        pos_breakdown=pos_breakdown,
        parametros=parametros,
        parametros_usados=parametros_usados,
        valores={
            "valor_adicional_noturno": valor_adicional_noturno,
            "valor_domingo_feriado_diurno": valor_domingo_feriado_diurno,
            "valor_domingo_feriado_noturno": valor_domingo_feriado_noturno,
            "valor_pre": valor_pre,
            "valor_pos": valor_pos,
            "total": total,
        },
        calculation_version=calculation_version,
    )

    return {
        "mission_id": _resolve_int(missao_operacional.get("id") or participante.get("mission_id")),
        "missao_operacional_id": _resolve_int(missao_operacional.get("id") or participante.get("missao_operacional_id")),
        "tripulante_id": tripulante_id,
        "funcao": funcao,
        "jornada_total_minutos": jornada_total_minutos,
        "minutos_diurnos": minutos_diurnos,
        "minutos_noturnos_reais": minutos_noturnos_reais,
        "minutos_noturnos": minutos_noturnos_reais,
        "horas_noturnas_convertidas": horas_noturnas_convertidas,
        "minutos_pre": minutos_pre,
        "minutos_pos": minutos_pos,
        "domingo_feriado": has_special_calendar,
        "valor_adicional_noturno": valor_adicional_noturno,
        "valor_domingo_feriado_diurno": valor_domingo_feriado_diurno,
        "valor_domingo_feriado_noturno": valor_domingo_feriado_noturno,
        "valor_pre": valor_pre,
        "valor_pos": valor_pos,
        "total": total,
        "memoria_calculo": memoria_calculo,
        "parametros_usados": parametros_usados,
        "calculation_version": calculation_version,
    }


def _resolve_funcao(participante: dict[str, Any]) -> str:
    funcao = str(participante.get("funcao") or "").strip()
    if funcao not in FINANCE_CREW_FUNCTIONS:
        raise BonificacaoHorariaInvalidaErro(
            "Funcao do participante deve ser comandante ou copiloto.",
            code="bonificacao_horaria_funcao_invalida",
        )
    return funcao


def _resolve_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _parse_reference_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _optional_text(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_active_status(parameter: dict[str, Any]) -> bool:
    return str(parameter.get("status") or "").strip().lower() == "ativo"


def _parameter_id(parameter: dict[str, Any], *, index: int) -> int:
    raw = parameter.get("id")
    if raw in (None, ""):
        raw = parameter.get("parameter_id")
    if raw in (None, ""):
        return -1_000_000 - index
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1_000_000 - index


def _normalize_parameter_pool(parametros_vigentes: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(parametros_vigentes or []):
        row = dict(item or {})
        row.setdefault("org_id", FINANCE_ORG_SCOPE_DEFAULT)
        row["status"] = str(row.get("status") or "ativo").strip() or "ativo"
        row["motivo"] = str(row.get("motivo") or "").strip()
        row["id"] = _parameter_id(row, index=index)
        normalized.append(row)
    return normalized


def _vigencia_cobre_data(parameter: dict[str, Any], *, reference_date: date) -> bool:
    start = _parse_reference_date(parameter.get("vigencia_inicio"))
    end = _parse_reference_date(parameter.get("vigencia_fim"))
    if start is None:
        return False
    if end is not None and end < start:
        return False
    if start > reference_date:
        return False
    if end is not None and end < reference_date:
        return False
    return True


def _blocking_payload(parameter: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        "parameter_id": parameter.get("id"),
        "tipo": str(parameter.get("tipo") or "").strip(),
        "funcao": str(parameter.get("funcao") or "").strip() or None,
        "categoria": str(parameter.get("categoria") or "").strip() or None,
        "unidade": str(parameter.get("unidade") or "").strip(),
        "valor": str(parameter.get("valor") or ""),
        "governance_class": classificacao_governanca_parametro(parameter),
        "reasons": sorted(set(reasons)),
    }


def _validate_parameter_pool(
    parametros_pool: list[dict[str, Any]],
    *,
    reference_date: date,
    supported_types: tuple[str, ...],
    real_closure: bool,
    release_environment: str,
) -> None:
    relevant = [
        parameter
        for parameter in parametros_pool
        if str(parameter.get("tipo") or "").strip() in supported_types
    ]
    if not relevant:
        return

    overlap_ids = detectar_sobreposicoes_ativas(relevant, include_unit=False)
    divergence_ids = detectar_divergencias_ativas(relevant, include_unit=False)
    blocking: list[dict[str, Any]] = []

    for parameter in relevant:
        reasons: list[str] = []
        tipo = _optional_text(parameter.get("tipo")) or ""
        unidade = _optional_text(parameter.get("unidade")) or ""
        funcao_parametro = _optional_text(parameter.get("funcao"))
        categoria_parametro = _optional_text(parameter.get("categoria"))
        rule = HOURLY_PARAMETER_RULES.get(tipo)
        parameter_id = int(parameter.get("id"))
        if not _is_active_status(parameter):
            reasons.append("status_inativo")
        if rule:
            if unidade != rule["unidade"]:
                reasons.append("unidade_invalida_para_tipo")
            if rule["funcao_mode"] == "none" and funcao_parametro is not None:
                reasons.append("funcao_invalida_para_tipo")
            if rule["funcao_mode"] == "crew" and funcao_parametro not in FINANCE_CREW_FUNCTIONS:
                reasons.append("funcao_invalida_para_tipo")
            if categoria_parametro not in rule["categorias"]:
                reasons.append("categoria_invalida_para_tipo")
        if str(parameter.get("unidade") or "").strip().upper() == "BRL":
            reasons.append("unidade_brl_legacy")
        if not _vigencia_cobre_data(parameter, reference_date=reference_date):
            reasons.append("vigencia_invalida_ou_fora_da_data")
        if parameter_id in overlap_ids:
            reasons.append("sobreposicao_semantica_ativa")
        if parameter_id in divergence_ids:
            reasons.append("divergencia_semantica_ativa")
        if real_closure:
            if not parametro_elegivel_fechamento_real(parameter, environment=release_environment):
                reasons.append("nao_elegivel_para_fechamento_real")
            if classificacao_governanca_parametro(parameter) == "qa-smoke":
                reasons.append("classificacao_qa_smoke_bloqueada")
        if reasons:
            blocking.append(_blocking_payload(parameter, reasons))

    if blocking:
        raise ParametroBonificacaoHorariaNaoElegivelErro(
            blocking_parameters=blocking,
            real_closure=real_closure,
        )


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        raise BonificacaoHorariaInvalidaErro(
            "Data da missao operacional e obrigatoria.",
            code="bonificacao_horaria_data_obrigatoria",
        )
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise BonificacaoHorariaInvalidaErro(
            "Data da missao operacional deve estar no formato YYYY-MM-DD.",
            code="bonificacao_horaria_data_invalida",
        ) from exc


def _parse_optional_date(value) -> date | None:
    if value in (None, ""):
        return None
    return _parse_date(value)


def _parse_datetime_with_explicit_date(value, *, base_date: date) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None), True
    if isinstance(value, time):
        return datetime.combine(base_date, value), False
    raw = str(value or "").strip()
    if not raw:
        raise BonificacaoHorariaInvalidaErro(
            "Horario de apresentacao e abandono sao obrigatorios.",
            code="bonificacao_horaria_horario_obrigatorio",
        )
    try:
        if len(raw) <= 5 and ":" in raw:
            hour, minute = raw.split(":", 1)
            return datetime.combine(base_date, time(int(hour), int(minute))), False
        return datetime.fromisoformat(raw.replace(" ", "T")).replace(tzinfo=None), True
    except ValueError as exc:
        raise BonificacaoHorariaInvalidaErro(
            "Horario deve estar em formato ISO ou HH:MM.",
            code="bonificacao_horaria_horario_invalido",
        ) from exc


def _resolve_journey_interval(
    missao_operacional: dict[str, Any],
    *,
    data_missao: date,
    data_final: date,
) -> tuple[datetime, datetime]:
    horario_apresentacao, _start_has_explicit_date = _parse_datetime_with_explicit_date(
        missao_operacional.get("horario_apresentacao"),
        base_date=data_missao,
    )
    horario_abandono, end_has_explicit_date = _parse_datetime_with_explicit_date(
        missao_operacional.get("horario_abandono"),
        base_date=data_missao,
    )
    if not end_has_explicit_date and data_final > data_missao:
        horario_abandono = datetime.combine(data_final, horario_abandono.time())
    if horario_abandono <= horario_apresentacao:
        horario_abandono += timedelta(days=1)
    return horario_apresentacao, horario_abandono


def _parse_datetime(value, *, base_date: date) -> datetime:
    return _parse_datetime_with_explicit_date(value, base_date=base_date)[0]


def _parameter_time(parameter: dict[str, Any]) -> time:
    if str(parameter.get("unidade") or "").strip() != DAY_PERIOD_UNIT:
        raise BonificacaoHorariaInvalidaErro(
            f"Parametro {parameter.get('tipo')} deve usar unidade minutos_do_dia.",
            code="bonificacao_horaria_parametro_horario_invalido",
        )
    try:
        minute_of_day_decimal = Decimal(str(parameter.get("valor")).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise BonificacaoHorariaInvalidaErro(
            f"Parametro {parameter.get('tipo')} deve usar valor numerico em minutos_do_dia.",
            code="bonificacao_horaria_parametro_horario_invalido",
        ) from exc
    if minute_of_day_decimal != minute_of_day_decimal.to_integral_value():
        raise BonificacaoHorariaInvalidaErro(
            f"Parametro {parameter.get('tipo')} deve usar minuto inteiro desde 00:00.",
            code="bonificacao_horaria_parametro_horario_invalido",
        )
    minute_of_day = int(minute_of_day_decimal)
    if minute_of_day < 0 or minute_of_day > 1439 or 0 < minute_of_day < 60:
        raise BonificacaoHorariaInvalidaErro(
            f"Parametro {parameter.get('tipo')} deve estar entre 0 e 1439 minutos desde 00:00.",
            code="bonificacao_horaria_parametro_horario_invalido",
        )
    return time(minute_of_day // 60, minute_of_day % 60)


def _parameter_decimal(parameter: dict[str, Any]) -> Decimal:
    try:
        return Decimal(str(parameter.get("valor")).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise BonificacaoHorariaInvalidaErro(
            f"Parametro {parameter.get('tipo')} deve ser numerico.",
            code="bonificacao_horaria_parametro_decimal_invalido",
        ) from exc


def _resolve_required_parameters(parametros_vigentes: list[dict[str, Any]] | tuple[dict[str, Any], ...], *, funcao: str):
    resolved = {
        "duracao_hora_noturna_minutos": _find_parameter(
            parametros_vigentes,
            "duracao_hora_noturna_minutos",
            funcao=None,
            unidade=NIGHT_DURATION_UNIT,
        ),
        "periodo_diurno_inicio": _find_parameter(
            parametros_vigentes,
            "periodo_diurno_inicio",
            funcao=None,
            unidade=DAY_PERIOD_UNIT,
        ),
        "periodo_diurno_fim": _find_parameter(
            parametros_vigentes,
            "periodo_diurno_fim",
            funcao=None,
            unidade=DAY_PERIOD_UNIT,
        ),
        "adicional_noturno": _find_parameter(
            parametros_vigentes,
            "adicional_noturno",
            funcao=funcao,
            unidade=MONETARY_PARAMETER_UNIT,
        ),
        "domingo_feriado_diurno": _find_parameter(
            parametros_vigentes,
            "domingo_feriado_diurno",
            funcao=funcao,
            unidade=MONETARY_PARAMETER_UNIT,
        ),
        "domingo_feriado_noturno": _find_parameter(
            parametros_vigentes,
            "domingo_feriado_noturno",
            funcao=funcao,
            unidade=MONETARY_PARAMETER_UNIT,
        ),
    }
    return resolved


def _find_parameter(
    parametros_vigentes: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    tipo: str,
    *,
    funcao: str | None,
    unidade: str,
) -> dict[str, Any]:
    candidates = [
        item
        for item in parametros_vigentes
        if str(item.get("tipo") or "").strip() == tipo
        and str(item.get("unidade") or "").strip() == unidade
    ]
    if funcao:
        candidates = [item for item in candidates if str(item.get("funcao") or "").strip() == funcao]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ParametroBonificacaoHorariaAmbiguoErro(tipo, funcao=funcao, unidade=unidade)
        raise ParametroBonificacaoHorariaAusenteErro(tipo, funcao=funcao)
    global_candidates = [item for item in candidates if not str(item.get("funcao") or "").strip()]
    if len(global_candidates) == 1:
        return global_candidates[0]
    if len(global_candidates) > 1:
        raise ParametroBonificacaoHorariaAmbiguoErro(tipo, unidade=unidade)
    raise ParametroBonificacaoHorariaAusenteErro(tipo)


def _minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _diurnal_minutes(
    start: datetime,
    end: datetime,
    *,
    periodo_diurno_inicio: time,
    periodo_diurno_fim: time,
) -> int:
    total = 0
    day = start.date() - timedelta(days=1)
    last_day = end.date() + timedelta(days=1)
    while day <= last_day:
        interval_start = datetime.combine(day, periodo_diurno_inicio)
        interval_end = datetime.combine(day, periodo_diurno_fim)
        if interval_end <= interval_start:
            interval_end += timedelta(days=1)
        total += _intersection_minutes(start, end, interval_start, interval_end)
        day += timedelta(days=1)
    return min(total, _minutes_between(start, end))


def _normalize_holiday_dates(
    feriados: list[Any] | tuple[Any, ...] | set[Any] | None,
    *,
    feriado: bool,
    data_missao: date,
) -> set[date]:
    dates: set[date] = set()
    for value in feriados or []:
        resolved = _parse_reference_date(value.get("data") if isinstance(value, dict) else value)
        if resolved:
            dates.add(resolved)
    if feriado:
        dates.add(data_missao)
    return dates


def _empty_calendar_breakdown() -> dict[str, Any]:
    return {
        "minutos_diurnos": 0,
        "minutos_noturnos_reais": 0,
        "normal_minutos_diurnos": 0,
        "normal_minutos_noturnos": 0,
        "especial_minutos_diurnos": 0,
        "especial_minutos_noturnos": 0,
        "tem_domingo": False,
        "tem_feriado": False,
        "tem_especial": False,
        "dias": [],
    }


def _split_calendar_interval(
    start: datetime,
    end: datetime,
    *,
    periodo_diurno_inicio: time,
    periodo_diurno_fim: time,
    feriados: set[date],
) -> dict[str, Any]:
    breakdown = _empty_calendar_breakdown()
    if end <= start:
        return breakdown

    current_day = start.date()
    while current_day <= end.date():
        day_start = max(start, datetime.combine(current_day, time.min))
        day_end = min(end, datetime.combine(current_day + timedelta(days=1), time.min))
        if day_end <= day_start:
            current_day += timedelta(days=1)
            continue

        total_day_minutes = _minutes_between(day_start, day_end)
        day_diurnal_minutes = _diurnal_minutes(
            day_start,
            day_end,
            periodo_diurno_inicio=periodo_diurno_inicio,
            periodo_diurno_fim=periodo_diurno_fim,
        )
        day_night_minutes = total_day_minutes - day_diurnal_minutes
        is_sunday = current_day.weekday() == 6
        is_holiday = current_day in feriados
        is_special = bool(is_sunday or is_holiday)

        breakdown["minutos_diurnos"] += day_diurnal_minutes
        breakdown["minutos_noturnos_reais"] += day_night_minutes
        if is_special:
            breakdown["especial_minutos_diurnos"] += day_diurnal_minutes
            breakdown["especial_minutos_noturnos"] += day_night_minutes
        else:
            breakdown["normal_minutos_diurnos"] += day_diurnal_minutes
            breakdown["normal_minutos_noturnos"] += day_night_minutes
        breakdown["tem_domingo"] = bool(breakdown["tem_domingo"] or is_sunday)
        breakdown["tem_feriado"] = bool(breakdown["tem_feriado"] or is_holiday)
        breakdown["tem_especial"] = bool(breakdown["tem_especial"] or is_special)
        breakdown["dias"].append(
            {
                "data": current_day.isoformat(),
                "inicio": day_start.isoformat(),
                "fim": day_end.isoformat(),
                "domingo": is_sunday,
                "feriado": is_holiday,
                "especial": is_special,
                "minutos_diurnos": day_diurnal_minutes,
                "minutos_noturnos_reais": day_night_minutes,
            }
        )
        current_day += timedelta(days=1)
    return breakdown


def _intersection_minutes(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> int:
    intersection_start = max(start, other_start)
    intersection_end = min(end, other_end)
    if intersection_end <= intersection_start:
        return 0
    return _minutes_between(intersection_start, intersection_end)


def _decimal(*, minutes: int) -> Decimal:
    return Decimal(int(minutes))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _parameter_reference(parameter: dict[str, Any]) -> dict[str, Any]:
    reference = {
        "parameter_id": _resolve_int(parameter.get("parameter_id") if "parameter_id" in parameter else parameter.get("id")),
        "tipo": str(parameter.get("tipo") or "").strip(),
        "funcao": str(parameter.get("funcao") or "").strip() or None,
        "categoria": str(parameter.get("categoria") or "").strip() or None,
        "valor": str(parameter.get("valor")),
        "unidade": str(parameter.get("unidade") or "").strip(),
        "vigencia_inicio": _date_text(parameter.get("vigencia_inicio")),
        "vigencia_fim": _date_text(parameter.get("vigencia_fim")),
    }
    display_value = _parameter_display_value(parameter)
    if display_value:
        reference["display_value"] = display_value
    return reference


def _parameter_display_value(parameter: dict[str, Any]) -> str | None:
    if str(parameter.get("tipo") or "").strip() not in {"periodo_diurno_inicio", "periodo_diurno_fim"}:
        return None
    if str(parameter.get("unidade") or "").strip() != DAY_PERIOD_UNIT:
        return None
    try:
        minute = int(Decimal(str(parameter.get("valor")).replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None
    if minute < 0 or minute > 1439:
        return None
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _date_text(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _build_step(
    *,
    rule_key: str,
    rule_label: str,
    entrada_usada: dict[str, Any],
    parametro_usado: dict[str, Any] | None,
    formula_conceitual: str,
    resultado_intermediario: dict[str, Any],
    resultado_final: dict[str, Any],
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "rule_key": rule_key,
        "rule_label": rule_label,
        "entrada_usada": entrada_usada,
        "parametro_usado": _parameter_reference(parametro_usado) if parametro_usado else None,
        "formula_conceitual": formula_conceitual,
        "resultado_intermediario": resultado_intermediario,
        "resultado_final": resultado_final,
        "notes": notes or [],
    }


def _build_memory(
    *,
    missao_operacional: dict[str, Any],
    participante: dict[str, Any],
    funcao: str,
    tripulante_id: int | None,
    data_missao: date,
    horario_apresentacao: datetime,
    horario_abandono: datetime,
    jornada_total_minutos: int,
    minutos_diurnos: int,
    minutos_noturnos_reais: int,
    horas_noturnas_convertidas: Decimal,
    horas_diurnas_padrao: Decimal,
    minutos_pre: int,
    minutos_pos: int,
    pos_exec_min: int,
    domingo: bool,
    feriado: bool,
    domingo_feriado: bool,
    calendar_breakdown: dict[str, Any],
    pos_breakdown: dict[str, Any],
    parametros: dict[str, dict[str, Any]],
    parametros_usados: list[dict[str, Any]],
    valores: dict[str, Decimal],
    calculation_version: str,
) -> dict[str, Any]:
    return {
        "calculation_version": calculation_version,
        "org_id": str(missao_operacional.get("org_id") or FINANCE_ORG_SCOPE_DEFAULT),
        "competencia": str(missao_operacional.get("competencia") or ""),
        "source": {
            "type": "finance_mission_operational",
            "id": _resolve_int(missao_operacional.get("id")),
        },
        "participant": {
            "tripulante_id": tripulante_id,
            "funcao": funcao,
        },
        "inputs": {
            "data_missao": data_missao.isoformat(),
            "data_final": _date_text(missao_operacional.get("data_final") or data_missao),
            "horario_apresentacao": horario_apresentacao.isoformat(),
            "horario_abandono": horario_abandono.isoformat(),
            "pos_exec_min": pos_exec_min,
            "participante": {
                "mission_id": participante.get("mission_id"),
                "tripulante_id": participante.get("tripulante_id"),
                "funcao": participante.get("funcao"),
            },
        },
        "parameters": parametros_usados,
        "calendar_flags": {
            "domingo": domingo,
            "feriado": bool(feriado),
            "domingo_feriado": domingo_feriado,
        },
        "steps": [
            _build_step(
                rule_key="jornada_total",
                rule_label="Jornada total da missao operacional",
                entrada_usada={
                    "horario_apresentacao": horario_apresentacao.isoformat(),
                    "horario_abandono": horario_abandono.isoformat(),
                },
                parametro_usado=None,
                formula_conceitual="diferenca_em_minutos(horario_abandono - horario_apresentacao)",
                resultado_intermediario={},
                resultado_final={"jornada_total_minutos": jornada_total_minutos},
            ),
            _build_step(
                rule_key="separacao_diurno_noturno",
                rule_label="Separacao entre minutos diurnos e noturnos reais",
                entrada_usada={
                    "jornada_total_minutos": jornada_total_minutos,
                    "periodo_diurno_inicio": {
                        "minutos_do_dia": int(Decimal(str(parametros["periodo_diurno_inicio"].get("valor")))),
                        "display_value": _parameter_display_value(parametros["periodo_diurno_inicio"]),
                    },
                    "periodo_diurno_fim": {
                        "minutos_do_dia": int(Decimal(str(parametros["periodo_diurno_fim"].get("valor")))),
                        "display_value": _parameter_display_value(parametros["periodo_diurno_fim"]),
                    },
                },
                parametro_usado=None,
                formula_conceitual=(
                    "fatiamento por dia calendario; intersecao com periodo diurno; "
                    "normal e domingo/feriado separados por data real do minuto"
                ),
                resultado_intermediario={
                    "minutos_diurnos": minutos_diurnos,
                    "normal_minutos_diurnos": calendar_breakdown["normal_minutos_diurnos"],
                    "especial_minutos_diurnos": calendar_breakdown["especial_minutos_diurnos"],
                    "fatias": calendar_breakdown["dias"],
                },
                resultado_final={
                    "minutos_noturnos_reais": minutos_noturnos_reais,
                    "normal_minutos_noturnos": calendar_breakdown["normal_minutos_noturnos"],
                    "especial_minutos_noturnos": calendar_breakdown["especial_minutos_noturnos"],
                },
            ),
            _build_step(
                rule_key="conversao_hora_noturna",
                rule_label="Conversao da hora noturna remuneravel",
                entrada_usada={
                    "minutos_noturnos_reais": minutos_noturnos_reais,
                    "minutos_pos": minutos_pos,
                },
                parametro_usado=parametros["duracao_hora_noturna_minutos"],
                formula_conceitual=(
                    "(minutos_noturnos_reais + minutos_pos) / duracao_hora_noturna_minutos; "
                    "minutos_pos representam estouro de jornada acima de 10h30"
                ),
                resultado_intermediario={
                    "duracao_hora_noturna_minutos": str(parametros["duracao_hora_noturna_minutos"].get("valor")),
                },
                resultado_final={"horas_noturnas_convertidas": _decimal_text(horas_noturnas_convertidas)},
            ),
            _build_step(
                rule_key="adicional_aplicavel",
                rule_label="Aplicacao de adicional horario por calendario",
                entrada_usada={
                    "domingo_feriado": domingo_feriado,
                    "horas_diurnas_padrao": _decimal_text(horas_diurnas_padrao),
                    "horas_noturnas_convertidas": _decimal_text(horas_noturnas_convertidas),
                },
                parametro_usado=(
                    parametros["domingo_feriado_noturno"]
                    if domingo_feriado and minutos_noturnos_reais
                    else parametros["domingo_feriado_diurno"]
                    if domingo_feriado
                    else parametros["adicional_noturno"]
                ),
                formula_conceitual=(
                    "adicional_noturno apenas em minutos noturnos normais; "
                    "domingo_feriado_diurno em minutos diurnos especiais; "
                    "domingo_feriado_noturno em minutos noturnos especiais"
                    if domingo_feriado
                    else "adicional_noturno por hora noturna convertida"
                ),
                resultado_intermediario={
                    "normal_minutos_noturnos": calendar_breakdown["normal_minutos_noturnos"],
                    "especial_minutos_diurnos": calendar_breakdown["especial_minutos_diurnos"],
                    "especial_minutos_noturnos": calendar_breakdown["especial_minutos_noturnos"],
                    "valor_adicional_noturno": _decimal_text(valores["valor_adicional_noturno"]),
                    "valor_domingo_feriado_diurno": _decimal_text(valores["valor_domingo_feriado_diurno"]),
                    "valor_domingo_feriado_noturno": _decimal_text(valores["valor_domingo_feriado_noturno"]),
                },
                resultado_final={"subtotal": _decimal_text(valores["total"])},
            ),
            _build_step(
                rule_key="pre_pos_jornada",
                rule_label="Pre e pos-jornada",
                entrada_usada={
                    "jornada_total_minutos": jornada_total_minutos,
                    "limite_jornada_minutos": DUTY_LIMIT_MINUTES,
                    "pos_exec_min": pos_exec_min,
                },
                parametro_usado=None,
                formula_conceitual=(
                    "intersecao entre intervalo efetivo ate abandono+pos_exec e o ponto apresentacao+10h30; "
                    "minutos especiais usam taxa domingo/feriado_noturno, minutos normais usam adicional_noturno"
                ),
                resultado_intermediario={
                    "minutos_pre": minutos_pre,
                    "minutos_pos": minutos_pos,
                    "normal_minutos_pos": pos_breakdown["normal_minutos_diurnos"] + pos_breakdown["normal_minutos_noturnos"],
                    "especial_minutos_pos": pos_breakdown["especial_minutos_diurnos"] + pos_breakdown["especial_minutos_noturnos"],
                    "fatias_pos": pos_breakdown["dias"],
                },
                resultado_final={
                    "valor_pre": _decimal_text(valores["valor_pre"]),
                    "valor_pos": _decimal_text(valores["valor_pos"]),
                },
                notes=["Estouro de jornada acima de 10h30 compoe pos-calculo e entra na hora reduzida remuneravel."],
            ),
        ],
        "totals": {
            "jornada_total_minutos": jornada_total_minutos,
            "minutos_diurnos": minutos_diurnos,
            "minutos_noturnos_reais": minutos_noturnos_reais,
            "normal_minutos_diurnos": calendar_breakdown["normal_minutos_diurnos"],
            "normal_minutos_noturnos": calendar_breakdown["normal_minutos_noturnos"],
            "especial_minutos_diurnos": calendar_breakdown["especial_minutos_diurnos"],
            "especial_minutos_noturnos": calendar_breakdown["especial_minutos_noturnos"],
            "minutos_pre": minutos_pre,
            "minutos_pos": minutos_pos,
            "horas_noturnas_convertidas": _decimal_text(horas_noturnas_convertidas),
            "total": _decimal_text(valores["total"]),
        },
        "warnings": [],
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
    }
