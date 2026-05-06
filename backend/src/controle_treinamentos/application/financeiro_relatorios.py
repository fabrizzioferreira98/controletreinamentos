from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from html import escape
from io import BytesIO
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..audit import record_audit_event
from ..contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
from ..core.domain_errors import DomainNotFoundError, DomainValidationError
from ..db import get_db
from .financeiro_jornada_query import (
    consultar_calculos_horarios_jornada as listar_calculos_horarios,
    consultar_calculos_produtividade_jornada as listar_calculos_produtividade,
    consultar_participacoes_produtividade_jornada as listar_participacoes_produtividade_por_competencia,
    consultar_tripulante_relatorio as fetch_tripulante_detail,
)
from .financeiro_competencias import (
    PERIOD_SNAPSHOT_VERSION,
    avaliar_elegibilidade_fechamento_real_snapshot,
    detalhar_competencia_financeira,
)

FINANCE_REPORT_VERSION = "finance-period-report-v1"
FINANCE_INDIVIDUAL_REPORT_VERSION = "finance-individual-report-v1"
_PDF_EOF_MARKER = b"%%EOF"
_PDF_EOF_SCAN_BYTES = 4096
_UNPERSISTED_HOURLY_MESSAGE = (
    "Existem lançamentos sem cálculo persistido. Recalcule a grade antes de exportar o relatório financeiro."
)


class _NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(total_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, total_pages: int):
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawRightString(198 * mm, 8 * mm, f"Pagina {self.getPageNumber()} de {total_pages}")


def _resolve_db(db=None):
    return db if db is not None else get_db()


def _resolve_org_id(org_id: str | None) -> str:
    return (org_id or "").strip() or FINANCE_ORG_SCOPE_DEFAULT


def _assert_pdf_bytes_complete(content: bytes, *, code: str) -> bytes:
    data = bytes(content or b"")
    if not data:
        raise DomainValidationError("PDF gerado vazio.", code=f"{code}_empty", status=500)
    if not data.startswith(b"%PDF"):
        raise DomainValidationError("PDF gerado sem assinatura valida.", code=f"{code}_invalid_signature", status=500)
    if _PDF_EOF_MARKER not in data[-_PDF_EOF_SCAN_BYTES:]:
        raise DomainValidationError("PDF gerado incompleto.", code=f"{code}_incomplete", status=500)
    return data


def _money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _format_money(value) -> str:
    return f"R$ {_money(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _text(value, fallback: str = "-") -> str:
    normalized = str(value or "").strip()
    return normalized or fallback


def _bool_text(value) -> str:
    return "Sim" if bool(value) else "Nao"


def _compact_json_text(value, *, limit: int = 220) -> str:
    if value in (None, "", [], {}):
        return "-"
    text = str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return f"{text[: limit - 3]}..." if len(text) > limit else text


def _paragraph(value, style):
    return Paragraph(escape(_text(value)), style)


def _period_mode(period: dict) -> str:
    return "fechamento" if str(period.get("status") or "").lower() == "fechada" else "previa"


def _period_notice(mode: str) -> str:
    if mode == "fechamento":
        return "FECHAMENTO - SNAPSHOT CONGELADO"
    return "PREVIA / QA - NAO USAR PARA FECHAMENTO REAL"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "FinanceReportTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_RIGHT,
        ),
        "subtitle": ParagraphStyle(
            "FinanceReportSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#475569"),
            alignment=TA_RIGHT,
        ),
        "section": ParagraphStyle(
            "FinanceReportSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=7,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "FinanceReportBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.5,
            textColor=colors.HexColor("#172033"),
        ),
        "body_center": ParagraphStyle(
            "FinanceReportBodyCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.5,
            textColor=colors.HexColor("#172033"),
            alignment=TA_CENTER,
        ),
        "small": ParagraphStyle(
            "FinanceReportSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#475569"),
        ),
        "notice": ParagraphStyle(
            "FinanceReportNotice",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#92400e"),
            alignment=TA_CENTER,
        ),
    }


def _table(rows, col_widths, *, header=True):
    table = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d9e6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
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


def _header_story(story: list, *, competencia: str, period: dict, mode: str, generated_at: str, actor_user_id: int):
    styles = _styles()
    story.append(
        _table(
            [
                [
                    Paragraph("<b>Brasil Vida Taxi Aereo</b><br/>Relatorio Financeiro da Competencia", styles["body"]),
                    Paragraph(f"Competencia {escape(competencia)}<br/>{escape(_period_notice(mode))}", styles["title"]),
                ],
                [
                    Paragraph(f"Gerado em: {escape(generated_at)}<br/>Usuario gerador: {actor_user_id or '-'}", styles["small"]),
                    Paragraph(f"Status: {escape(_text(period.get('status'), 'aberta'))}", styles["subtitle"]),
                ],
            ],
            [70 * mm, 110 * mm],
            header=False,
        )
    )
    story.append(Spacer(1, 3 * mm))


def _summary_story(story: list, snapshot: dict, totals: dict, styles: dict):
    story.append(Paragraph("Resumo", styles["section"]))
    rows = [
        ["Indicador", "Valor"],
        ["Total bonificacao horaria", _format_money(totals.get("total_horario"))],
        ["Total produtividade", _format_money(totals.get("total_produtividade"))],
        ["Total geral", _format_money(totals.get("total_geral"))],
        ["Quantidade de missoes", str(totals.get("mission_count") or len(snapshot.get("missoes_operacionais") or []))],
        [
            "Quantidade de tripulantes",
            str(len({item.get("tripulante_id") for item in snapshot.get("calculos_produtividade") or [] if item.get("tripulante_id")})),
        ],
        ["Pendencias/divergencias", str(totals.get("divergence_count") or len(snapshot.get("divergencias") or []))],
    ]
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [85 * mm, 45 * mm]))


def _missions_story(story: list, missions: list[dict], styles: dict):
    story.append(Paragraph("Missoes Operacionais", styles["section"]))
    rows = [["Data", "Voo", "Aeronave", "Categoria", "Comandante", "Copiloto", "Status"]]
    for mission in missions[:120]:
        rows.append(
            [
                _text(mission.get("data_missao")),
                _text(mission.get("cavok_numero_voo")),
                _text(mission.get("aeronave_id")),
                _text(mission.get("categoria_financeira_aeronave")),
                _text(mission.get("comandante_tripulante_id")),
                _text(mission.get("copiloto_tripulante_id")),
                _text(mission.get("status")),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Nenhuma missao operacional persistida.", "-", "-", "-", "-", "-"])
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [22 * mm, 28 * mm, 24 * mm, 20 * mm, 27 * mm, 27 * mm, 24 * mm]))


def _hourly_story(story: list, calculations: list[dict], styles: dict):
    story.append(Paragraph("Bonificacao Horaria", styles["section"]))
    rows = [["Missao", "Tripulante", "Funcao", "Jornada", "Noturno real", "Hora noturna conv.", "Total", "Status"]]
    for item in calculations[:160]:
        rows.append(
            [
                _text(item.get("mission_id") or item.get("missao_operacional_id")),
                _text(item.get("tripulante", {}).get("nome") or item.get("tripulante_id")),
                _text(item.get("funcao")),
                _text(item.get("jornada_total_minutos")),
                _text(item.get("minutos_noturnos_reais")),
                _text(item.get("horas_noturnas_convertidas")),
                _format_money(item.get("total")),
                _text(item.get("status")),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Nenhum calculo horario persistido.", "-", "-", "-", "-", "-", "-"])
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [18 * mm, 35 * mm, 22 * mm, 20 * mm, 23 * mm, 27 * mm, 22 * mm, 22 * mm]))


def _productivity_story(story: list, calculations: list[dict], styles: dict):
    story.append(Paragraph("Produtividade / Funcao", styles["section"]))
    rows = [["Tripulante", "Funcao", "Categoria", "Produtividade", "Garantia minima", "Excedente", "Total devido", "Status"]]
    for item in calculations[:160]:
        rows.append(
            [
                _text(item.get("tripulante", {}).get("nome") or item.get("tripulante_id")),
                _text(item.get("funcao")),
                _text(item.get("categoria_aplicavel")),
                _format_money(item.get("produtividade_calculada")),
                _format_money(item.get("garantia_minima")),
                _format_money(_productivity_excedente(item)),
                _format_money(item.get("total_devido")),
                _text(item.get("status")),
            ]
        )
    if len(rows) == 1:
        rows.append(["Nenhum calculo de produtividade persistido.", "-", "-", "-", "-", "-", "-", "-"])
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [34 * mm, 21 * mm, 22 * mm, 27 * mm, 27 * mm, 23 * mm, 26 * mm, 16 * mm]))


def _parameters_story(story: list, snapshot: dict, styles: dict):
    story.append(Paragraph("Parametros usados", styles["section"]))
    parameters = snapshot.get("parametros_usados") or snapshot.get("parametros_vigentes") or []
    rows = [["ID", "Tipo", "Funcao", "Categoria", "Unidade", "Valor"]]
    for item in parameters[:180]:
        rows.append(
            [
                _text(item.get("parameter_id") or item.get("id")),
                _text(item.get("tipo")),
                _text(item.get("funcao")),
                _text(item.get("categoria")),
                _text(item.get("unidade")),
                _text(item.get("valor")),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Nenhum parametro usado foi registrado.", "-", "-", "-", "-"])
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [18 * mm, 50 * mm, 28 * mm, 30 * mm, 28 * mm, 25 * mm]))


