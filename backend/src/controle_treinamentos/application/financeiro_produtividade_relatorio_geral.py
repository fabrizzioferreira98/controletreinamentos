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
from ..repositories.financeiro_calculos_produtividade import listar_calculos_produtividade

MONEY_QUANTIZER = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")
_MAX_REPORT_ROWS = 10000
_PDF_EOF_MARKER = b"%%EOF"
_PDF_EOF_SCAN_BYTES = 4096
_REPORT_VERSION = "finance-productivity-general-report-v1"
_TITLE_PREFIX = "RELAT\u00d3RIO GERAL DE PRODUTIVIDADE"
_UNEXPORTABLE_MESSAGE = (
    "Existem inconsistencias na memoria de produtividade persistida. "
    "Recalcule a grade antes de exportar o relatorio financeiro."
)
_EXCLUDED_STATUSES = {
    "obsoleto",
    "cancelado",
    "cancelada",
    "excluido",
    "excluida",
    "exclu\u00eddo",
    "exclu\u00edda",
    "preview",
    "rascunho",
}
_MONTHS_PT = {
    1: "JANEIRO",
    2: "FEVEREIRO",
    3: "MAR\u00c7O",
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


def _money_text(value) -> str:
    return format(_money(value), "f")


def _pdf_money(value, *, dash_when_zero: bool = False) -> str:
    amount = _money(value)
    if dash_when_zero and amount == ZERO_MONEY:
        return "-"
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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


def _validate_competencia(competencia: str) -> str:
    value = _text(competencia)
    if len(value) != 7 or value[4] != "-":
        raise DomainValidationError(
            "Competencia invalida. Use o formato YYYY-MM.",
            code="finance_productivity_general_report_invalid_competence",
            details={"field": "competencia", "expected_format": "YYYY-MM", "value": value or None},
        )
    year, month = value.split("-", 1)
    if not (year.isdigit() and month.isdigit() and 1 <= int(month) <= 12):
        raise DomainValidationError(
            "Competencia invalida. Use o formato YYYY-MM.",
            code="finance_productivity_general_report_invalid_competence",
            details={"field": "competencia", "expected_format": "YYYY-MM", "value": value or None},
        )
    return value


def _validate_funcao(funcao: str) -> str:
    value = _text(funcao).lower()
    if value not in FINANCE_CREW_FUNCTIONS:
        raise DomainValidationError(
            "Funcao operacional invalida.",
            code="finance_productivity_general_report_invalid_funcao",
            details={"field": "funcao", "allowed": list(FINANCE_CREW_FUNCTIONS), "value": value or None},
        )
    return value


def _normalize_category(value) -> str | None:
    text = _text(value).upper().replace("CATEGORIA", "").strip()
    return text or None


def _category_a_or_b(value) -> str | None:
    normalized = _normalize_category(value)
    return normalized if normalized in {"A", "B"} else None


def _display_category(row: dict) -> str:
    return (
        _category_a_or_b(row.get("tripulante_categoria_operacional"))
        or _category_a_or_b(row.get("categoria_aplicavel"))
        or ""
    )


def _is_default_report_eligible(row: dict) -> bool:
    return bool(_display_category(row) or _bool(row.get("tripulante_elegivel_adicional_excepcional")))


def _validate_categoria(categoria: str | None) -> str | None:
    normalized = _normalize_category(categoria)
    if normalized in (None, ""):
        return None
    if normalized not in {"A", "B"}:
        raise DomainValidationError(
            "Categoria invalida.",
            code="finance_productivity_general_report_invalid_category",
            details={"field": "categoria", "allowed": ["A", "B"], "value": categoria},
        )
    return normalized


def _funcao_plural(funcao: str) -> str:
    normalized = _validate_funcao(funcao)
    return "COMANDANTES" if normalized == "comandante" else "COPILOTOS"


def _title(funcao: str) -> str:
    return f"{_TITLE_PREFIX} - {_funcao_plural(funcao)}"


def _competencia_label(competencia: str) -> str:
    year, month = _validate_competencia(competencia).split("-", 1)
    return f"{_MONTHS_PT[int(month)]}\n{year}"


def _is_excluded_row(row: dict, *, funcao: str, categoria: str | None) -> bool:
    if _text(row.get("funcao")).lower() != funcao:
        return True
    if categoria and _display_category(row) != categoria:
        return True
    if not categoria and not _is_default_report_eligible(row):
        return True
    status = _text(row.get("status"), "calculado").lower()
    if status in _EXCLUDED_STATUSES:
        return True
    if _bool(row.get("preview") or row.get("is_preview") or row.get("eh_preview")):
        return True
    return False


def _warnings_from_memory(memory: dict) -> list[dict]:
    warnings = memory.get("warnings") if isinstance(memory, dict) else []
    if not isinstance(warnings, list):
        return []
    return [item for item in warnings if isinstance(item, dict)]


def _row_pendencias(row: dict, *, components_total: Decimal, memory: dict) -> list[dict]:
    pendencias: list[dict] = []
    status = _text(row.get("status"), "calculado").lower()
    if status != "calculado":
        pendencias.append(
            {
                "code": "calculo_produtividade_status_nao_final",
                "message": "Calculo de produtividade persistido nao esta com status calculado.",
                "calculo_produtividade_id": _int(row.get("id")),
                "status": status,
            }
        )
    productivity = _money(row.get("produtividade_calculada"))
    if productivity != components_total:
        pendencias.append(
            {
                "code": "produtividade_apurada_difere_componentes_persistidos",
                "message": "Produtividade apurada persistida difere da soma dos componentes persistidos.",
                "calculo_produtividade_id": _int(row.get("id")),
                "produtividade_apurada": _money_text(productivity),
                "componentes": _money_text(components_total),
            }
        )
    memory_totals = memory.get("totals") if isinstance(memory, dict) else {}
    if isinstance(memory_totals, dict):
        persisted_total = _money(row.get("total_devido"))
        memory_total = _money(memory_totals.get("total_devido")) if "total_devido" in memory_totals else persisted_total
        if memory_total != persisted_total:
            pendencias.append(
                {
                    "code": "total_devido_difere_memoria_persistida",
                    "message": "Total devido da linha difere do total registrado na memoria persistida.",
                    "calculo_produtividade_id": _int(row.get("id")),
                    "total_devido": _money_text(persisted_total),
                    "total_memoria": _money_text(memory_total),
                }
            )
    return pendencias


def _item_from_row(row: dict, *, competencia: str, funcao: str) -> dict:
    memory = _json_value(row.get("memoria_calculo"), {})
    memory = memory if isinstance(memory, dict) else {}
    icao_sdea = _money(row.get("valor_icao"))
    instrutor = _money(row.get("valor_instrutor"))
    checador = _money(row.get("valor_checador"))
    missoes = _money(row.get("valor_missoes_categoria_a")) + _money(row.get("valor_missoes_categoria_b"))
    cobertura_base = _money(row.get("valor_cobertura_base"))
    pernoite_comum = _money(row.get("valor_pernoite_comum"))
    condicao_especial = _money(row.get("valor_excecao_palmas"))
    produtividade_apurada = _money(row.get("produtividade_calculada"))
    garantia_minima = _money(row.get("garantia_minima"))
    excedente = _money(row.get("excedente"))
    if "excedente" not in row or row.get("excedente") in (None, ""):
        memory_totals = memory.get("totals") if isinstance(memory, dict) else {}
        if isinstance(memory_totals, dict) and memory_totals.get("excedente") not in (None, ""):
            excedente = _money(memory_totals.get("excedente"))
        else:
            excedente = _money(max(produtividade_apurada - garantia_minima, ZERO_MONEY))
    total_produtividade = _money(row.get("total_devido"))
    components_total = (
        icao_sdea
        + instrutor
        + checador
        + missoes
        + cobertura_base
        + pernoite_comum
        + condicao_especial
    ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    warnings = _warnings_from_memory(memory)
    pendencias = _row_pendencias(row, components_total=components_total, memory=memory)
    return {
        "calculo_produtividade_id": _int(row.get("id")),
        "tripulante_id": _int(row.get("tripulante_id")),
        "nome": _text(row.get("tripulante_nome") or row.get("nome")),
        "funcao": funcao,
        "categoria": _display_category(row),
        "competencia": competencia,
        "icao_sdea": _money_text(icao_sdea),
        "instrutor": _money_text(instrutor),
        "checador": _money_text(checador),
        "missoes": _money_text(missoes),
        "cobertura_base": _money_text(cobertura_base),
        "pernoite_comum": _money_text(pernoite_comum),
        "condicao_especial": _money_text(condicao_especial),
        "produtividade_apurada": _money_text(produtividade_apurada),
        "garantia_minima": _money_text(garantia_minima),
        "excedente": _money_text(excedente),
        "total_produtividade": _money_text(total_produtividade),
        "status_calculo": _text(row.get("status"), "calculado"),
        "calculation_version": _text(row.get("calculation_version")),
        "warnings": warnings,
        "possui_pendencias": bool(pendencias),
        "pendencias": pendencias,
        "memoria_calculo": memory,
        "fonte_dados": "financeiro_calculos_produtividade_persistidos_vigentes",
    }


def _has_amount(item: dict) -> bool:
    for key in (
        "icao_sdea",
        "instrutor",
        "checador",
        "missoes",
        "cobertura_base",
        "pernoite_comum",
        "condicao_especial",
        "produtividade_apurada",
        "garantia_minima",
        "excedente",
        "total_produtividade",
    ):
        if _money(item.get(key)) != ZERO_MONEY:
            return True
    return False


def _totais(items: list[dict]) -> dict:
    keys = (
        "icao_sdea",
        "instrutor",
        "checador",
        "missoes",
        "cobertura_base",
        "pernoite_comum",
        "condicao_especial",
        "produtividade_apurada",
        "garantia_minima",
        "excedente",
        "total_produtividade",
    )
    totals = {key: _money_text(sum((_money(item.get(key)) for item in items), ZERO_MONEY)) for key in keys}
    totals.update(
        {
            "tripulantes": len(items),
            "calculos": len(items),
            "possui_pendencias": any(item.get("possui_pendencias") for item in items),
            "linhas_com_pendencias": sum(1 for item in items if item.get("possui_pendencias")),
        }
    )
    return totals


def consolidar_relatorio_geral_produtividade(
    *,
    competencia: str,
    funcao: str,
    org_id: str | None = None,
    incluir_zerados: bool = True,
    categoria: str | None = None,
    db=None,
) -> dict:
    resolved_competencia = _validate_competencia(competencia)
    resolved_funcao = _validate_funcao(funcao)
    resolved_categoria = _validate_categoria(categoria)
    resolved_org_id = _resolve_org_id(org_id)
    resolved_db = _resolve_db(db)

    rows = listar_calculos_produtividade(
        resolved_db,
        competencia=resolved_competencia,
        funcao=resolved_funcao,
        org_id=resolved_org_id,
        limit=_MAX_REPORT_ROWS,
        offset=0,
    )
    items = []
    pendencias: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for row in rows:
        if _is_excluded_row(row, funcao=resolved_funcao, categoria=resolved_categoria):
            continue
        key = (_int(row.get("tripulante_id")), resolved_funcao)
        if key in seen:
            pendencias.append(
                {
                    "code": "calculo_produtividade_duplicado",
                    "message": "Mais de um calculo de produtividade vigente foi retornado para o tripulante e funcao.",
                    "tripulante_id": key[0],
                    "funcao": resolved_funcao,
                }
            )
            continue
        seen.add(key)
        item = _item_from_row(row, competencia=resolved_competencia, funcao=resolved_funcao)
        if incluir_zerados or item.get("possui_pendencias") or _has_amount(item):
            items.append(item)
            pendencias.extend(item.get("pendencias") or [])

    items.sort(key=lambda item: (_text(item.get("nome")).upper(), _int(item.get("tripulante_id"))))
    totals = _totais(items)
    if pendencias:
        totals["possui_pendencias"] = True
        totals["linhas_com_pendencias"] = sum(1 for item in items if item.get("possui_pendencias"))
    return {
        "competencia": resolved_competencia,
        "funcao": resolved_funcao,
        "titulo": _title(resolved_funcao),
        "totais": totals,
        "items": items,
        "pendencias": pendencias,
        "contexto": {
            "competencia": resolved_competencia,
            "funcao": resolved_funcao,
            "org_id": resolved_org_id,
            "categoria": resolved_categoria,
            "fonte_de_verdade": "financeiro_calculos_produtividade",
            "usa_preview": False,
            "report_version": _REPORT_VERSION,
        },
        "filters": {
            "competencia": resolved_competencia,
            "funcao": resolved_funcao,
            "org_id": resolved_org_id,
            "categoria": resolved_categoria,
            "incluir_zerados": bool(incluir_zerados),
        },
    }


def _pdf_styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "ProdutividadeGeralBrand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=colors.HexColor("#21274f"),
        ),
        "title": ParagraphStyle(
            "ProdutividadeGeralTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "competencia": ParagraphStyle(
            "ProdutividadeGeralCompetencia",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
        ),
        "group": ParagraphStyle(
            "ProdutividadeGeralGroup",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6,
            leading=7,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "header": ParagraphStyle(
            "ProdutividadeGeralHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=5.4,
            leading=6.4,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "body": ParagraphStyle(
            "ProdutividadeGeralBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=5.5,
            leading=6.4,
            textColor=colors.HexColor("#111827"),
        ),
        "body_center": ParagraphStyle(
            "ProdutividadeGeralBodyCenter",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=5.5,
            leading=6.4,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "body_money": ParagraphStyle(
            "ProdutividadeGeralBodyMoney",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=5.5,
            leading=6.4,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#0f5f7f"),
        ),
        "small": ParagraphStyle(
            "ProdutividadeGeralSmall",
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


def _productivity_rows(report: dict, styles: dict) -> list[list]:
    rows: list[list] = [
        [
            _pdf_cell("IDENTIFICACAO", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("COMPONENTES", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("FECHAMENTO", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
            _pdf_cell("", styles["group"]),
        ],
        [
            _pdf_cell("TRIPULANTE", styles["header"]),
            _pdf_cell("CAT.", styles["header"]),
            _pdf_cell("FUNCAO", styles["header"]),
            _pdf_cell("ICAO/SDEA", styles["header"]),
            _pdf_cell("INSTRUTOR", styles["header"]),
            _pdf_cell("CHECADOR", styles["header"]),
            _pdf_cell("MISSOES", styles["header"]),
            _pdf_cell("COBERTURA", styles["header"]),
            _pdf_cell("PERNOITE", styles["header"]),
            _pdf_cell("ESPECIAL", styles["header"]),
            _pdf_cell("APURADA", styles["header"]),
            _pdf_cell("PISO", styles["header"]),
            _pdf_cell("EXCEDENTE", styles["header"]),
            _pdf_cell("TOTAL", styles["header"]),
        ],
    ]
    for item in report.get("items") or []:
        rows.append(
            [
                _pdf_cell(item.get("nome"), styles["body"]),
                _pdf_cell(item.get("categoria") or "-", styles["body_center"]),
                _pdf_cell(item.get("funcao"), styles["body_center"]),
                _pdf_cell(_pdf_money(item.get("icao_sdea"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("instrutor"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("checador"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("missoes"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("cobertura_base"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("pernoite_comum"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("condicao_especial"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("produtividade_apurada"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("garantia_minima"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("excedente"), dash_when_zero=True), styles["body_money"]),
                _pdf_cell(_pdf_money(item.get("total_produtividade"), dash_when_zero=True), styles["body_money"]),
            ]
        )
    if len(rows) == 2:
        rows.append(
            [
                _pdf_cell("Nenhum tripulante encontrado para os filtros.", styles["body"]),
                *[_pdf_cell("-", styles["body_center"]) for _ in range(13)],
            ]
        )
    return rows


def _productivity_table(report: dict, styles: dict):
    rows = _productivity_rows(report, styles)
    table = Table(
        rows,
        colWidths=[48 * mm, 9 * mm, 17 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 19 * mm, 18 * mm, 18 * mm, 21 * mm],
        repeatRows=2,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
                ("SPAN", (0, 0), (2, 0)),
                ("SPAN", (3, 0), (9, 0)),
                ("SPAN", (10, 0), (13, 0)),
                ("BACKGROUND", (0, 0), (2, 1), colors.HexColor("#f4f7fb")),
                ("BACKGROUND", (3, 0), (9, 0), colors.HexColor("#cbd7ee")),
                ("BACKGROUND", (3, 1), (9, 1), colors.HexColor("#dbe9cf")),
                ("BACKGROUND", (10, 0), (13, 0), colors.HexColor("#f5d8c7")),
                ("BACKGROUND", (10, 1), (13, 1), colors.HexColor("#f8e2d5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1.6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    return table


def _productivity_summary(report: dict, styles: dict):
    totals = report.get("totais") or {}
    rows = [
        [
            _pdf_cell("Fonte de dados", styles["header"]),
            _pdf_cell("Tripulantes", styles["header"]),
            _pdf_cell("Pendencias", styles["header"]),
            _pdf_cell("Apurada", styles["header"]),
            _pdf_cell("Total geral", styles["header"]),
        ],
        [
            _pdf_cell("Calculos de produtividade persistidos vigentes", styles["body"]),
            _pdf_cell(totals.get("tripulantes"), styles["body_center"]),
            _pdf_cell("Sim" if totals.get("possui_pendencias") else "Nao", styles["body_center"]),
            _pdf_cell(_pdf_money(totals.get("produtividade_apurada")), styles["body_money"]),
            _pdf_cell(_pdf_money(totals.get("total_produtividade")), styles["body_money"]),
        ],
    ]
    table = Table(rows, colWidths=[98 * mm, 28 * mm, 28 * mm, 34 * mm, 36 * mm], hAlign="LEFT")
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


def _build_relatorio_geral_produtividade_pdf(
    *,
    report: dict,
    actor_user_id: int,
    request_id: str,
    correlation_id: str,
) -> bytes:
    styles = _pdf_styles()
    context = report.get("contexto") or {}
    competencia = _text(context.get("competencia"))
    title = _text(report.get("titulo")) or _title(_text(context.get("funcao")))
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
        subject="Relatorio financeiro geral de produtividade",
    )
    header = Table(
        [
            [
                Paragraph('<font color="#21274f">Brasil</font><font color="#bc2035">vida</font>', styles["brand"]),
                Paragraph(title, styles["title"]),
                Paragraph(_competencia_label(competencia), styles["competencia"]),
            ],
            [
                Paragraph("Fonte: calculos de produtividade persistidos vigentes. Preview nao entra no fechamento financeiro.", styles["small"]),
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
        _productivity_table(report, styles),
        Spacer(1, 3 * mm),
        _productivity_summary(report, styles),
    ]
    footer = _pdf_page_footer("Relatorio Geral de Produtividade")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    value = buffer.getvalue()
    buffer.close()
    return value


def _assert_exportable(report: dict) -> None:
    if not (report.get("pendencias") or (report.get("totais") or {}).get("possui_pendencias")):
        return
    raise DomainValidationError(
        _UNEXPORTABLE_MESSAGE,
        status=409,
        code="finance_productivity_general_report_pending_calculations",
        details={"pendencias": report.get("pendencias") or []},
    )


def exportar_relatorio_geral_produtividade_pdf(
    *,
    competencia: str,
    funcao: str,
    org_id: str | None = None,
    incluir_zerados: bool = True,
    categoria: str | None = None,
    actor_user_id: int,
    request_id: str = "",
    correlation_id: str = "",
    source_endpoint: str = "/api/v1/financeiro/produtividade/relatorio-geral.pdf",
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    report = consolidar_relatorio_geral_produtividade(
        competencia=competencia,
        funcao=funcao,
        org_id=org_id,
        incluir_zerados=incluir_zerados,
        categoria=categoria,
        db=resolved_db,
    )
    _assert_exportable(report)
    context = report.get("contexto") or {}
    resolved_competencia = _text(context.get("competencia"))
    resolved_funcao = _text(context.get("funcao"))
    pdf_bytes = _build_relatorio_geral_produtividade_pdf(
        report=report,
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    pdf_bytes = _assert_pdf_bytes_complete(pdf_bytes, code="finance_productivity_general_report_pdf")
    filename = f"relatorio-geral-produtividade-{_funcao_plural(resolved_funcao).lower()}-{resolved_competencia}.pdf"
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
                "record_count": len(report.get("items") or []),
                "totais": report.get("totais") or {},
            }
        },
        observacao=f"competencia={resolved_competencia}; funcao={resolved_funcao}; report=produtividade_geral",
    )
    resolved_db.commit()
    return {
        "content": pdf_bytes,
        "filename": filename,
        "mimetype": "application/pdf",
        "metadata": {
            "report_version": _REPORT_VERSION,
            "filters": report.get("filters") or {},
            "record_count": len(report.get("items") or []),
            "totais": report.get("totais") or {},
        },
    }
