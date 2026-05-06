from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..audit import record_audit_event
from ..contracts.financeiro import FINANCE_CREW_FUNCTIONS, FINANCE_ORG_SCOPE_DEFAULT
from ..core.domain_errors import DomainError, DomainValidationError
from ..db import get_db
from ..repositories.financeiro_lancamentos_jornada import listar_linhas_horas_totais_voadas

MONEY_QUANTIZER = Decimal("0.01")
MINUTE_QUANTIZER = Decimal("1")
ZERO_MONEY = Decimal("0.00")
_PDF_EOF_MARKER = b"%%EOF"
_PDF_EOF_SCAN_BYTES = 4096
_REPORT_VERSION = "finance-total-flight-hours-report-v1"
_UNPERSISTED_HOURLY_MESSAGE = (
    "Existem lançamentos sem cálculo persistido. "
    "Recalcule a grade antes de exportar o relatório financeiro."
)
_MONTHS_PT = {
    1: "JANEIRO",
    2: "FEVEREIRO",
    3: "MARÇO",
    4: "ABRIL",
    5: "MAIO",
    6: "JUNHO",
    7: "JULHO",
    8: "AGOSTO",
    9: "SETEMBRO",
    10: "OUTUBRO",
    11: "NOVEMBRO",
    12: "DEZEMBRO",
}


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _text(value, default: str = "") -> str:
    return str(value or "").strip() or default


def _bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sim", "yes", "on"}
    return bool(value)