def _release_gate_story(story: list, snapshot: dict, styles: dict, *, mode: str):
    story.append(Paragraph("Release gate", styles["section"]))
    release_gate = snapshot.get("release_gate") or {}
    blocking_parameters = release_gate.get("blocking_parameters") or []
    rows = [
        ["Indicador", "Valor"],
        ["Modo do relatorio", "Fechamento" if mode == "fechamento" else "Previa"],
        ["Ambiente", _text(release_gate.get("environment"), "-")],
        ["Elegivel para fechamento real", _bool_text(release_gate.get("release_eligible"))],
        ["Parametros bloqueantes", str(len(blocking_parameters))],
        ["Next action", _text(release_gate.get("next_action"), "-")],
    ]
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [58 * mm, 72 * mm]))
    if not blocking_parameters:
        return
    detail_rows = [["Parametro", "Classificacao", "Motivos"]]
    for item in blocking_parameters[:120]:
        detail_rows.append(
            [
                _text(item.get("parameter_id") or item.get("id")),
                _text(item.get("classification") or item.get("gov_class") or item.get("status")),
                _compact_json_text(item.get("reasons") or item.get("motivos")),
            ]
        )
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in detail_rows], [26 * mm, 34 * mm, 70 * mm]))


def _memory_story(story: list, snapshot: dict, styles: dict):
    story.append(Paragraph("Memoria de calculo resumida", styles["section"]))
    rows = [["Origem", "Referencia", "Resumo"]]
    for item in (snapshot.get("calculos_horarios") or [])[:40]:
        rows.append(["Horaria", f"calc {item.get('id')}", _compact_json_text(item.get("memoria_calculo"))])
    for item in (snapshot.get("calculos_produtividade") or [])[:40]:
        rows.append(["Produtividade", f"calc {item.get('id')}", _compact_json_text(item.get("memoria_calculo"))])
    if len(rows) == 1:
        rows.append(["-", "-", "Nenhuma memoria de calculo persistida."])
    story.append(_table([[_paragraph(cell, styles["small"]) for cell in row] for row in rows], [26 * mm, 28 * mm, 126 * mm]))


def _divergences_story(story: list, divergences: list[dict], styles: dict):
    story.append(Paragraph("Divergencias / Pendencias", styles["section"]))
    rows = [["Severidade", "Codigo", "Mensagem", "Entidade", "Status"]]
    for item in divergences[:120]:
        rows.append(
            [
                _text(item.get("severity")),
                _text(item.get("code")),
                _text(item.get("message")),
                _text(item.get("entity_type")),
                _text(item.get("status")),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "sem_pendencias", "Nenhuma divergencia persistida para a competencia.", "-", "-"])
    story.append(_table([[_paragraph(cell, styles["body"]) for cell in row] for row in rows], [24 * mm, 32 * mm, 78 * mm, 28 * mm, 22 * mm]))


def _footer_story(story: list, *, request_id: str, correlation_id: str, calculation_version: str, mode: str):
    styles = _styles()
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            escape(
                " | ".join(
                    [
                        f"mode={mode}",
                        f"request_id={request_id or '-'}",
                        f"correlation_id={correlation_id or '-'}",
                        f"calculation_version={calculation_version or PERIOD_SNAPSHOT_VERSION}",
                        f"report_version={FINANCE_REPORT_VERSION}",
                    ]
                )
            ),
            styles["small"],
        )
    )


def _build_pdf(*, competencia: str, data: dict, actor_user_id: int, request_id: str, correlation_id: str) -> bytes:
    period = data.get("period") or {}
    snapshot = data.get("snapshot") or period.get("snapshot") or {}
    totals = data.get("totals") or snapshot.get("totals") or {}
    mode = _period_mode(period)
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    styles = _styles()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        leftMargin=11 * mm,
        rightMargin=11 * mm,
        title=f"Relatorio Financeiro {competencia}",
        author="Brasil Vida Taxi Aereo",
        subject="Relatorio financeiro da competencia",
    )
    story: list = []
    _header_story(story, competencia=competencia, period=period, mode=mode, generated_at=generated_at, actor_user_id=actor_user_id)
    story.append(Paragraph(_period_notice(mode), styles["notice"]))
    story.append(Spacer(1, 2 * mm))
    _summary_story(story, snapshot, totals, styles)
    _missions_story(story, snapshot.get("missoes_operacionais") or [], styles)
    _hourly_story(story, snapshot.get("calculos_horarios") or [], styles)
    _productivity_story(story, snapshot.get("calculos_produtividade") or [], styles)
    _parameters_story(story, snapshot, styles)
    _release_gate_story(story, snapshot, styles, mode=mode)
    _memory_story(story, snapshot, styles)
    _divergences_story(story, data.get("divergences") or snapshot.get("divergencias") or [], styles)
    _footer_story(
        story,
        request_id=request_id,
        correlation_id=correlation_id,
        calculation_version=snapshot.get("snapshot_version") or PERIOD_SNAPSHOT_VERSION,
        mode=mode,
    )
    document.build(story, canvasmaker=_NumberedCanvas)
    value = buffer.getvalue()
    buffer.close()
    return value


def gerar_relatorio_financeiro_competencia_pdf(
    competencia: str,
    *,
    org_id: str | None = None,
    actor_user_id: int = 0,
    request_id: str = "",
    correlation_id: str = "",
    source_endpoint: str = "/api/v1/financeiro/competencias/{competencia}/relatorio.pdf",
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    data = detalhar_competencia_financeira(competencia, org_id=resolved_org_id, db=resolved_db)
    period = data.get("period") or {}
    snapshot = data.get("snapshot") or period.get("snapshot") or {}
    totals = data.get("totals") or snapshot.get("totals") or {}
    mode = _period_mode(period)
    release_gate = avaliar_elegibilidade_fechamento_real_snapshot(
        db=resolved_db,
        competencia=competencia,
        org_id=resolved_org_id,
        snapshot=snapshot,
        strict=(mode == "fechamento"),
    )
    snapshot["release_gate"] = release_gate
    pdf_bytes = _build_pdf(
        competencia=competencia,
        data=data,
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    record_count = (
        len(snapshot.get("missoes_operacionais") or [])
        + len(snapshot.get("calculos_horarios") or [])
        + len(snapshot.get("calculos_produtividade") or [])
        + len(snapshot.get("divergencias") or [])
    )
    metadata = {
        "event_name": "finance.export.generated",
        "org_id": resolved_org_id,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "actor_user_id": actor_user_id,
        "entity_type": "finance_export",
        "entity_id": period.get("id") or 0,
        "permission": "finance:exports:create",
        "source_endpoint": source_endpoint,
        "competencia": competencia,
        "format": "pdf",
        "filters": {"competencia": competencia, "mode": mode},
        "record_count": record_count,
        "release_eligibility": {
            "environment": release_gate.get("environment"),
            "release_eligible": bool(release_gate.get("release_eligible")),
            "blocking_parameters_count": len(release_gate.get("blocking_parameters") or []),
        },
        "report_version": FINANCE_REPORT_VERSION,
        "calculation_version": snapshot.get("snapshot_version") or PERIOD_SNAPSHOT_VERSION,
    }
    record_audit_event(
        resolved_db,
        entidade="finance_export",
        entidade_id=int(period.get("id") or 0),
        acao="finance.export.generated",
        realizado_por=actor_user_id,
        payload_anterior=None,
        payload_novo={
            "metadata": metadata,
            "totals": totals,
            "pdf_bytes": len(pdf_bytes),
        },
        observacao=f"competencia={competencia}; format=pdf; mode={mode}",
    )
    resolved_db.commit()
    filename = f"relatorio-financeiro-{competencia}-{mode}.pdf"
    return {
        "content": pdf_bytes,
        "filename": filename,
        "mimetype": "application/pdf",
        "mode": mode,
        "metadata": metadata,
    }


class _IndividualReportCanvas(Canvas):
    def __init__(self, *args, report_header: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._report_header = report_header or {}
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_header_footer(self, total_pages: int):
        width, height = self._pagesize
        self.setFillColor(colors.HexColor("#f8fafc"))
        self.rect(8 * mm, height - 28 * mm, width - 16 * mm, 20 * mm, fill=1, stroke=0)
        self.setStrokeColor(colors.HexColor("#dbe4ef"))
        self.setLineWidth(0.5)
        self.line(8 * mm, height - 28 * mm, width - 8 * mm, height - 28 * mm)

        self.setFont("Helvetica-Bold", 9)
        self.setFillColor(colors.HexColor("#b91c1c"))
        self.drawString(11 * mm, height - 14 * mm, _text(self._report_header.get("system"), "Treinamentos Brasil Vida"))
        self.setFont("Helvetica", 7.2)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(11 * mm, height - 19 * mm, _text(self._report_header.get("document_notice"), "Documento gerado pelo sistema"))

        self.setFont("Helvetica-Bold", 13)
        self.setFillColor(colors.HexColor("#0f172a"))
        self.drawCentredString(width / 2, height - 14 * mm, _text(self._report_header.get("title")))
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawCentredString(width / 2, height - 20 * mm, f"Competencia {_text(self._report_header.get('competencia_label'))}")

        self.setFont("Helvetica", 7.2)
        self.setFillColor(colors.HexColor("#334155"))
        self.drawRightString(width - 11 * mm, height - 13 * mm, f"Emissao {_text(self._report_header.get('generated_at'))}")
        self.drawRightString(width - 11 * mm, height - 18 * mm, f"Pagina {self.getPageNumber()} de {total_pages}")
        self.drawRightString(width - 11 * mm, height - 23 * mm, f"Tripulante {_text(self._report_header.get('tripulante_nome'))}")

        self.setStrokeColor(colors.HexColor("#dbe4ef"))
        self.line(8 * mm, 10 * mm, width - 8 * mm, 10 * mm)
        self.setFont("Helvetica", 6.8)
        self.setFillColor(colors.HexColor("#64748b"))
        footer = " | ".join(
            [
                f"report_version={FINANCE_INDIVIDUAL_REPORT_VERSION}",
                f"request_id={_text(self._report_header.get('request_id'))}",
                f"correlation_id={_text(self._report_header.get('correlation_id'))}",
            ]
        )
        self.drawString(11 * mm, 6 * mm, footer)


def _individual_styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "FinanceIndividualBrand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=10,
            textColor=colors.HexColor("#e21d48"),
        ),
        "title": ParagraphStyle(
            "FinanceIndividualTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#0f172a"),
        ),
        "subtitle": ParagraphStyle(
            "FinanceIndividualSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=12,
            textColor=colors.HexColor("#475569"),
        ),
        "header_label": ParagraphStyle(
            "FinanceIndividualHeaderLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9.2,
            textColor=colors.HexColor("#334155"),
        ),
        "header_value": ParagraphStyle(
            "FinanceIndividualHeaderValue",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.3,
            leading=9,
            textColor=colors.HexColor("#0f172a"),
        ),
        "section": ParagraphStyle(
            "FinanceIndividualSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=5,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "FinanceIndividualBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.9,
            leading=8.2,
            textColor=colors.HexColor("#172033"),
            alignment=TA_LEFT,
        ),
        "body_center": ParagraphStyle(
            "FinanceIndividualBodyCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.9,
            leading=8.2,
            textColor=colors.HexColor("#172033"),
            alignment=TA_CENTER,
        ),
        "body_center_inverse": ParagraphStyle(
            "FinanceIndividualBodyCenterInverse",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9.2,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "body_right": ParagraphStyle(
            "FinanceIndividualBodyRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.9,
            leading=8.2,
            textColor=colors.HexColor("#172033"),
            alignment=TA_RIGHT,
        ),
        "small": ParagraphStyle(
            "FinanceIndividualSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.2,
            leading=7.3,
            textColor=colors.HexColor("#475569"),
        ),
        "kpi_label": ParagraphStyle(
            "FinanceIndividualKpiLabel",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6,
            leading=7,
            textColor=colors.HexColor("#64748b"),
        ),
        "kpi_value": ParagraphStyle(
            "FinanceIndividualKpiValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=10.2,
            textColor=colors.HexColor("#0f172a"),
        ),
        "notice": ParagraphStyle(
            "FinanceIndividualNotice",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.6,
            leading=8,
            textColor=colors.HexColor("#475569"),
        ),
    }


def _cell(value, style):
    text = escape(_text(value)).replace("\n", "<br/>")
    return Paragraph(text, style)


def _individual_table(rows, col_widths, *, header=True, total_row_index: int | None = None):
    table = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0, hAlign="LEFT")
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
    if total_row_index is not None:
        style.extend(
            [
                ("BACKGROUND", (0, total_row_index), (-1, total_row_index), colors.HexColor("#e0f2fe")),
                ("FONTNAME", (0, total_row_index), (-1, total_row_index), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(style))
    return table


def _individual_report_subtitle(data: dict) -> str:
    report_kind = "bonificacao horaria" if data["tipo"] == "horaria" else "produtividade"
    return f"Competencia {_format_competencia_label(data['competencia'])} - relatorio individual de {report_kind}"


def _individual_header_story(story: list, data: dict, styles: dict, *, generated_text: str):
    left = Table(
        [
            [Paragraph("Treinamentos Brasil Vida", styles["brand"])],
            [Paragraph(_text(data.get("title")), styles["title"])],
            [Paragraph(_individual_report_subtitle(data), styles["subtitle"])],
        ],
        colWidths=[214 * mm],
    )
    left.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    right = Table(
        [
            [Paragraph("Emissao", styles["header_label"])],
            [Paragraph(generated_text, styles["header_value"])],
            [Paragraph("Documento gerado pelo sistema", styles["header_label"])],
        ],
        colWidths=[55 * mm],
    )
    right.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    header = Table([[left, right]], colWidths=[216 * mm, 63 * mm], rowHeights=[56 * mm])
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#d4deea")),
                ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.HexColor("#d4deea")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#d4deea")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 3 * mm))


def _individual_page_footer(title: str, emitted_at: str):
    def _draw(canvas, document):
        canvas.saveState()
        width, _height = landscape(A4)
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.setLineWidth(0.3)
        canvas.line(10 * mm, 10 * mm, width - 10 * mm, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(10 * mm, 6 * mm, f"Treinamentos Brasil Vida - {title} | Emissao {emitted_at}")
        canvas.drawRightString(width - 10 * mm, 6 * mm, f"Pagina {document.page}")
        canvas.restoreState()

    return _draw


def _individual_summary_table(rows, widths, spans: list[tuple[tuple[int, int], tuple[int, int]]] | None = None):
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f5597")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]
    for start, end in spans or []:
        style.append(("SPAN", start, end))
    table.setStyle(TableStyle(style))
    return table


def _safe_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _safe_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_date_br(value) -> str:
    parsed = _safe_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else _text(value)


def _format_datetime_br(value) -> str:
    parsed = _safe_datetime(value)
    return parsed.strftime("%d/%m/%Y %H:%M:%S") if parsed else _text(value)


def _format_time_br(value) -> str:
    parsed = _safe_datetime(value)
    if parsed:
        return parsed.strftime("%H:%M")
    text = str(value or "").strip()
    return text[:5] if re.match(r"^\d{2}:\d{2}", text) else _text(text)


def _format_competencia_label(competencia: str) -> str:
    months = (
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
    )
    text = str(competencia or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})$", text)
    if not match:
        return _text(text)
    year, month = match.groups()
    return f"{months[int(month) - 1]}/{year}"


def _minutes(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _format_minutes_hhmm(value) -> str:
    total = _minutes(value)
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 60:02d}:{total % 60:02d}"


def _format_decimal_hours_hhmm(value) -> str:
    try:
        hours = Decimal(str(value or "0"))
    except Exception:
        hours = Decimal("0")
    minutes_total = int((hours * Decimal("60")).quantize(Decimal("1")))
    return _format_minutes_hhmm(minutes_total)


def _slugify_filename(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or "tripulante"


def _normalize_status(value) -> str:
    return str(value or "").strip().lower()


def _is_obsolete(row: dict) -> bool:
    return _normalize_status(row.get("status")) == "obsoleto"


def _is_cancelled_mission(row: dict) -> bool:
    mission = row.get("missao") or {}
    status = _normalize_status(row.get("missao_status") or mission.get("status"))
    return status in {"cancelada", "excluida", "excluída"} or bool(row.get("deleted_at") or mission.get("deleted_at"))


def _is_payable(row: dict) -> bool:
    return _normalize_status(row.get("status")) == "calculado" and not _is_obsolete(row) and not _is_cancelled_mission(row)


def _unpersisted_hourly_rows(rows: list[dict]) -> list[dict]:
    pending = []
    for row in rows:
        if _is_payable(row):
            continue
        if _is_obsolete(row) or _is_cancelled_mission(row):
            continue
        pending.append(row)
    return pending


def _assert_no_unpersisted_hourly_rows(rows: list[dict], *, filters: dict) -> None:
    pending = _unpersisted_hourly_rows(rows)
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
                    "calculo_id": item.get("id"),
                    "missao_operacional_id": item.get("missao_operacional_id") or item.get("mission_id"),
                    "tripulante_id": item.get("tripulante_id"),
                    "funcao": item.get("funcao"),
                    "status": item.get("status"),
                }
                for item in pending[:20]
            ],
        },
    )


def _memory_warnings(row: dict) -> list:
    memory = row.get("memoria_calculo") or {}
    if not isinstance(memory, dict):
        return []
    warnings = memory.get("warnings") or memory.get("alertas") or []
    return warnings if isinstance(warnings, list) else [warnings]


def _memory_totals(row: dict) -> dict:
    memory = row.get("memoria_calculo") or {}
    if not isinstance(memory, dict):
        return {}
    totals = memory.get("totals") or {}
    return totals if isinstance(totals, dict) else {}


def _hourly_memory_minutes(row: dict, key: str, fallback: int = 0) -> int:
    totals = _memory_totals(row)
    if key in totals:
        return _minutes(totals.get(key))
    return fallback


def _hourly_night_duration_minutes(row: dict) -> Decimal | None:
    memory = row.get("memoria_calculo") or {}
    parameters = []
    if isinstance(memory, dict):
        parameters.extend(memory.get("parameters") or [])
    parameters.extend(row.get("parametros_usados") or [])
    for item in parameters:
        if not isinstance(item, dict) or _text(item.get("tipo")) != "duracao_hora_noturna_minutos":
            continue
        try:
            duration = Decimal(str(item.get("valor") or "0"))
        except Exception:
            duration = Decimal("0")
        if duration > 0:
            return duration
    return None


def _hourly_reduced_minutes_from_raw(row: dict, raw_minutes: int) -> int:
    raw_minutes = _minutes(raw_minutes)
    if raw_minutes <= 0:
        return 0
    duration = _hourly_night_duration_minutes(row)
    if duration:
        reduced_hours = Decimal(raw_minutes) / duration
        return int((reduced_hours * Decimal("60")).quantize(Decimal("1")))
    return 0