def _int(value, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _money(value) -> Decimal:
    if value in (None, ""):
        return ZERO_MONEY
    try:
        return Decimal(str(value).replace(",", ".")).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return ZERO_MONEY


def _decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return default


def _money_text(value: Decimal) -> str:
    return format(_money(value), "f")


def _pdf_money(value, *, dash_when_zero: bool = False) -> str:
    amount = _money(value)
    if dash_when_zero and amount == ZERO_MONEY:
        return "-"
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _minutes_hhmm(total_minutes: int) -> str:
    sign = "-" if total_minutes < 0 else ""
    minutes = abs(int(total_minutes or 0))
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def _json_value(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _assert_pdf_bytes_complete(content: bytes, *, code: str) -> bytes:
    data = bytes(content or b"")
    if not data:
        raise DomainError("PDF gerado vazio.", status=500, code=f"{code}_empty")
    if not data.startswith(b"%PDF"):
        raise DomainError("PDF gerado sem assinatura valida.", status=500, code=f"{code}_invalid_signature")
    if _PDF_EOF_MARKER not in data[-_PDF_EOF_SCAN_BYTES:]:
        raise DomainError("PDF gerado incompleto.", status=500, code=f"{code}_incomplete")
    return data


def _competencia_label(competencia: str) -> str:
    year, month = _validate_competencia(competencia).split("-", 1)
    return f"{_MONTHS_PT[int(month)]}\n{year}"


def _funcao_plural(funcao: str) -> str:
    normalized = _validate_funcao(funcao)
    return "COMANDANTES" if normalized == "comandante" else "COPILOTOS"


def _validate_competencia(competencia: str) -> str:
    value = _text(competencia)
    if len(value) != 7 or value[4] != "-":
        raise DomainValidationError(
            "Competencia invalida. Use o formato YYYY-MM.",
            code="finance_total_flight_hours_invalid_competence",
            details={"field": "competencia", "expected_format": "YYYY-MM", "value": value or None},
        )
    year, month = value.split("-", 1)
    if not (year.isdigit() and month.isdigit() and 1 <= int(month) <= 12):
        raise DomainValidationError(
            "Competencia invalida. Use o formato YYYY-MM.",
            code="finance_total_flight_hours_invalid_competence",
            details={"field": "competencia", "expected_format": "YYYY-MM", "value": value or None},
        )
    return value


def _validate_funcao(funcao: str) -> str:
    value = _text(funcao).lower()
    if value not in FINANCE_CREW_FUNCTIONS:
        raise DomainValidationError(
            "Funcao operacional invalida.",
            code="finance_total_flight_hours_invalid_funcao",
            details={"field": "funcao", "allowed": list(FINANCE_CREW_FUNCTIONS), "value": value or None},
        )
    return value


def _memory_totals(memory: dict) -> dict:
    totals = memory.get("totals") if isinstance(memory, dict) else {}
    return totals if isinstance(totals, dict) else {}


def _parameter_pool(row: dict, memory: dict) -> list[dict]:
    pool = []
    if isinstance(memory, dict):
        parameters = memory.get("parameters")
        if isinstance(parameters, list):
            pool.extend(item for item in parameters if isinstance(item, dict))
    persisted = _json_value(row.get("parametros_usados"), [])
    if isinstance(persisted, list):
        pool.extend(item for item in persisted if isinstance(item, dict))
    return pool


def _night_duration_minutes(row: dict, memory: dict) -> Decimal | None:
    for parameter in _parameter_pool(row, memory):
        if _text(parameter.get("tipo")) != "duracao_hora_noturna_minutos":
            continue
        value = _decimal(parameter.get("valor"), default=Decimal("0"))
        if value > 0:
            return value
    return None


def _minutes_from_decimal_hours(value) -> int:
    return int((_decimal(value) * Decimal("60")).quantize(MINUTE_QUANTIZER, rounding=ROUND_HALF_UP))


def _persisted_reduced_minutes(memory_totals: dict, *keys: str) -> int | None:
    for key in keys:
        if key not in memory_totals or memory_totals.get(key) in (None, ""):
            continue
        if "horas" in key:
            return _minutes_from_decimal_hours(memory_totals.get(key))
        return _int(memory_totals.get(key))
    return None


def _night_reduced_minutes(
    *,
    row: dict,
    memory: dict,
    memory_totals: dict,
    raw_minutes: int,
    total_raw_night_minutes: int,
    bucket: str,
) -> tuple[int, list[dict]]:
    if raw_minutes <= 0:
        return 0, []

    if bucket == "normal":
        persisted = _persisted_reduced_minutes(
            memory_totals,
            "normal_minutos_noturnos_reduzidos",
            "normal_hora_reduzida_minutos",
            "normal_horas_noturnas_convertidas",
        )
    else:
        persisted = _persisted_reduced_minutes(
            memory_totals,
            "especial_minutos_noturnos_reduzidos",
            "domingo_feriado_minutos_noturnos_reduzidos",
            "especial_hora_reduzida_minutos",
            "especial_horas_noturnas_convertidas",
        )
    if persisted is not None:
        return persisted, []

    duration = _night_duration_minutes(row, memory)
    if duration and duration > 0:
        reduced = (Decimal(raw_minutes) / duration * Decimal("60")).quantize(
            MINUTE_QUANTIZER,
            rounding=ROUND_HALF_UP,
        )
        return int(reduced), []

    total_reduced = _minutes_from_decimal_hours(row.get("horas_noturnas_convertidas"))
    if total_reduced <= 0 or total_raw_night_minutes <= 0:
        return 0, []
    allocated = (Decimal(total_reduced) * Decimal(raw_minutes) / Decimal(total_raw_night_minutes)).quantize(
        MINUTE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )
    return int(allocated), [
        {
            "code": "duracao_hora_noturna_ausente_na_memoria",
            "message": "Split noturno usou proporcao da hora reduzida total persistida por falta do parametro na memoria.",
            "missao_operacional_id": _int(row.get("missao_operacional_id")),
        }
    ]


def _is_excluded_row(row: dict, *, funcao: str) -> bool:
    if _text(row.get("linha_funcao")).lower() != funcao:
        return True
    if _text(row.get("linha_status")).lower() != "ativo":
        return True
    if _text(row.get("missao_status")).lower() == "cancelada":
        return True
    if row.get("missao_deleted_at") not in (None, "") or row.get("deleted_at") not in (None, ""):
        return True
    if _text(row.get("calculo_status")).lower() in {"obsoleto", "cancelado", "cancelada", "excluido", "excluida"}:
        return True
    if _bool(row.get("preview") or row.get("is_preview") or row.get("eh_preview")):
        return True
    return False


def _pending_payload(row: dict, *, code: str, message: str) -> dict:
    return {
        "code": code,
        "message": message,
        "linha_id": _int(row.get("linha_id")),
        "missao_operacional_id": _int(row.get("missao_operacional_id")),
        "tripulante_id": _int(row.get("linha_tripulante_id") or row.get("tripulante_id")),
        "funcao": _text(row.get("linha_funcao") or row.get("funcao")),
    }


def _new_group(row: dict, *, competencia: str, funcao: str) -> dict:
    tripulante_id = _int(row.get("linha_tripulante_id") or row.get("tripulante_id"))
    return {
        "tripulante_id": tripulante_id,
        "nome_tripulante": _text(row.get("tripulante_nome")),
        "funcao": funcao,
        "competencia": competencia,
        "dia_normal_diu_minutos": 0,
        "dia_normal_diu_valor": ZERO_MONEY,
        "dia_normal_not_minutos_reduzidos": 0,
        "dia_normal_not_valor": ZERO_MONEY,
        "domingo_feriado_diu_minutos": 0,
        "domingo_feriado_diu_valor": ZERO_MONEY,
        "domingo_feriado_not_minutos_reduzidos": 0,
        "domingo_feriado_not_valor": ZERO_MONEY,
        "componentes_adicionais_valor": ZERO_MONEY,
        "valor_total_horas": ZERO_MONEY,
        "quantidade_lancamentos": 0,
        "pendencias": [],
    }


def _componentes_linha(row: dict) -> tuple[dict, list[dict]]:
    memory = _json_value(row.get("memoria_calculo"), {})
    memory = memory if isinstance(memory, dict) else {}
    totals = _memory_totals(memory)
    is_special = _bool(row.get("domingo_feriado"))
    total_raw_night_minutes = _int(totals.get("normal_minutos_noturnos")) + _int(
        totals.get("especial_minutos_noturnos")
    )
    if total_raw_night_minutes <= 0:
        total_raw_night_minutes = _int(row.get("minutos_noturnos_reais") or row.get("minutos_noturnos"))

    normal_diu = _int(totals.get("normal_minutos_diurnos"))
    special_diu = _int(totals.get("especial_minutos_diurnos"))
    normal_not_raw = _int(totals.get("normal_minutos_noturnos"))
    special_not_raw = _int(totals.get("especial_minutos_noturnos"))
    if not any((normal_diu, special_diu, normal_not_raw, special_not_raw)):
        if is_special:
            special_diu = _int(row.get("minutos_diurnos"))
            special_not_raw = _int(row.get("minutos_noturnos_reais") or row.get("minutos_noturnos"))
        else:
            normal_diu = _int(row.get("minutos_diurnos"))
            normal_not_raw = _int(row.get("minutos_noturnos_reais") or row.get("minutos_noturnos"))

    normal_not_reduced, normal_pendencias = _night_reduced_minutes(
        row=row,
        memory=memory,
        memory_totals=totals,
        raw_minutes=normal_not_raw,
        total_raw_night_minutes=total_raw_night_minutes,
        bucket="normal",
    )
    special_not_reduced, special_pendencias = _night_reduced_minutes(
        row=row,
        memory=memory,
        memory_totals=totals,
        raw_minutes=special_not_raw,
        total_raw_night_minutes=total_raw_night_minutes,
        bucket="especial",
    )

    componentes = {
        "dia_normal_diu_minutos": normal_diu,
        "dia_normal_diu_valor": ZERO_MONEY,
        "dia_normal_not_minutos_reduzidos": normal_not_reduced,
        "dia_normal_not_valor": _money(row.get("valor_adicional_noturno")),
        "domingo_feriado_diu_minutos": special_diu,
        "domingo_feriado_diu_valor": _money(row.get("valor_domingo_feriado_diurno")),
        "domingo_feriado_not_minutos_reduzidos": special_not_reduced,
        "domingo_feriado_not_valor": _money(row.get("valor_domingo_feriado_noturno")),
        "componentes_adicionais_valor": _money(row.get("valor_pre")) + _money(row.get("valor_pos")),
        "valor_total_horas": _money(row.get("calculo_total") if row.get("calculo_total") not in (None, "") else row.get("total")),
    }
    return componentes, normal_pendencias + special_pendencias


def _add_componentes(group: dict, componentes: dict) -> None:
    for key in (
        "dia_normal_diu_minutos",
        "dia_normal_not_minutos_reduzidos",
        "domingo_feriado_diu_minutos",
        "domingo_feriado_not_minutos_reduzidos",
    ):
        group[key] += int(componentes[key])
    for key in (
        "dia_normal_diu_valor",
        "dia_normal_not_valor",
        "domingo_feriado_diu_valor",
        "domingo_feriado_not_valor",
        "componentes_adicionais_valor",
        "valor_total_horas",
    ):
        group[key] = _money(group[key] + componentes[key])


def _include_group(group: dict, *, incluir_zerados: bool) -> bool:
    if incluir_zerados or group["pendencias"]:
        return True
    numeric_minutes = (
        group["dia_normal_diu_minutos"]
        + group["dia_normal_not_minutos_reduzidos"]
        + group["domingo_feriado_diu_minutos"]
        + group["domingo_feriado_not_minutos_reduzidos"]
    )
    return numeric_minutes > 0 or group["valor_total_horas"] > ZERO_MONEY


def _finalize_group(group: dict) -> dict:
    component_total = (
        group["dia_normal_diu_valor"]
        + group["dia_normal_not_valor"]
        + group["domingo_feriado_diu_valor"]
        + group["domingo_feriado_not_valor"]
        + group["componentes_adicionais_valor"]
    ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    pendencias = list(group["pendencias"])
    if group["valor_total_horas"] != component_total:
        pendencias.append(
            {
                "code": "total_diferente_componentes_persistidos",
                "message": "Total persistido difere da soma dos componentes remuneraveis retornados.",
                "valor_total_horas": _money_text(group["valor_total_horas"]),
                "valor_componentes": _money_text(component_total),
            }
        )

    return {
        "tripulante_id": group["tripulante_id"],
        "nome_tripulante": group["nome_tripulante"],
        "funcao": group["funcao"],
        "competencia": group["competencia"],
        "dia_normal_diu_minutos": group["dia_normal_diu_minutos"],
        "dia_normal_diu_hhmm": _minutes_hhmm(group["dia_normal_diu_minutos"]),
        "dia_normal_diu_valor": _money_text(group["dia_normal_diu_valor"]),
        "dia_normal_not_minutos_reduzidos": group["dia_normal_not_minutos_reduzidos"],
        "dia_normal_not_hhmm": _minutes_hhmm(group["dia_normal_not_minutos_reduzidos"]),
        "dia_normal_not_valor": _money_text(group["dia_normal_not_valor"]),
        "domingo_feriado_diu_minutos": group["domingo_feriado_diu_minutos"],
        "domingo_feriado_diu_hhmm": _minutes_hhmm(group["domingo_feriado_diu_minutos"]),
        "domingo_feriado_diu_valor": _money_text(group["domingo_feriado_diu_valor"]),
        "domingo_feriado_not_minutos_reduzidos": group["domingo_feriado_not_minutos_reduzidos"],
        "domingo_feriado_not_hhmm": _minutes_hhmm(group["domingo_feriado_not_minutos_reduzidos"]),
        "domingo_feriado_not_valor": _money_text(group["domingo_feriado_not_valor"]),
        "componentes_adicionais_valor": _money_text(group["componentes_adicionais_valor"]),
        "valor_total_horas": _money_text(group["valor_total_horas"]),
        "quantidade_lancamentos": group["quantidade_lancamentos"],
        "possui_pendencias": bool(pendencias),
        "pendencias": pendencias,
        "fonte_dados": "financeiro_calculos_horarios_persistidos_vigentes",
    }


def _totais(linhas: list[dict]) -> dict:
    total = sum((_money(item["valor_total_horas"]) for item in linhas), ZERO_MONEY)
    return {
        "tripulantes": len(linhas),
        "quantidade_lancamentos": sum(_int(item.get("quantidade_lancamentos")) for item in linhas),
        "valor_total_horas": _money_text(total),
        "possui_pendencias": any(item.get("possui_pendencias") for item in linhas),
        "linhas_com_pendencias": sum(1 for item in linhas if item.get("possui_pendencias")),
    }


def consolidar_horas_totais_voadas(
    *,
    competencia: str,
    funcao: str,
    org_id: str | None = None,
    incluir_zerados: bool = True,
    db=None,
) -> dict:
    resolved_competencia = _validate_competencia(competencia)
    resolved_funcao = _validate_funcao(funcao)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_db = _resolve_db(db)

    rows = listar_linhas_horas_totais_voadas(
        resolved_db,
        competencia=resolved_competencia,
        funcao=resolved_funcao,
        org_id=resolved_org_id,
    )
    groups: dict[tuple[int, str], dict] = {}
    for row in rows:
        if _is_excluded_row(row, funcao=resolved_funcao):
            continue
        tripulante_id = _int(row.get("linha_tripulante_id") or row.get("tripulante_id"))
        key = (tripulante_id, resolved_funcao)
        if key not in groups:
            groups[key] = _new_group(row, competencia=resolved_competencia, funcao=resolved_funcao)
        group = groups[key]
        group["quantidade_lancamentos"] += 1

        if not _int(row.get("calculo_horario_id")):
            group["pendencias"].append(
                _pending_payload(
                    row,
                    code="calculo_horario_ausente",
                    message="Lancamento ativo sem calculo horario persistido vigente.",
                )
            )
            continue

        if _int(row.get("calculos_vigentes_count")) > 1:
            group["pendencias"].append(
                _pending_payload(
                    row,
                    code="calculos_horarios_vigentes_duplicados",
                    message="Mais de um calculo horario vigente encontrado; o relatorio usou o mais recente.",
                )
            )
        if _text(row.get("calculo_status")).lower() == "recalculo_pendente":
            group["pendencias"].append(
                _pending_payload(
                    row,
                    code="calculo_horario_recalculo_pendente",
                    message="Calculo horario persistido vigente esta marcado como recalculo_pendente.",
                )
            )

        componentes, pendencias = _componentes_linha(row)
        _add_componentes(group, componentes)
        group["pendencias"].extend(pendencias)

    linhas = [
        _finalize_group(group)
        for group in sorted(groups.values(), key=lambda item: (_text(item.get("nome_tripulante")).upper(), item["tripulante_id"]))
        if _include_group(group, incluir_zerados=bool(incluir_zerados))
    ]
    return {
        "contexto": {
            "competencia": resolved_competencia,
            "funcao": resolved_funcao,
            "org_id": resolved_org_id,
            "fonte_de_verdade": "financeiro_calculos_horarios",
            "usa_preview": False,
        },
        "linhas": linhas,
        "totais": _totais(linhas),
        "filters": {
            "competencia": resolved_competencia,
            "funcao": resolved_funcao,
            "org_id": resolved_org_id,
            "incluir_zerados": bool(incluir_zerados),
        },
    }


def _pdf_styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "HorasTotaisBrand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=colors.HexColor("#21274f"),
        ),
        "title": ParagraphStyle(
            "HorasTotaisTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "competencia": ParagraphStyle(
            "HorasTotaisCompetencia",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
        ),
        "group": ParagraphStyle(
            "HorasTotaisGroup",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "header": ParagraphStyle(
            "HorasTotaisHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.4,
            leading=7.2,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "body": ParagraphStyle(
            "HorasTotaisBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.4,
            leading=7.3,
            textColor=colors.HexColor("#111827"),
        ),
        "body_center": ParagraphStyle(
            "HorasTotaisBodyCenter",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.4,
            leading=7.3,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "body_money": ParagraphStyle(
            "HorasTotaisBodyMoney",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.4,
            leading=7.3,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#0f5f7f"),
        ),
        "small": ParagraphStyle(
            "HorasTotaisSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=8.5,
            textColor=colors.HexColor("#475569"),
        ),
    }


def _pdf_cell(value, style):
    return Paragraph(escape(_text(value, "-")).replace("\n", "<br/>"), style)


def _pdf_page_footer(title: str):
    def _draw(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(9 * mm, 6 * mm, "Brasil Vida - Documento gerado pelo sistema")
        canvas.drawCentredString(landscape(A4)[0] / 2, 6 * mm, title)
        canvas.drawRightString(landscape(A4)[0] - 9 * mm, 6 * mm, f"Pagina {document.page}")
        canvas.restoreState()

    return _draw


def _total_flight_hours_rows(report: dict, styles: dict) -> list[list]:
    rows: list[list] = [
        [
            _pdf_cell("TRIPULANTE", styles["group"]),
            _pdf_cell("DIA NORMAL", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("DOMINGO/FERIADO", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("VALOR TOTAL\nHORAS (R$)", styles["group"]),
        ],
        [
            _pdf_cell("", styles["header"]),
            _pdf_cell("DIU", styles["header"]),
            _pdf_cell("VALOR (R$)", styles["header"]),
            _pdf_cell("NOT", styles["header"]),
            _pdf_cell("VALOR (R$)", styles["header"]),
            _pdf_cell("DIU", styles["header"]),
            _pdf_cell("VALOR (R$)", styles["header"]),
            _pdf_cell("NOT", styles["header"]),
            _pdf_cell("VALOR (R$)", styles["header"]),
            _pdf_cell("", styles["header"]),
        ],
    ]
    for line in report.get("linhas") or []:
        rows.append(
            [
                _pdf_cell(line.get("nome_tripulante"), styles["body"]),
                _pdf_cell(line.get("dia_normal_diu_hhmm"), styles["body_center"]),
                _pdf_cell(_pdf_money(line.get("dia_normal_diu_valor"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(line.get("dia_normal_not_hhmm"), styles["body_center"]),
                _pdf_cell(_pdf_money(line.get("dia_normal_not_valor"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(line.get("domingo_feriado_diu_hhmm"), styles["body_center"]),
                _pdf_cell(_pdf_money(line.get("domingo_feriado_diu_valor"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(line.get("domingo_feriado_not_hhmm"), styles["body_center"]),
                _pdf_cell(_pdf_money(line.get("domingo_feriado_not_valor"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(line.get("valor_total_horas"), dash_when_zero=True), styles["body_money"]),
            ]
        )
    if len(rows) == 2:
        rows.append(
            [
                _pdf_cell("Nenhum tripulante encontrado para os filtros.", styles["body"]),
                *[_pdf_cell("-", styles["body_center"]) for _ in range(9)],
            ]
        )
    return rows


def _total_flight_hours_table(report: dict, styles: dict):
    rows = _total_flight_hours_rows(report, styles)
    table = Table(
        rows,
        colWidths=[68 * mm, 15 * mm, 24 * mm, 15 * mm, 24 * mm, 15 * mm, 24 * mm, 15 * mm, 24 * mm, 31 * mm],
        repeatRows=2,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
                ("SPAN", (0, 0), (0, 1)),
                ("SPAN", (1, 0), (4, 0)),
                ("SPAN", (5, 0), (8, 0)),
                ("SPAN", (9, 0), (9, 1)),
                ("BACKGROUND", (0, 0), (0, 1), colors.HexColor("#f4f7fb")),
                ("BACKGROUND", (1, 0), (4, 0), colors.HexColor("#cbd7ee")),
                ("BACKGROUND", (5, 0), (8, 0), colors.HexColor("#f6dfaa")),
                ("BACKGROUND", (9, 0), (9, 1), colors.HexColor("#f5d8c7")),
                ("BACKGROUND", (1, 1), (2, 1), colors.HexColor("#dbe9cf")),
                ("BACKGROUND", (3, 1), (4, 1), colors.HexColor("#f4c4aa")),
                ("BACKGROUND", (5, 1), (6, 1), colors.HexColor("#dbe9cf")),
                ("BACKGROUND", (7, 1), (8, 1), colors.HexColor("#f4c4aa")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    return table


def _total_flight_hours_summary(report: dict, styles: dict):
    totals = report.get("totais") or {}
    rows = [
        [
            _pdf_cell("Fonte de dados", styles["header"]),
            _pdf_cell("Tripulantes", styles["header"]),
            _pdf_cell("Lancamentos", styles["header"]),
            _pdf_cell("Pendencias", styles["header"]),
            _pdf_cell("Total geral", styles["header"]),
        ],
        [
            _pdf_cell("Calculos horarios persistidos vigentes", styles["body"]),
            _pdf_cell(totals.get("tripulantes"), styles["body_center"]),
            _pdf_cell(totals.get("quantidade_lancamentos"), styles["body_center"]),
            _pdf_cell("Sim" if totals.get("possui_pendencias") else "Nao", styles["body_center"]),
            _pdf_cell(_pdf_money(totals.get("valor_total_horas")), styles["body_money"]),
        ],
    ]
    table = Table(rows, colWidths=[92 * mm, 30 * mm, 30 * mm, 30 * mm, 35 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _build_horas_totais_voadas_pdf(*, report: dict, actor_user_id: int, request_id: str, correlation_id: str) -> bytes:
    styles = _pdf_styles()
    context = report.get("contexto") or {}
    competencia = _text(context.get("competencia"))
    funcao = _text(context.get("funcao"))
    title = f"RELATÓRIO DE HORAS TOTAIS VOADAS - {_funcao_plural(funcao)}"
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=8 * mm,
        bottomMargin=10 * mm,
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        title=f"{title} {competencia}",
        author="Brasil Vida",
        subject="Relatorio financeiro de horas totais voadas",
    )
    header = Table(
        [
            [
                Paragraph('<font color="#21274f">Brasil</font><font color="#bc2035">vida</font>', styles["brand"]),
                Paragraph(title, styles["title"]),
                Paragraph(_competencia_label(competencia), styles["competencia"]),
            ],
            [
                Paragraph("Fonte: calculos horarios persistidos vigentes. Preview nao entra no fechamento financeiro.", styles["small"]),
                Paragraph(
                    f"Org: {escape(_text(context.get('org_id'), '-'))} | Request: {escape(_text(request_id, '-'))} | Correlation: {escape(_text(correlation_id, '-'))}",
                    styles["small"],
                ),
                Paragraph(f"Usuario: {actor_user_id or '-'}", styles["small"]),
            ],
        ],
        colWidths=[56 * mm, 174 * mm, 41 * mm],
        hAlign="LEFT",
    )
    header.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
                ("SPAN", (1, 1), (1, 1)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, 0), colors.white),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#eef2ff")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story = [
        header,
        Spacer(1, 3 * mm),
        _total_flight_hours_table(report, styles),
        Spacer(1, 3 * mm),
        _total_flight_hours_summary(report, styles),
    ]
    footer = _pdf_page_footer("Relatorio de Horas Totais Voadas")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    value = buffer.getvalue()
    buffer.close()
    return value


def _assert_exportable(report: dict) -> None:
    totals = report.get("totais") or {}
    if not totals.get("possui_pendencias"):
        return
    pendencias = []
    for line in report.get("linhas") or []:
        for pending in line.get("pendencias") or []:
            if isinstance(pending, dict):
                pendencias.append(pending)
    raise DomainValidationError(
        _UNPERSISTED_HOURLY_MESSAGE,
        status=409,
        code="finance_total_flight_hours_pending_calculations",
        details={"pendencias": pendencias},
    )


def exportar_horas_totais_voadas_pdf(
    *,
    competencia: str,
    funcao: str,
    org_id: str | None = None,
    incluir_zerados: bool = True,
    actor_user_id: int,
    request_id: str = "",
    correlation_id: str = "",
    source_endpoint: str = "/api/v1/financeiro/horas-totais-voadas.pdf",
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    report = consolidar_horas_totais_voadas(
        competencia=competencia,
        funcao=funcao,
        org_id=org_id,
        incluir_zerados=incluir_zerados,
        db=resolved_db,
    )
    _assert_exportable(report)
    context = report.get("contexto") or {}
    resolved_competencia = _text(context.get("competencia"))
    resolved_funcao = _text(context.get("funcao"))
    pdf_bytes = _build_horas_totais_voadas_pdf(
        report=report,
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    pdf_bytes = _assert_pdf_bytes_complete(pdf_bytes, code="finance_total_flight_hours_pdf")
    filename = f"relatorio-horas-totais-voadas-{_funcao_plural(resolved_funcao).lower()}-{resolved_competencia}.pdf"
    record_audit_event(
        resolved_db,
        entidade="finance_export",
        entidade_id=0,
        acao="finance.export.generated",
        realizado_por=actor_user_id,
        payload_anterior=None,
        payload_novo={
            "metadata": {
                "report_version": _REPORT_VERSION,
                "source_endpoint": source_endpoint,
                "filename": filename,
                "mimetype": "application/pdf",
                "pdf_bytes": len(pdf_bytes),
                "filters": report.get("filters") or {},
                "record_count": len(report.get("linhas") or []),
                "totais": report.get("totais") or {},
            }
        },
        observacao=f"competencia={resolved_competencia}; funcao={resolved_funcao}; report=horas_totais_voadas",
    )
    resolved_db.commit()
    return {
        "content": pdf_bytes,
        "filename": filename,
        "mimetype": "application/pdf",
        "metadata": {
            "report_version": _REPORT_VERSION,
            "filters": report.get("filters") or {},
            "record_count": len(report.get("linhas") or []),
            "totais": report.get("totais") or {},
        },
    }