def _hourly_reduced_minutes(row: dict, key: str, fallback: int = 0) -> int:
    raw_minutes = _hourly_memory_minutes(row, key, fallback)
    reduced = _hourly_reduced_minutes_from_raw(row, raw_minutes)
    if reduced > 0:
        return reduced
    return _minutes(row.get("horas_noturnas_convertidas"))


def _hourly_step_intermediate(row: dict, rule_key: str) -> dict:
    memory = row.get("memoria_calculo") or {}
    steps = memory.get("steps") if isinstance(memory, dict) else []
    for step in steps or []:
        if not isinstance(step, dict) or _text(step.get("rule_key")) != rule_key:
            continue
        result = step.get("resultado_intermediario")
        return result if isinstance(result, dict) else {}
    return {}


def _hourly_pos_minutes(row: dict, key: str) -> int:
    intermediate = _hourly_step_intermediate(row, "pre_pos_jornada")
    if key in intermediate:
        return _minutes(intermediate.get(key))
    pos_minutes = _minutes(row.get("minutos_pos"))
    if key == "normal_minutos_pos" and not bool(row.get("domingo_feriado")):
        return pos_minutes
    if key == "especial_minutos_pos" and bool(row.get("domingo_feriado")):
        return pos_minutes
    return 0


def _alert_text(row: dict) -> str:
    alerts = []
    if _is_obsolete(row):
        alerts.append("calculo obsoleto")
    if _is_cancelled_mission(row):
        alerts.append("missao cancelada")
    if _normalize_status(row.get("status")) not in {"", "calculado"}:
        alerts.append(_text(row.get("status")))
    for warning in _memory_warnings(row)[:2]:
        if isinstance(warning, dict):
            alerts.append(_text(warning.get("message") or warning.get("code") or warning))
        else:
            alerts.append(_text(warning))
    return "; ".join(dict.fromkeys(alerts)) or "-"


def _parameter_text(parameters, *, limit: int = 4) -> str:
    if not isinstance(parameters, list) or not parameters:
        return "Parametros persistidos nao informados no calculo."
    parts = []
    for item in parameters[:limit]:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("tipo") or item.get("parameter_id"))
        value = _text(item.get("valor"))
        unit = _text(item.get("unidade"), "")
        parts.append(f"{label}: {value} {unit}".strip())
    return "; ".join(parts) or "Parametros persistidos nao informados no calculo."


def _filter_individual_rows(rows: list[dict], *, incluir_obsoletos: bool, status: str | None, report_type: str) -> list[dict]:
    normalized_status = _normalize_status(status)
    if normalized_status == "obsoleto" and not incluir_obsoletos:
        raise DomainValidationError(
            "Calculos obsoletos exigem incluir_obsoletos=true.",
            code="finance_individual_report_obsolete_requires_flag",
            details={"field": "incluir_obsoletos", "tipo": report_type},
        )
    filtered = []
    for row in rows:
        if not incluir_obsoletos and _is_obsolete(row):
            continue
        if not incluir_obsoletos and _is_cancelled_mission(row):
            continue
        filtered.append(row)
    return filtered


def _ensure_tripulante_for_report(db, tripulante_id: int) -> dict:
    tripulante = fetch_tripulante_detail(db, tripulante_id=int(tripulante_id))
    if not tripulante:
        raise DomainNotFoundError(
            "Tripulante nao encontrado.",
            code="finance_individual_report_tripulante_not_found",
            details={"tripulante_id": int(tripulante_id)},
        )
    return tripulante


def _hourly_report_data(
    db,
    *,
    competencia: str,
    tripulante_id: int,
    funcao: str | None,
    status: str | None,
    incluir_obsoletos: bool,
    org_id: str,
) -> dict:
    rows = listar_calculos_horarios(
        db,
        org_id=org_id,
        competencia=competencia,
        tripulante_id=tripulante_id,
        funcao=funcao,
        status=status,
        incluir_obsoletos=incluir_obsoletos,
        limit=1000,
        offset=0,
    )
    display_rows = _filter_individual_rows(rows, incluir_obsoletos=incluir_obsoletos, status=status, report_type="horaria")
    if not display_rows:
        raise DomainNotFoundError(
            "Nenhum calculo horario vigente encontrado para o tripulante na competencia.",
            code="finance_individual_report_no_hourly_data",
            details={"competencia": competencia, "tripulante_id": tripulante_id, "funcao": funcao},
        )
    if not incluir_obsoletos:
        _assert_no_unpersisted_hourly_rows(
            display_rows,
            filters={
                "tipo": "horaria",
                "competencia": competencia,
                "tripulante_id": tripulante_id,
                "funcao": funcao,
                "status": status,
            },
        )
    tripulante = _ensure_tripulante_for_report(db, tripulante_id)
    payable_rows = [row for row in display_rows if _is_payable(row)]
    normal_rows = [row for row in payable_rows if not bool(row.get("domingo_feriado"))]
    holiday_rows = [row for row in payable_rows if bool(row.get("domingo_feriado"))]
    normal_minutos_diurnos = sum(
        _hourly_memory_minutes(
            row,
            "normal_minutos_diurnos",
            _minutes(row.get("minutos_diurnos")) if not bool(row.get("domingo_feriado")) else 0,
        )
        for row in payable_rows
    )
    normal_minutos_noturnos = sum(
        _hourly_memory_minutes(
            row,
            "normal_minutos_noturnos",
            _minutes(row.get("minutos_noturnos")) if not bool(row.get("domingo_feriado")) else 0,
        )
        for row in payable_rows
    )
    holiday_minutos_diurnos = sum(
        _hourly_memory_minutes(
            row,
            "especial_minutos_diurnos",
            _minutes(row.get("minutos_diurnos")) if bool(row.get("domingo_feriado")) else 0,
        )
        for row in payable_rows
    )
    holiday_minutos_noturnos = sum(
        _hourly_memory_minutes(
            row,
            "especial_minutos_noturnos",
            _minutes(row.get("minutos_noturnos")) if bool(row.get("domingo_feriado")) else 0,
        )
        for row in payable_rows
    )
    normal_minutos_noturnos_reduzidos = sum(
        _hourly_reduced_minutes(
            row,
            "normal_minutos_noturnos",
            _minutes(row.get("minutos_noturnos")) if not bool(row.get("domingo_feriado")) else 0,
        )
        for row in payable_rows
    )
    holiday_minutos_noturnos_reduzidos = sum(
        _hourly_reduced_minutes(
            row,
            "especial_minutos_noturnos",
            _minutes(row.get("minutos_noturnos")) if bool(row.get("domingo_feriado")) else 0,
        )
        for row in payable_rows
    )
    normal_minutos_pos = sum((_hourly_pos_minutes(row, "normal_minutos_pos") for row in payable_rows), 0)
    holiday_minutos_pos = sum((_hourly_pos_minutes(row, "especial_minutos_pos") for row in payable_rows), 0)
    normal_minutos_pos_reduzidos = sum(
        (_hourly_reduced_minutes_from_raw(row, _hourly_pos_minutes(row, "normal_minutos_pos")) for row in payable_rows),
        0,
    )
    holiday_minutos_pos_reduzidos = sum(
        (_hourly_reduced_minutes_from_raw(row, _hourly_pos_minutes(row, "especial_minutos_pos")) for row in payable_rows),
        0,
    )
    valor_adicional_noturno = sum((_money(row.get("valor_adicional_noturno")) for row in payable_rows), Decimal("0"))
    valor_pre = sum((_money(row.get("valor_pre")) for row in payable_rows), Decimal("0"))
    valor_pos = sum((_money(row.get("valor_pos")) for row in payable_rows), Decimal("0"))
    holiday_valor_diurno = sum((_money(row.get("valor_domingo_feriado_diurno")) for row in payable_rows), Decimal("0"))
    holiday_valor_noturno = sum((_money(row.get("valor_domingo_feriado_noturno")) for row in payable_rows), Decimal("0"))
    totals = {
        "rows": len(display_rows),
        "payable_rows": len(payable_rows),
        "obsoletos": len([row for row in display_rows if _is_obsolete(row)]),
        "canceladas": len([row for row in display_rows if _is_cancelled_mission(row)]),
        "alertas": sum(1 for row in display_rows if _alert_text(row) != "-"),
        "domingo_feriado": len(holiday_rows),
        "jornada_minutos": sum(_minutes(row.get("jornada_total_minutos")) for row in payable_rows),
        "minutos_diurnos": sum(_minutes(row.get("minutos_diurnos")) for row in payable_rows),
        "minutos_noturnos": sum(_minutes(row.get("minutos_noturnos")) for row in payable_rows),
        "hora_reduzida_decimal": sum((Decimal(str(row.get("horas_noturnas_convertidas") or "0")) for row in payable_rows), Decimal("0")),
        "normal_minutos_diurnos": normal_minutos_diurnos,
        "normal_minutos_noturnos": normal_minutos_noturnos,
        "normal_minutos_noturnos_reduzidos": normal_minutos_noturnos_reduzidos,
        "normal_minutos_pos": normal_minutos_pos,
        "normal_minutos_pos_reduzidos": normal_minutos_pos_reduzidos,
        "normal_minutos_noturnos_remuneraveis_reduzidos": normal_minutos_noturnos_reduzidos + normal_minutos_pos_reduzidos,
        "normal_total": valor_adicional_noturno + valor_pre + valor_pos,
        "holiday_minutos_diurnos": holiday_minutos_diurnos,
        "holiday_minutos_noturnos": holiday_minutos_noturnos,
        "holiday_minutos_noturnos_reduzidos": holiday_minutos_noturnos_reduzidos,
        "holiday_minutos_pos": holiday_minutos_pos,
        "holiday_minutos_pos_reduzidos": holiday_minutos_pos_reduzidos,
        "holiday_minutos_noturnos_remuneraveis_reduzidos": holiday_minutos_noturnos_reduzidos + holiday_minutos_pos_reduzidos,
        "holiday_valor_diurno": holiday_valor_diurno,
        "holiday_valor_noturno": holiday_valor_noturno,
        "valor_adicional_noturno": valor_adicional_noturno,
        "valor_pre": valor_pre,
        "valor_pos": valor_pos,
        "total": sum((_money(row.get("total")) for row in payable_rows), Decimal("0")),
    }
    totals["valor_normal"] = totals["normal_total"]
    totals["valor_domingo_feriado_total"] = totals["holiday_valor_diurno"] + totals["holiday_valor_noturno"]
    return {
        "tipo": "horaria",
        "title": "Relatorio Individual de Bonificacao Horaria",
        "competencia": competencia,
        "tripulante": tripulante,
        "funcao": funcao or _text(display_rows[0].get("funcao")),
        "rows": display_rows,
        "payable_rows": payable_rows,
        "totals": totals,
        "parameters": display_rows[0].get("parametros_usados") or [],
    }


def _productivity_contagens(calculation: dict) -> dict:
    memory = calculation.get("memoria_calculo") or {}
    inputs = memory.get("inputs") if isinstance(memory, dict) else {}
    if not isinstance(inputs, dict):
        return {}
    return inputs.get("contagens_agregadas") or inputs.get("contagens") or {}


def _productivity_excedente(calculation: dict) -> Decimal:
    if calculation.get("excedente") not in (None, ""):
        return _money(calculation.get("excedente"))
    memory = calculation.get("memoria_calculo") or {}
    totals = memory.get("totals") if isinstance(memory, dict) else {}
    if isinstance(totals, dict) and totals.get("excedente") not in (None, ""):
        return _money(totals.get("excedente"))
    return max(_money(calculation.get("produtividade_calculada")) - _money(calculation.get("garantia_minima")), Decimal("0.00"))


def _category_token(value) -> str:
    text = str(value or "").strip().upper()
    if "B" in text:
        return "B"
    if "A" in text:
        return "A"
    return text


def _divide_money(total, count) -> Decimal:
    count = int(count or 0)
    if count <= 0:
        return Decimal("0.00")
    return (_money(total) / Decimal(count)).quantize(Decimal("0.01"))


def _common_overnight_quantity(mission: dict) -> int:
    if bool(mission.get("cobertura_base")):
        return 0
    return max(0, _minutes(mission.get("quantidade_pernoites")) - 1)


def _coverage_overnight_quantity(mission: dict) -> int:
    if not bool(mission.get("cobertura_base")):
        return 0
    return max(1, _minutes(mission.get("quantidade_pernoites")))


def _productivity_rule_for_mission(calculation: dict, mission: dict) -> dict:
    contagens = _productivity_contagens(calculation)
    if bool(mission.get("cobertura_base")):
        quantity = _coverage_overnight_quantity(mission)
        unit_value = _divide_money(calculation.get("valor_cobertura_base"), contagens.get("cobertura_base"))
        return {
            "key": "cobertura_base",
            "label": "Cobertura de base",
            "quantity": quantity,
            "unit_value": unit_value,
            "total_value": (unit_value * Decimal(quantity)).quantize(Decimal("0.01")),
        }
    common_quantity = _common_overnight_quantity(mission)
    if common_quantity > 0:
        unit_value = _divide_money(
            calculation.get("valor_pernoite_comum"),
            contagens.get("pernoite_comum_sem_cobertura"),
        )
        return {
            "key": "pernoite_comum_sem_cobertura",
            "label": "Pernoite comum",
            "quantity": common_quantity,
            "unit_value": unit_value,
            "total_value": (unit_value * Decimal(common_quantity)).quantize(Decimal("0.01")),
        }
    if "palmas" in str(mission.get("operacao_especial") or "").lower():
        unit_value = _divide_money(
            calculation.get("valor_excecao_palmas"),
            contagens.get("excecao_palmas_turbohelice") or contagens.get("excecao_palmas"),
        )
        return {
            "key": "excecao_palmas",
            "label": "Excecao Palmas",
            "quantity": 1,
            "unit_value": unit_value,
            "total_value": unit_value,
        }
    category = _category_token(mission.get("categoria_financeira_aeronave"))
    if category == "B":
        unit_value = _divide_money(calculation.get("valor_missoes_categoria_b"), contagens.get("categoria_b"))
        return {
            "key": "missao_categoria_b",
            "label": "Missao categoria B",
            "quantity": 1,
            "unit_value": unit_value,
            "total_value": unit_value,
        }
    unit_value = _divide_money(calculation.get("valor_missoes_categoria_a"), contagens.get("categoria_a"))
    return {
        "key": "missao_categoria_a",
        "label": "Missao categoria A",
        "quantity": 1,
        "unit_value": unit_value,
        "total_value": unit_value,
    }


def _parameter_display(parameters: list[dict], tipo: str, *, funcao: str | None = None, categoria: str | None = None) -> str:
    for item in parameters or []:
        if _text(item.get("tipo")) != tipo:
            continue
        item_funcao = _text(item.get("funcao"))
        item_categoria = _text(item.get("categoria"))
        if funcao is not None and item_funcao and item_funcao != funcao:
            continue
        if categoria is not None and item_categoria and _category_token(item_categoria) != _category_token(categoria):
            continue
        parts = [tipo]
        if item_funcao:
            parts.append(item_funcao)
        if item_categoria:
            parts.append(f"cat. {item_categoria}")
        parts.append(_format_money(item.get("valor")))
        return " / ".join(parts)
    return tipo


def _component_unit(total: Decimal, quantity: int) -> Decimal:
    if quantity <= 0:
        return Decimal("0.00")
    return (total / Decimal(quantity)).quantize(Decimal("0.01"))


def _component_calc_text(quantity: int, unit_value: Decimal, *, mode: str = "multiplicacao") -> str:
    if mode == "garantia":
        return "max(produtividade apurada, garantia minima)"
    if mode == "excedente":
        return "max(produtividade apurada - garantia minima, 0)"
    if mode == "total":
        return "total a pagar conforme politica"
    return f"{quantity} x {_format_money(unit_value)}"


def _productivity_parameter_breakdown(data: dict) -> list[dict]:
    rows = data.get("payable_rows") or data.get("rows") or []
    funcao = _text(data.get("funcao"))
    parameters = data.get("parameters") or []
    totals = data.get("totals") or {}
    aggregate = {
        "valor_icao": {"quantity": 0, "total": Decimal("0.00")},
        "valor_instrutor": {"quantity": 0, "total": Decimal("0.00")},
        "valor_checador": {"quantity": 0, "total": Decimal("0.00")},
        "valor_missoes_categoria_a": {"quantity": 0, "total": Decimal("0.00")},
        "valor_missoes_categoria_b": {"quantity": 0, "total": Decimal("0.00")},
        "valor_cobertura_base": {"quantity": 0, "total": Decimal("0.00")},
        "valor_pernoite_comum": {"quantity": 0, "total": Decimal("0.00")},
        "valor_excecao_palmas": {"quantity": 0, "total": Decimal("0.00")},
    }
    for row in rows:
        contagens = _productivity_contagens(row)
        aggregate["valor_icao"]["quantity"] += 1 if _money(row.get("valor_icao")) > 0 else 0
        aggregate["valor_instrutor"]["quantity"] += 1 if _money(row.get("valor_instrutor")) > 0 else 0
        aggregate["valor_checador"]["quantity"] += 1 if _money(row.get("valor_checador")) > 0 else 0
        aggregate["valor_missoes_categoria_a"]["quantity"] += _minutes(contagens.get("categoria_a"))
        aggregate["valor_missoes_categoria_b"]["quantity"] += _minutes(contagens.get("categoria_b"))
        aggregate["valor_cobertura_base"]["quantity"] += _minutes(contagens.get("cobertura_base"))
        aggregate["valor_pernoite_comum"]["quantity"] += _minutes(contagens.get("pernoite_comum_sem_cobertura"))
        aggregate["valor_excecao_palmas"]["quantity"] += _minutes(
            contagens.get("excecao_palmas_turbohelice") or contagens.get("excecao_palmas")
        )
        for key in aggregate:
            aggregate[key]["total"] += _money(row.get(key))

    specs = [
        ("ICAO/SDEA", "icao_sdea", None, "valor_icao"),
        ("Instrutor", "instrutor", None, "valor_instrutor"),
        ("Checador", "checador", None, "valor_checador"),
        ("Missoes Categoria A", "missao_categoria_a", "A", "valor_missoes_categoria_a"),
        ("Missoes Categoria B", "missao_categoria_b", "B", "valor_missoes_categoria_b"),
        ("Cobertura de base", "cobertura_base", None, "valor_cobertura_base"),
        ("Pernoite comum sem cobertura", "pernoite_comum_sem_cobertura", None, "valor_pernoite_comum"),
        ("Palmas turbo-helice", "excecao_palmas_turbohelice", "PALMAS_TURBOHELICE", "valor_excecao_palmas"),
    ]
    breakdown = []
    for label, tipo, categoria, value_key in specs:
        quantity = int(aggregate[value_key]["quantity"])
        total = _money(aggregate[value_key]["total"])
        unit_value = _component_unit(total, quantity)
        breakdown.append(
            {
                "item": label,
                "quantidade": quantity,
                "valor_unitario": unit_value,
                "valor_total": total,
                "calculo": _component_calc_text(quantity, unit_value),
                "parametro": _parameter_display(parameters, tipo, funcao=funcao, categoria=categoria),
            }
        )
    produtividade = _money(totals.get("produtividade_calculada"))
    garantia = _money(totals.get("garantia_minima"))
    excedente = _money(totals.get("excedente"))
    total = _money(totals.get("total"))
    breakdown.extend(
        [
            {
                "item": "Produtividade apurada",
                "quantidade": "-",
                "valor_unitario": produtividade,
                "valor_total": produtividade,
                "calculo": "soma dos componentes acima",
                "parametro": "memoria persistida",
            },
            {
                "item": "Garantia minima",
                "quantidade": 1 if garantia > 0 else 0,
                "valor_unitario": garantia,
                "valor_total": garantia,
                "calculo": _component_calc_text(1, garantia, mode="garantia"),
                "parametro": _parameter_display(parameters, "garantia_minima", funcao=funcao),
            },
            {
                "item": "Excedente",
                "quantidade": "-",
                "valor_unitario": excedente,
                "valor_total": excedente,
                "calculo": _component_calc_text(0, excedente, mode="excedente"),
                "parametro": "calculado",
            },
            {
                "item": "Total a pagar",
                "quantidade": "-",
                "valor_unitario": total,
                "valor_total": total,
                "calculo": _component_calc_text(0, total, mode="total"),
                "parametro": "resultado final",
            },
        ]
    )
    return breakdown


def _productivity_parameters_story(story: list, data: dict, styles: dict):
    story.append(Paragraph("Parametros aplicados na produtividade", styles["section"]))
    rows = [["Parametro", "Quantidade", "Valor unitario", "Calculo", "Total", "Fonte"]]
    for item in _productivity_parameter_breakdown(data):
        rows.append(
            [
                _text(item.get("item")),
                _text(item.get("quantidade")),
                _format_money(item.get("valor_unitario")),
                _text(item.get("calculo")),
                _format_money(item.get("valor_total")),
                _text(item.get("parametro")),
            ]
        )
    story.append(
        _individual_table(
            [[_cell(cell, styles["body"]) for cell in row] for row in rows],
            [43 * mm, 24 * mm, 34 * mm, 76 * mm, 34 * mm, 68 * mm],
        )
    )


def _productivity_report_data(
    db,
    *,
    competencia: str,
    tripulante_id: int,
    funcao: str | None,
    status: str | None,
    incluir_obsoletos: bool,
    org_id: str,
) -> dict:
    calculations = listar_calculos_produtividade(
        db,
        org_id=org_id,
        competencia=competencia,
        tripulante_id=tripulante_id,
        funcao=funcao,
        status=status,
        incluir_obsoletos=incluir_obsoletos,
        limit=1000,
        offset=0,
    )
    display_rows = _filter_individual_rows(calculations, incluir_obsoletos=incluir_obsoletos, status=status, report_type="produtividade")
    if not display_rows:
        raise DomainNotFoundError(
            "Nenhum calculo de produtividade vigente encontrado para o tripulante na competencia.",
            code="finance_individual_report_no_productivity_data",
            details={"competencia": competencia, "tripulante_id": tripulante_id, "funcao": funcao},
        )
    tripulante = _ensure_tripulante_for_report(db, tripulante_id)
    mission_rows = [
        row
        for row in listar_participacoes_produtividade_por_competencia(
            db,
            competencia=competencia,
            org_id=org_id,
            tripulante_id=tripulante_id,
            funcao=funcao,
        )
    ]
    payable_rows = [row for row in display_rows if _is_payable(row)]
    totals = {
        "calculos": len(display_rows),
        "payable_rows": len(payable_rows),
        "missions": len(mission_rows),
        "missoes_calculadas": len(mission_rows) if payable_rows else 0,
        "missoes_bloqueadas": 0 if payable_rows else len(mission_rows),
        "alertas": sum(1 for row in display_rows if _alert_text(row) != "-"),
        "produtividade_calculada": sum((_money(row.get("produtividade_calculada")) for row in payable_rows), Decimal("0")),
        "garantia_minima": sum((_money(row.get("garantia_minima")) for row in payable_rows), Decimal("0")),
        "excedente": sum((_productivity_excedente(row) for row in payable_rows), Decimal("0")),
        "total": sum((_money(row.get("total_devido")) for row in payable_rows), Decimal("0")),
        "valor_pernoite_comum": sum((_money(row.get("valor_pernoite_comum")) for row in payable_rows), Decimal("0")),
        "valor_adicional": sum(
            (
                _money(row.get("valor_icao"))
                + _money(row.get("valor_instrutor"))
                + _money(row.get("valor_checador"))
                + _money(row.get("valor_cobertura_base"))
                + _money(row.get("valor_pernoite_comum"))
                + _money(row.get("valor_excecao_palmas"))
                for row in payable_rows
            ),
            Decimal("0"),
        ),
    }
    totals["valor_base"] = totals["produtividade_calculada"] - totals["valor_adicional"]
    if totals["valor_base"] < Decimal("0"):
        totals["valor_base"] = Decimal("0")
    return {
        "tipo": "produtividade",
        "title": "Relatorio Individual de Produtividade",
        "competencia": competencia,
        "tripulante": tripulante,
        "funcao": funcao or _text(display_rows[0].get("funcao")),
        "rows": display_rows,
        "missions": mission_rows,
        "payable_rows": payable_rows,
        "totals": totals,
        "parameters": display_rows[0].get("parametros_usados") or [],
    }


def _identification_story(story: list, data: dict, styles: dict):
    totals = data["totals"]
    tripulante = data["tripulante"]
    if data["tipo"] == "horaria":
        metric_rows = [
            ("Total geral", _format_money(totals["total"])),
            ("Lancamentos", str(totals["rows"])),
            ("Hora reduzida", _format_decimal_hours_hhmm(totals["hora_reduzida_decimal"])),
            ("Valor normal", _format_money(totals["valor_normal"])),
            ("Excecoes/alertas", str(totals["alertas"])),
            ("Domingos/feriados", str(totals["domingo_feriado"])),
        ]
    else:
        metric_rows = [
            ("Total geral", _format_money(totals["total"])),
            ("Missoes consideradas", str(totals["missions"])),
            ("Missoes calculadas", str(totals["missoes_calculadas"])),
            ("Missoes bloqueadas", str(totals["missoes_bloqueadas"])),
            ("Produtividade base", _format_money(totals["valor_base"])),
            ("Produtividade adicional", _format_money(totals["valor_adicional"])),
            ("Garantia minima", _format_money(totals["garantia_minima"])),
            ("Excedente", _format_money(totals["excedente"])),
            ("Excecoes/alertas", str(totals["alertas"])),
        ]
    story.append(Paragraph("Contexto do relatorio individual", styles["section"]))
    rows = [
        [
            _cell("Competencia", styles["kpi_label"]),
            _cell(_format_competencia_label(data["competencia"]), styles["kpi_value"]),
            _cell("Tripulante", styles["kpi_label"]),
            _cell(_text(tripulante.get("nome")), styles["kpi_value"]),
            _cell("Funcao operacional", styles["kpi_label"]),
            _cell(_text(data.get("funcao")), styles["kpi_value"]),
        ]
    ]
    story.append(_individual_table(rows, [28 * mm, 64 * mm, 34 * mm, 64 * mm, 28 * mm, 61 * mm], header=False))
    kpi_rows = []
    current = []
    for label, value in metric_rows:
        current.extend([_cell(label, styles["kpi_label"]), _cell(value, styles["kpi_value"])])
        if len(current) == 6:
            kpi_rows.append(current)
            current = []
    if current:
        current.extend([_cell("", styles["kpi_label"]), _cell("", styles["kpi_value"])] * ((6 - len(current)) // 2))
        kpi_rows.append(current)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Indicadores financeiros", styles["section"]))
    story.append(_individual_table(kpi_rows, [32 * mm, 60 * mm, 32 * mm, 60 * mm, 32 * mm, 61 * mm], header=False))


def _bases_story(story: list, data: dict, styles: dict):
    story.append(Paragraph("Bases de calculo", styles["section"]))
    if data["tipo"] == "horaria":
        rows = [
            ["Campo", "Regra/parametros usados"],
            ["Funcao", _text(data.get("funcao"))],
            ["Adicional noturno", "Usa minutos noturnos reais e hora noturna reduzida persistidos no calculo vigente."],
            ["Domingo/feriado diurno", "Separado por flag domingo_feriado; nao soma calculo obsoleto ou missao cancelada."],
            ["Domingo/feriado noturno", "Valor proprio para horas noturnas em domingo/feriado, conforme parametros persistidos."],
            ["Regra de aplicacao em horas", "Horas e valores sao lidos dos calculos horarios persistidos; o relatorio nao recalcula a missao."],
            ["Observacoes", _parameter_text(data.get("parameters"))],
        ]
    else:
        rows = [
            ["Campo", "Regra/parametros usados"],
            ["Funcao", _text(data.get("funcao"))],
            [
                "Regra de produtividade",
                "Total a pagar usa max(produtividade apurada, garantia minima); excedente = max(produtividade apurada - garantia minima, 0).",
            ],
            ["SDEA/ICAO", "Pago somente quando o cadastro esta ativo e a validade cobre o ultimo dia da competencia."],
            ["Instrutor", "Pago somente quando a designacao possui vigencia sobreposta a competencia."],
            ["Checador", "Pago uma vez por competencia quando existe carta/designacao vigente; multiplas cartas nao acumulam."],
            [
                "Pernoite comum sem cobertura",
                "Nao usa cobertura de base; aplica valor somente a partir do segundo pernoite quando houver parametro vigente aprovado.",
            ],
            ["Condicao operacional especial", "Cobertura de base, pernoite comum e excecoes sao exibidos quando retornados pela memoria persistida."],
            ["Regra de excecao", "Calculos obsoletos ficam fora por padrao e so aparecem com incluir_obsoletos=true."],
            ["Observacoes", _parameter_text(data.get("parameters"))],
        ]
    story.append(_individual_table([[_cell(cell, styles["body"]) for cell in row] for row in rows], [48 * mm, 231 * mm]))


def _hourly_rows_story(story: list, data: dict, styles: dict):
    story.append(Paragraph("Lancamentos detalhados", styles["section"]))
    rows = [["Data", "Tripulante / funcao", "Voo / trecho", "Jornada", "Adicionais", "Valores", "Total", "Status"]]
    for item in data["rows"]:
        day_type = "Domingo/feriado" if bool(item.get("domingo_feriado")) else "Normal"
        if _is_cancelled_mission(item):
            day_type = "Cancelada"
        if _is_obsolete(item):
            day_type = "Obsoleto"
        mission_label = "\n".join(
            [
                f"Voo {_text(item.get('cavok_numero_voo') or item.get('chamado'))}",
                f"Trecho {_text(item.get('trecho'))}",
                f"ACFT {_text(item.get('aeronave_nome') or item.get('aeronave_id'))}",
                f"Rel/DB {_text(item.get('chamado') or item.get('contratante'))}",
                f"Justif. {_text(item.get('justificativa'))}",
            ]
        )
        jornada = "\n".join(
            [
                f"Apres. {_format_time_br(item.get('horario_apresentacao'))}",
                f"Aband. {_format_time_br(item.get('horario_abandono'))}",
                f"D {_format_minutes_hhmm(item.get('minutos_diurnos'))} / N {_format_minutes_hhmm(item.get('minutos_noturnos'))}",
                f"H.red {_format_decimal_hours_hhmm(item.get('horas_noturnas_convertidas'))}",
            ]
        )
        adicionais = "\n".join(
            [
                f"Pre {_format_minutes_hhmm(item.get('minutos_pre'))}",
                f"Pos {_format_minutes_hhmm(item.get('minutos_pos'))}",
                "Manual: Nao",
            ]
        )
        valores = "\n".join(
            [
                f"Normal {_format_money(_money(item.get('valor_adicional_noturno')) + _money(item.get('valor_pre')) + _money(item.get('valor_pos')))}",
                f"Diurno {_format_money(item.get('valor_domingo_feriado_diurno'))}",
                f"Not/ad. {_format_money(item.get('valor_domingo_feriado_noturno'))}",
            ]
        )
        rows.append(
            [
                "\n".join(
                    [
                        f"{_format_date_br(item.get('data_missao'))}",
                        f"Fim {_format_date_br(item.get('data_final') or item.get('data_missao'))}",
                        day_type,
                    ]
                ),
                f"{_text(item.get('tripulante_nome') or data['tripulante'].get('nome'))}\n{_text(item.get('funcao'))}",
                mission_label,
                jornada,
                adicionais,
                valores,
                _format_money(item.get("total")) if _is_payable(item) else "Nao compoe total",
                f"{_text(item.get('status'))}\n{_alert_text(item)}",
            ]
        )
    story.append(
        _individual_table(
            [[_cell(cell, styles["body"]) for cell in row] for row in rows],
            [20 * mm, 42 * mm, 47 * mm, 38 * mm, 32 * mm, 48 * mm, 24 * mm, 28 * mm],
        )
    )


def _productivity_rows_story(story: list, data: dict, styles: dict):
    story.append(Paragraph("Missoes detalhadas", styles["section"]))
    rows = [["Data", "Missao / trecho", "Aeronave", "Funcao", "Condicao", "Status", "Parametros", "Valores", "Alertas"]]
    main_calculation = (data.get("payable_rows") or data.get("rows") or [{}])[0]
    missions = data.get("missions") or []
    if not missions:
        missions = [
            {
                "data_missao": data["competencia"],
                "cavok_numero_voo": "Consolidado",
                "trecho": "Sem missoes detalhadas vinculadas",
                "aeronave_id": "-",
                "funcao": data.get("funcao"),
                "categoria_financeira_aeronave": main_calculation.get("categoria_aplicavel"),
                "missao_status": main_calculation.get("status"),
            }
        ]
    for mission in missions:
        rule = _productivity_rule_for_mission(main_calculation, mission)
        rows.append(
            [
                "\n".join(
                    [
                        _format_date_br(mission.get("data_missao")),
                        f"Fim {_format_date_br(mission.get('data_final') or mission.get('data_missao'))}",
                    ]
                ),
                "\n".join([f"Voo {_text(mission.get('cavok_numero_voo') or mission.get('chamado'))}", f"Trecho {_text(mission.get('trecho'))}"]),
                _text(mission.get("aeronave_nome") or mission.get("aeronave_id")),
                _text(mission.get("funcao")),
                "\n".join(
                    [
                        f"Categoria {_text(mission.get('categoria_financeira_aeronave'))}",
                        f"Pernoites {_text(mission.get('quantidade_pernoites'))}",
                        f"Cobertura {_bool_text(mission.get('cobertura_base'))}",
                        f"Especial {_text(mission.get('operacao_especial'))}",
                        f"Justif. {_text(mission.get('justificativa'))}",
                    ]
                ),
                "\n".join([f"Missao {_text(mission.get('missao_status'))}", f"Calculo {_text(main_calculation.get('status'))}"]),
                "\n".join([rule["key"], f"Quantidade {rule['quantity']}"]),
                "\n".join(
                    [
                        f"Unit. {_format_money(rule['unit_value'])}",
                        f"Calc. {_format_money(rule['total_value'])}",
                    ]
                ),
                _alert_text(main_calculation),
            ]
        )
    story.append(
        _individual_table(
            [[_cell(cell, styles["body"]) for cell in row] for row in rows],
            [19 * mm, 42 * mm, 24 * mm, 22 * mm, 38 * mm, 31 * mm, 30 * mm, 33 * mm, 40 * mm],
        )
    )


def _subtotals_story(story: list, data: dict, styles: dict):
    story.append(Paragraph("Subtotais", styles["section"]))
    totals = data["totals"]
    if data["tipo"] == "horaria":
        rows = [
            ["Tripulante", "Funcao", "Linhas", "Hora reduzida", "Normal", "Diurno", "Noturno/adicional", "Total"],
            [
                _text(data["tripulante"].get("nome")),
                _text(data.get("funcao")),
                str(totals["rows"]),
                _format_decimal_hours_hhmm(totals["hora_reduzida_decimal"]),
                _format_money(totals["valor_normal"]),
                _format_money(totals["holiday_valor_diurno"]),
                _format_money(totals["holiday_valor_noturno"]),
                _format_money(totals["total"]),
            ],
        ]
        widths = [58 * mm, 30 * mm, 23 * mm, 32 * mm, 34 * mm, 34 * mm, 40 * mm, 28 * mm]
    else:
        rows = [
            ["Tripulante", "Funcao", "Missoes", "Produtividade", "Valor base", "Valor adicional", "Total"],
            [
                _text(data["tripulante"].get("nome")),
                _text(data.get("funcao")),
                str(totals["missions"]),
                _format_money(totals["produtividade_calculada"]),
                _format_money(totals["valor_base"]),
                _format_money(totals["valor_adicional"]),
                _format_money(totals["total"]),
            ],
        ]
        widths = [65 * mm, 30 * mm, 24 * mm, 40 * mm, 38 * mm, 38 * mm, 44 * mm]
    story.append(_individual_table([[_cell(cell, styles["body"]) for cell in row] for row in rows], widths))


def _final_summary_story(story: list, data: dict, styles: dict):
    story.append(Paragraph("Resumo final", styles["section"]))
    totals = data["totals"]
    if data["tipo"] == "horaria":
        rows = [
            [_cell("RESUMO DAS HORAS E VALORES", styles["body_center_inverse"]), "", "", "", "", "", "", "", "", ""],
            [
                _cell("DIA NORMAL", styles["body_center"]),
                "",
                "",
                "",
                _cell("DOMINGO E FERIADOS", styles["body_center"]),
                "",
                "",
                "",
                "",
                _cell("TOTAL A PAGAR", styles["body_center"]),
            ],
            [
                _cell("DIU", styles["body_center"]),
                _cell("NOT", styles["body_center"]),
                _cell("POS", styles["body_center"]),
                _cell("VALOR", styles["body_center"]),
                _cell("DIU", styles["body_center"]),
                _cell("VALOR", styles["body_center"]),
                _cell("NOT", styles["body_center"]),
                _cell("POS", styles["body_center"]),
                _cell("VALOR", styles["body_center"]),
                "",
            ],
            [
                _cell(_format_minutes_hhmm(totals["normal_minutos_diurnos"]), styles["body_center"]),
                _cell(_format_minutes_hhmm(totals["normal_minutos_noturnos_reduzidos"]), styles["body_center"]),
                _cell(_format_minutes_hhmm(totals["normal_minutos_pos_reduzidos"]), styles["body_center"]),
                _cell(_format_money(totals["normal_total"]), styles["body_center"]),
                _cell(_format_minutes_hhmm(totals["holiday_minutos_diurnos"]), styles["body_center"]),
                _cell(_format_money(totals["holiday_valor_diurno"]), styles["body_center"]),
                _cell(_format_minutes_hhmm(totals["holiday_minutos_noturnos_reduzidos"]), styles["body_center"]),
                _cell(_format_minutes_hhmm(totals["holiday_minutos_pos_reduzidos"]), styles["body_center"]),
                _cell(_format_money(totals["holiday_valor_noturno"]), styles["body_center"]),
                _cell(_format_money(totals["total"]), styles["body_center"]),
            ],
        ]
        table = _individual_summary_table(
            rows,
            [24 * mm, 24 * mm, 24 * mm, 33 * mm, 24 * mm, 33 * mm, 24 * mm, 24 * mm, 33 * mm, 36 * mm],
            spans=[
                ((0, 0), (-1, 0)),
                ((0, 1), (3, 1)),
                ((4, 1), (8, 1)),
                ((9, 1), (9, 2)),
            ],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 1), (3, 1), colors.HexColor("#fff2cc")),
                    ("BACKGROUND", (4, 1), (8, 1), colors.HexColor("#d9ead3")),
                    ("BACKGROUND", (9, 1), (9, 3), colors.HexColor("#f4cccc")),
                    ("BACKGROUND", (0, 2), (8, 2), colors.white),
                    ("BACKGROUND", (0, 3), (8, 3), colors.white),
                ]
            )
        )
        story.append(table)
    else:
        rows = [
            [_cell("RESUMO DA PRODUTIVIDADE E VALORES", styles["body_center_inverse"]), "", "", "", "", ""],
            [
                _cell("Produtividade apurada", styles["body_center"]),
                _cell("Garantia minima", styles["body_center"]),
                _cell("Excedente", styles["body_center"]),
                _cell("Total a pagar", styles["body_center"]),
                _cell("Missoes", styles["body_center"]),
                _cell("Alertas", styles["body_center"]),
            ],
            [
                _cell(_format_money(totals["produtividade_calculada"]), styles["body_center"]),
                _cell(_format_money(totals["garantia_minima"]), styles["body_center"]),
                _cell(_format_money(totals["excedente"]), styles["body_center"]),
                _cell(_format_money(totals["total"]), styles["body_center"]),
                _cell(str(totals["missions"]), styles["body_center"]),
                _cell(str(totals["alertas"]), styles["body_center"]),
            ],
        ]
        table = _individual_summary_table(
            rows,
            [49 * mm, 49 * mm, 43 * mm, 49 * mm, 43 * mm, 46 * mm],
            spans=[((0, 0), (-1, 0))],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 1), (2, 1), colors.HexColor("#fff2cc")),
                    ("BACKGROUND", (3, 1), (3, 2), colors.HexColor("#f4cccc")),
                    ("BACKGROUND", (4, 1), (5, 1), colors.HexColor("#d9ead3")),
                    ("BACKGROUND", (0, 2), (2, 2), colors.white),
                    ("BACKGROUND", (4, 2), (5, 2), colors.white),
                ]
            )
        )
        story.append(table)


def _build_individual_pdf(*, data: dict, actor_user_id: int, request_id: str, correlation_id: str, generated_at: datetime | None = None) -> bytes:
    generated = generated_at or datetime.now()
    generated_text = generated.strftime("%d/%m/%Y %H:%M:%S")
    footer_generated_text = generated.strftime("%d/%m/%Y %H:%M")
    styles = _individual_styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=9 * mm,
        rightMargin=9 * mm,
        title=f"{data['title']} {data['competencia']}",
        author="Treinamentos Brasil Vida",
        subject="Relatorio financeiro individual",
    )
    story: list = []
    _individual_header_story(story, data, styles, generated_text=footer_generated_text)
    _identification_story(story, data, styles)
    story.append(Spacer(1, 2 * mm))
    _bases_story(story, data, styles)
    story.append(Spacer(1, 2 * mm))
    if data["tipo"] == "horaria":
        _hourly_rows_story(story, data, styles)
    else:
        _productivity_parameters_story(story, data, styles)
        story.append(Spacer(1, 2 * mm))
        _productivity_rows_story(story, data, styles)
    story.append(Spacer(1, 2 * mm))
    _subtotals_story(story, data, styles)
    story.append(Spacer(1, 2 * mm))
    _final_summary_story(story, data, styles)
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            escape(f"Emitido por usuario {actor_user_id or '-'} em {generated_text}. Documento de conferencia financeira gerado a partir de calculos persistidos."),
            styles["notice"],
        )
    )
    footer = _individual_page_footer(_text(data.get("title")), footer_generated_text)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    value = buffer.getvalue()
    buffer.close()
    return value


def gerar_relatorio_financeiro_individual_pdf(
    *,
    tipo: str,
    competencia: str,
    tripulante_id: int,
    funcao: str | None = None,
    status: str | None = None,
    incluir_obsoletos: bool = False,
    org_id: str | None = None,
    actor_user_id: int = 0,
    request_id: str = "",
    correlation_id: str = "",
    source_endpoint: str = "/api/v1/financeiro/relatorios/individual.pdf",
    db=None,
) -> dict:
    resolved_db = _resolve_db(db)
    resolved_org_id = _resolve_org_id(org_id)
    report_type = str(tipo or "").strip().lower()
    if report_type not in {"horaria", "produtividade"}:
        raise DomainValidationError(
            "Tipo de relatorio individual invalido.",
            code="finance_individual_report_invalid_type",
            details={"field": "tipo", "allowed": ["horaria", "produtividade"]},
        )
    if int(tripulante_id or 0) <= 0:
        raise DomainValidationError(
            "tripulante_id e obrigatorio.",
            code="finance_individual_report_tripulante_required",
            details={"field": "tripulante_id"},
        )
    normalized_funcao = str(funcao or "").strip() or None
    normalized_status = str(status or "").strip() or None
    if report_type == "horaria":
        data = _hourly_report_data(
            resolved_db,
            competencia=competencia,
            tripulante_id=int(tripulante_id),
            funcao=normalized_funcao,
            status=normalized_status,
            incluir_obsoletos=bool(incluir_obsoletos),
            org_id=resolved_org_id,
        )
        filename_prefix = "relatorio-bonificacao-horaria"
    else:
        data = _productivity_report_data(
            resolved_db,
            competencia=competencia,
            tripulante_id=int(tripulante_id),
            funcao=normalized_funcao,
            status=normalized_status,
            incluir_obsoletos=bool(incluir_obsoletos),
            org_id=resolved_org_id,
        )
        filename_prefix = "relatorio-produtividade"

    pdf_bytes = _build_individual_pdf(
        data=data,
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    pdf_bytes = _assert_pdf_bytes_complete(pdf_bytes, code="finance_individual_report_pdf")
    totals = data["totals"]
    metadata = {
        "event_name": "finance.export.generated",
        "org_id": resolved_org_id,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "actor_user_id": actor_user_id,
        "entity_type": "finance_export",
        "entity_id": int(tripulante_id),
        "permission": "finance:exports:create",
        "source_endpoint": source_endpoint,
        "competencia": competencia,
        "format": "pdf",
        "filters": {
            "tipo": report_type,
            "competencia": competencia,
            "tripulante_id": int(tripulante_id),
            "funcao": normalized_funcao,
            "status": normalized_status,
            "incluir_obsoletos": bool(incluir_obsoletos),
        },
        "record_count": int(totals.get("rows") or totals.get("missions") or 0),
        "total_calculado": str(totals.get("total") or Decimal("0")),
        "report_version": FINANCE_INDIVIDUAL_REPORT_VERSION,
    }
    record_audit_event(
        resolved_db,
        entidade="finance_export",
        entidade_id=int(tripulante_id),
        acao="finance.export.generated",
        realizado_por=actor_user_id,
        payload_anterior=None,
        payload_novo={
            "metadata": metadata,
            "totals": {key: str(value) for key, value in totals.items()},
            "pdf_bytes": len(pdf_bytes),
        },
        observacao=f"tipo={report_type}; competencia={competencia}; tripulante_id={tripulante_id}; format=pdf",
    )
    individual_metadata = {**metadata, "event_name": "finance.report.individual.generated"}
    record_audit_event(
        resolved_db,
        entidade="finance_export",
        entidade_id=int(tripulante_id),
        acao="finance.report.individual.generated",
        realizado_por=actor_user_id,
        payload_anterior=None,
        payload_novo={
            "metadata": individual_metadata,
            "totals": {key: str(value) for key, value in totals.items()},
            "pdf_bytes": len(pdf_bytes),
        },
        observacao=f"tipo={report_type}; competencia={competencia}; tripulante_id={tripulante_id}; format=pdf",
    )
    resolved_db.commit()
    filename = f"{filename_prefix}-{competencia}-{_slugify_filename(data['tripulante'].get('nome'))}.pdf"
    return {
        "content": pdf_bytes,
        "filename": filename,
        "mimetype": "application/pdf",
        "tipo": report_type,
        "metadata": metadata,
    }
