from __future__ import annotations

from datetime import date, datetime

from html import escape
from io import BytesIO
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _status_chip_color(status_key: str) -> colors.Color:
    if status_key == "vencido":
        return colors.HexColor("#b42318")
    if status_key == "critico_15":
        return colors.HexColor("#dc2626")
    if status_key == "vencer_30":
        return colors.HexColor("#ea580c")
    if status_key == "vencer_60":
        return colors.HexColor("#b45309")
    if status_key == "vencer_90":
        return colors.HexColor("#ca8a04")
    if status_key == "em_dia":
        return colors.HexColor("#15803d")
    return colors.HexColor("#475467")


def _training_status_chip_color(status_label: str) -> colors.Color:
    normalized = (status_label or "").strip().lower()
    if normalized == "vencido":
        return colors.HexColor("#b42318")
    if normalized == "a vencer":
        return colors.HexColor("#b45309")
    if normalized == "regular":
        return colors.HexColor("#15803d")
    return colors.HexColor("#475467")


def _format_pdf_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return text


def _fmt_summary_rows(summary: dict) -> list[list[str]]:
    return [
        ["Total de tripulantes", str(summary.get("total_tripulantes", 0))],
        ["Total de habilitações", str(summary.get("total_habilitacoes", 0))],
        ["Em dia", str(summary.get("total_em_dia", 0))],
        ["A vencer até 90 dias", str(summary.get("total_vencer_90", 0))],
        ["A vencer até 60 dias", str(summary.get("total_vencer_60", 0))],
        ["A vencer até 30 dias", str(summary.get("total_vencer_30", 0))],
        ["Crítico até 15 dias", str(summary.get("total_critico_15", 0))],
        ["Vencido", str(summary.get("total_vencido", 0))],
    ]


def _iter_detail_rows(tripulantes_grouped: Iterable[dict]):
    for group in tripulantes_grouped:
        tripulante = group.get("tripulante_nome") or "-"
        base = group.get("base") or "-"
        for item in group.get("habilitacoes") or []:
            if item.get("is_placeholder"):
                continue
            yield [
                tripulante,
                base,
                item.get("habilitacao_nome") or "-",
                item.get("data_vencimento") or "Sem vencimento informado",
                item.get("days_remaining_label") or "Sem vencimento informado",
                item.get("status_label") or "-",
                item.get("status_key") or "sem_vencimento",
            ]


def build_habilitacoes_consolidado_pdf(
    *,
    summary: dict,
    tripulantes_grouped: list[dict],
    filtros_aplicados: dict[str, str],
    emitted_at: str,
) -> bytes:
    """Gera PDF corporativo real para o consolidado de habilitações."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title="Consolidado de Habilitações",
        author="Treinamentos Brasil vida",
        subject="Relatório operacional de vencimentos",
    )

    story: list = []
    base_font, bold_font, label_style, value_style = _build_pdf_brand_header(
        story,
        title="Consolidado de Habilitações",
        subtitle="Relatório operacional de vencimentos por tripulante",
        emitted_at=emitted_at,
    )

    filtros_data = [
        [Paragraph("<b>Tripulante</b>", label_style), Paragraph(filtros_aplicados.get("nome", "-"), value_style)],
        [Paragraph("<b>Base</b>", label_style), Paragraph(filtros_aplicados.get("base", "-"), value_style)],
        [Paragraph("<b>Status</b>", label_style), Paragraph(filtros_aplicados.get("status", "-"), value_style)],
        [Paragraph("<b>Tipo</b>", label_style), Paragraph(filtros_aplicados.get("tipo", "-"), value_style)],
        [Paragraph("<b>Ordenacao</b>", label_style), Paragraph(filtros_aplicados.get("ordenacao", "criticidade"), value_style)],
    ]
    filtros_table = Table(filtros_data, colWidths=[36 * mm, 56 * mm, 22 * mm, 56 * mm])
    filtros_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(filtros_table)
    story.append(Spacer(1, 4 * mm))

    summary_rows = [[Paragraph("<b>Indicador</b>", label_style), Paragraph("<b>Valor</b>", label_style)]]
    for label, value in _fmt_summary_rows(summary):
        summary_rows.append([Paragraph(label, value_style), Paragraph(value, value_style)])
    summary_table = Table(summary_rows, colWidths=[88 * mm, 20 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ffffff")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#ffffff"), colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d9e6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 5 * mm))

    detail_rows = [
        [
            Paragraph("<b>Tripulante</b>", label_style),
            Paragraph("<b>Base</b>", label_style),
            Paragraph("<b>Habilitação</b>", label_style),
            Paragraph("<b>Vencimento</b>", label_style),
            Paragraph("<b>Dias</b>", label_style),
            Paragraph("<b>Status</b>", label_style),
        ]
    ]
    detail_status_colors: list[colors.Color] = []
    for row in _iter_detail_rows(tripulantes_grouped):
        detail_rows.append(
            [
                Paragraph(row[0], value_style),
                Paragraph(row[1], value_style),
                Paragraph(row[2], value_style),
                Paragraph(row[3], value_style),
                Paragraph(row[4], value_style),
                Paragraph(row[5], value_style),
            ]
        )
        detail_status_colors.append(_status_chip_color(row[6]))

    if len(detail_rows) == 1:
        detail_rows.append(
            [
                Paragraph("Nenhum registro encontrado para os filtros atuais.", value_style),
                "",
                "",
                "",
                "",
                "",
            ]
        )
        detail_status_colors.append(colors.HexColor("#64748b"))

    detail_table = Table(
        detail_rows,
        repeatRows=1,
        colWidths=[40 * mm, 20 * mm, 43 * mm, 24 * mm, 23 * mm, 25 * mm],
    )
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#ffffff"), colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for idx, status_color in enumerate(detail_status_colors, start=1):
        style_cmds.append(("TEXTCOLOR", (5, idx), (5, idx), status_color))
        style_cmds.append(("FONTNAME", (5, idx), (5, idx), bold_font))
    detail_table.setStyle(TableStyle(style_cmds))
    story.append(detail_table)

    footer = _build_pdf_footer_renderer(
        base_font=base_font,
        footer_left_text="Treinamentos Brasil vida • Consolidado de habilitações",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value


def _prepare_pdf_fonts():
    font_registered = False
    inter_path = Path(__file__).resolve().parent / "static" / "fonts" / "Inter-Regular.ttf"
    inter_bold_path = Path(__file__).resolve().parent / "static" / "fonts" / "Inter-Bold.ttf"
    if inter_path.exists() and inter_bold_path.exists():
        pdfmetrics.registerFont(TTFont("Inter", str(inter_path)))
        pdfmetrics.registerFont(TTFont("Inter-Bold", str(inter_bold_path)))
        font_registered = True
    base_font = "Inter" if font_registered else "Helvetica"
    bold_font = "Inter-Bold" if font_registered else "Helvetica-Bold"
    styles = getSampleStyleSheet()
    label_style = ParagraphStyle(
        "PLabel",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=9.2,
        textColor=colors.HexColor("#334155"),
        leading=12.5,
    )
    value_style = ParagraphStyle(
        "PValue",
        parent=styles["Normal"],
        fontName=base_font,
        fontSize=9.4,
        textColor=colors.HexColor("#0f172a"),
        leading=13,
    )
    return base_font, bold_font, label_style, value_style


def _build_pdf_brand_header(story: list, *, title: str, subtitle: str, emitted_at: str):
    base_font, bold_font, label_style, value_style = _prepare_pdf_fonts()
    logo_path = Path(__file__).resolve().parent / "static" / "apple-touch-icon.png"
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HdrTitle",
        parent=styles["Heading1"],
        fontName=bold_font,
        fontSize=18,
        leading=21.5,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_RIGHT,
        spaceAfter=0.8 * mm,
    )
    subtitle_style = ParagraphStyle(
        "HdrSubtitle",
        parent=styles["Normal"],
        fontName=base_font,
        fontSize=10.2,
        textColor=colors.HexColor("#475569"),
        alignment=TA_RIGHT,
        leading=13.5,
    )
    kicker_style = ParagraphStyle(
        "HdrKicker",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=8.8,
        textColor=colors.HexColor("#9f1239"),
        alignment=TA_RIGHT,
        leading=10.5,
        spaceAfter=0.6 * mm,
    )
    header_meta_flow = [
        Paragraph("Treinamentos Brasil vida", kicker_style),
        Paragraph(title, title_style),
        Paragraph(subtitle, subtitle_style),
    ]
    has_logo = logo_path.exists()
    if has_logo:
        logo = Image(str(logo_path), width=32 * mm, height=32 * mm)
        header_table = Table([[logo, header_meta_flow]], colWidths=[40 * mm, 140 * mm])
    else:
        header_table = Table([[header_meta_flow]], colWidths=[180 * mm])
    header_style = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
    ]
    if has_logo:
        header_style.append(("ALIGN", (1, 0), (1, 0), "RIGHT"))
    header_table.setStyle(TableStyle(header_style))
    story.append(header_table)
    story.append(Spacer(1, 2.2 * mm))

    divider_top = Table([[""]], colWidths=[180 * mm], rowHeights=[0.4 * mm])
    divider_top.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#d6deea")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(divider_top)
    story.append(Spacer(1, 1.5 * mm))

    emitted_style = ParagraphStyle(
        "HdrMeta",
        parent=styles["Normal"],
        fontName=base_font,
        fontSize=9.2,
        textColor=colors.HexColor("#334155"),
        leading=12,
        alignment=TA_LEFT,
    )
    story.append(Paragraph(f"Emissão: {emitted_at}", emitted_style))
    story.append(Spacer(1, 1.5 * mm))

    divider_bottom = Table([[""]], colWidths=[180 * mm], rowHeights=[0.4 * mm])
    divider_bottom.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#d6deea")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(divider_bottom)
    story.append(Spacer(1, 4.2 * mm))
    return base_font, bold_font, label_style, value_style


def _build_pdf_footer_renderer(*, base_font: str, footer_left_text: str):
    def _footer(canvas, _doc):
        canvas.saveState()
        page_width = _doc.pagesize[0]
        left = _doc.leftMargin
        right = page_width - _doc.rightMargin
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.setLineWidth(0.3)
        canvas.line(left, 10 * mm, right, 10 * mm)
        canvas.setFont(base_font, 8)
        page = canvas.getPageNumber()
        stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(left, 6 * mm, f"{footer_left_text} • Emissão {stamp}")
        canvas.drawRightString(right, 6 * mm, f"Página {page}")
        canvas.restoreState()

    return _footer


def build_tripulante_treinamentos_pdf(
    *,
    tripulante: dict,
    treinamentos: list[dict],
    resumo: dict,
    emitted_at: str,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title="Relatório Individual de Treinamentos",
        author="Treinamentos Brasil vida",
        subject="Relatório operacional individual de treinamentos e vencimentos",
    )

    story: list = []
    base_font, bold_font, label_style, value_style = _build_pdf_brand_header(
        story,
        title=f"Relatório Individual • {tripulante.get('nome') or '-'}",
        subtitle="Treinamentos registrados, status de vencimento e visão consolidada",
        emitted_at=emitted_at,
    )

    identificacao_rows = [
        [Paragraph("<b>Nome</b>", label_style), Paragraph(str(tripulante.get("nome") or "-"), value_style)],
        [Paragraph("<b>CPF</b>", label_style), Paragraph(str(tripulante.get("cpf") or "-"), value_style)],
        [Paragraph("<b>Código ANAC</b>", label_style), Paragraph(str(tripulante.get("licenca_anac") or "-"), value_style)],
        [Paragraph("<b>E-mail</b>", label_style), Paragraph(str(tripulante.get("email") or "-"), value_style)],
        [Paragraph("<b>WhatsApp</b>", label_style), Paragraph(str(tripulante.get("telefone") or "-"), value_style)],
        [Paragraph("<b>Base</b>", label_style), Paragraph(str(tripulante.get("base") or "-"), value_style)],
        [Paragraph("<b>Status</b>", label_style), Paragraph(str(tripulante.get("status") or "-"), value_style)],
    ]
    identificacao_table = Table(identificacao_rows, colWidths=[46 * mm, 89 * mm])
    identificacao_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(identificacao_table)
    story.append(Spacer(1, 4 * mm))

    resumo_rows = [
        [
            Paragraph("<b>Total</b>", label_style),
            Paragraph("<b>Vencidos</b>", label_style),
            Paragraph("<b>A vencer</b>", label_style),
            Paragraph("<b>Regulares</b>", label_style),
        ],
        [
            Paragraph(str(resumo.get("total", 0)), value_style),
            Paragraph(str(resumo.get("vencido", 0)), value_style),
            Paragraph(str(resumo.get("a vencer", 0)), value_style),
            Paragraph(str(resumo.get("regular", 0)), value_style),
        ],
    ]
    resumo_table = Table(resumo_rows, colWidths=[33.75 * mm, 33.75 * mm, 33.75 * mm, 33.75 * mm])
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("FONTNAME", (0, 1), (-1, 1), bold_font),
                ("FONTSIZE", (0, 1), (-1, 1), 12),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d9e6")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(resumo_table)
    story.append(Spacer(1, 5 * mm))

    detail_rows = [
        [
            Paragraph("<b>Equipamento</b>", label_style),
            Paragraph("<b>Tipo de treinamento</b>", label_style),
            Paragraph("<b>Realização</b>", label_style),
            Paragraph("<b>Vencimento</b>", label_style),
            Paragraph("<b>Status</b>", label_style),
            Paragraph("<b>Observação</b>", label_style),
        ]
    ]
    status_colors: list[colors.Color] = []
    for row in treinamentos:
        status_text = str(row.get("status_calculado") or "-")
        detail_rows.append(
            [
                Paragraph(str(row.get("equipamento_nome") or "-"), value_style),
                Paragraph(str(row.get("tipo_treinamento_nome") or "-"), value_style),
                Paragraph(_format_pdf_date(row.get("data_realizacao")), value_style),
                Paragraph(_format_pdf_date(row.get("data_vencimento")), value_style),
                Paragraph(status_text, value_style),
                Paragraph(str(row.get("observacao") or "-"), value_style),
            ]
        )
        status_colors.append(_training_status_chip_color(status_text))

    if len(detail_rows) == 1:
        detail_rows.append(
            [
                Paragraph("Nenhum treinamento registrado para este tripulante.", value_style),
                "",
                "",
                "",
                "",
                "",
            ]
        )
        status_colors.append(colors.HexColor("#64748b"))

    detail_table = Table(
        detail_rows,
        repeatRows=1,
        colWidths=[31 * mm, 45 * mm, 22 * mm, 22 * mm, 20 * mm, 40 * mm],
    )
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for idx, status_color in enumerate(status_colors, start=1):
        style_cmds.append(("TEXTCOLOR", (4, idx), (4, idx), status_color))
        style_cmds.append(("FONTNAME", (4, idx), (4, idx), bold_font))
    detail_table.setStyle(TableStyle(style_cmds))
    story.append(detail_table)

    footer = _build_pdf_footer_renderer(
        base_font=base_font,
        footer_left_text=f"Treinamentos Brasil vida • Relatório individual • {tripulante.get('nome') or '-'}",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value


def build_auditoria_pdf(
    *,
    emitted_at: str,
    filtros_aplicados: dict[str, str],
    rows: list[dict],
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title="Log de ações",
        author="Treinamentos Brasil vida",
        subject="Histórico de auditoria do sistema",
    )

    story: list = []
    base_font, bold_font, label_style, value_style = _build_pdf_brand_header(
        story,
        title="Log de ações",
        subtitle="Resumo simples da auditoria operacional",
        emitted_at=emitted_at,
    )

    filtros_table = Table(
        [
            [Paragraph("<b>Entidade</b>", label_style), Paragraph(filtros_aplicados.get("entidade", "-"), value_style)],
            [Paragraph("<b>Ação</b>", label_style), Paragraph(filtros_aplicados.get("acao", "-"), value_style)],
            [Paragraph("<b>Responsável</b>", label_style), Paragraph(filtros_aplicados.get("autor", "-"), value_style)],
            [Paragraph("<b>Busca</b>", label_style), Paragraph(filtros_aplicados.get("busca", "-"), value_style)],
        ],
        colWidths=[42 * mm, 93 * mm],
    )
    filtros_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d9e6")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(filtros_table)
    story.append(Spacer(1, 4 * mm))

    table_rows = [
        [
            Paragraph("<b>Data e hora</b>", label_style),
            Paragraph("<b>Ação registrada</b>", label_style),
            Paragraph("<b>Observação</b>", label_style),
        ]
    ]
    for row in rows:
        table_rows.append(
            [
                Paragraph(row.get("realizado_em_label") or "-", value_style),
                Paragraph(row.get("resumo_simples") or "-", value_style),
                Paragraph(row.get("observacao") or "-", value_style),
            ]
        )
    if len(table_rows) == 1:
        table_rows.append(
            [
                Paragraph("-", value_style),
                Paragraph("Nenhuma ação registrada para os filtros selecionados.", value_style),
                Paragraph("-", value_style),
            ]
        )

    detail_table = Table(table_rows, repeatRows=1, colWidths=[35 * mm, 90 * mm, 43 * mm])
    detail_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(detail_table)

    footer = _build_pdf_footer_renderer(
        base_font=base_font,
        footer_left_text="Treinamentos Brasil vida • Log de ações",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value


def build_user_guide_pdf(*, emitted_at: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title="Guia do Usuário",
        author="Treinamentos Brasil vida",
        subject="Manual operacional completo da plataforma",
    )

    story: list = []
    base_font, bold_font, label_style, value_style = _build_pdf_brand_header(
        story,
        title="Guia do Usuário da Plataforma",
        subtitle="Manual operacional detalhado para treinamento e consulta",
        emitted_at=emitted_at,
    )

    section_title_style = ParagraphStyle(
        "GuideSectionTitle",
        parent=value_style,
        fontName=bold_font,
        fontSize=12.5,
        leading=17,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=3 * mm,
        spaceAfter=2 * mm,
    )
    subsection_style = ParagraphStyle(
        "GuideSubsection",
        parent=value_style,
        fontName=bold_font,
        fontSize=10.2,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=1.5 * mm,
        spaceAfter=1.2 * mm,
    )
    paragraph_style = ParagraphStyle(
        "GuideParagraph",
        parent=value_style,
        fontName=base_font,
        fontSize=9.6,
        leading=14.4,
        textColor=colors.HexColor("#111827"),
        spaceAfter=1.4 * mm,
    )
    bullet_style = ParagraphStyle(
        "GuideBullet",
        parent=paragraph_style,
        leftIndent=10,
        bulletIndent=0,
        spaceAfter=1.0 * mm,
    )
    note_style = ParagraphStyle(
        "GuideNote",
        parent=paragraph_style,
        fontName=base_font,
        textColor=colors.HexColor("#334155"),
        backColor=colors.HexColor("#f8fafc"),
        borderWidth=0.5,
        borderColor=colors.HexColor("#cbd5e1"),
        borderPadding=6,
        borderRadius=3,
        spaceBefore=1.2 * mm,
        spaceAfter=2 * mm,
    )

    sections = [
        (
            "Sumario executivo do manual",
            [
                "Este manual orienta o uso operacional do sistema Treinamentos Brasil vida apos a simplificacao de superficies analiticas.",
                "A leitura recomendada segue os dominios ativos: acesso, dashboard, cadastros, operacoes, relatorios de habilitacoes, documentos, usuarios e governanca.",
                "## Estrutura de leitura",
                "• 1. Apresentacao do sistema",
                "• 2. Estrutura geral e navegacao",
                "• 3. Acesso ao sistema",
                "• 4. Dashboard e visao geral",
                "• 5. Cadastros",
                "• 6. Operacoes",
                "• 7. Relatorios de habilitacoes",
                "• 8. PDFs e documentos gerados",
                "• 9. Usuarios e permissoes",
                "• 10. Fluxo operacional recomendado",
            ],
        ),
        (
            "1. Apresentacao do sistema",
            [
                "O Treinamentos Brasil vida centraliza cadastros, treinamentos, vencimentos, pernoites, auditoria e administracao de acesso em um unico ambiente.",
                "O objetivo principal e reduzir controles paralelos, melhorar rastreabilidade e apoiar a execucao diaria da operacao.",
                "Relatorios e documentos oficiais devem sempre refletir dados estruturados, filtros aplicados e trilha de auditoria adequada.",
            ],
        ),
        (
            "2. Estrutura geral do sistema e navegacao",
            [
                "A navegacao e organizada por dominio funcional: Dashboard, Operacoes, Relatorios, Cadastros e Usuarios.",
                "## 2.1 Menu lateral",
                "A barra lateral exibe apenas modulos permitidos ao usuario autenticado. Se uma entrada nao aparece, valide as permissoes antes de tentar acesso direto por URL.",
                "## 2.2 Boas praticas",
                "• Revise filtros antes de exportar documentos.",
                "• Evite multiplas abas com contextos diferentes sem identificar cada filtro.",
                "• Ao encontrar divergencia, volte ao registro de origem antes de concluir analise.",
            ],
        ),
        (
            "3. Acesso ao sistema",
            [
                "O acesso usa usuario e senha cadastrados pela administracao. Ao autenticar, as permissoes sao carregadas para controlar menu, rotas e acoes.",
                "Nunca compartilhe credenciais. A auditoria registra eventos por usuario e depende de identidade individual para manter responsabilidade operacional.",
            ],
        ),
        (
            "4. Dashboard e visao geral",
            [
                "O Dashboard mostra criticidade de treinamentos e vencimentos para orientar prioridade diaria.",
                "A leitura recomendada e: vencidos, proximos 7 dias, proximos 30 dias e registros regulares.",
                "Use os atalhos do dashboard para abrir a lista ou o cadastro de origem e corrigir pendencias.",
            ],
        ),
        (
            "5. Cadastros",
            [
                "Cadastros sustentam todos os fluxos do sistema. Dados incompletos afetam alertas, relatorios e comunicacoes.",
                "## 5.1 Tripulantes",
                "Mantenha nome, CPF, licenca, base, status e funcao operacional consistentes com a realidade da operacao.",
                "## 5.2 Treinamentos",
                "Registre tipo, equipamento, datas e anexos comprobatórios quando aplicavel. Datas inconsistentes geram alertas incorretos.",
                "## 5.3 Equipamentos e tipos",
                "Padronize nomes e periodicidades para evitar duplicidade e interpretacao divergente.",
            ],
        ),
        (
            "6. Operacoes",
            [
                "Operacoes registra pernoites vinculados ao dia a dia da equipe.",
                "Pernoites devem informar tripulante, data, tipo, quantidade e observacoes suficientes para auditoria operacional.",
            ],
        ),
        (
            "7. Relatorios de habilitacoes",
            [
                "O consolidado de habilitacoes apoia gestao preventiva de vencimentos por tripulante.",
                "Aplique filtros de nome, base, status e tipo antes de interpretar totais ou exportar arquivos.",
                "Quando um total parecer incoerente, confira primeiro os filtros e depois os registros de treinamento vinculados.",
            ],
        ),
        (
            "8. PDFs e documentos gerados",
            [
                "PDFs oficiais sao gerados a partir de dados estruturados e incluem cabecalho corporativo, filtros e identificacao de emissao.",
                "Antes de compartilhar, valide escopo, filtros, data de emissao e aderencia ao registro de origem.",
            ],
        ),
        (
            "9. Usuarios e permissoes",
            [
                "Permissoes devem seguir o menor privilegio necessario para a funcao de cada pessoa.",
                "Revise acessos periodicamente e remova permissoes imediatamente quando houver mudanca de funcao ou desligamento.",
            ],
        ),
        (
            "10. Fluxo operacional recomendado",
            [
                "Rotina diaria: abrir Dashboard, tratar vencidos e proximos vencimentos, registrar operacoes e conferir cadastros alterados.",
                "Rotina semanal: revisar consolidado de habilitacoes, pendencias sem data e amostra de registros operacionais.",
                "Governanca: manter auditoria, backups e documentos oficiais alinhados ao comportamento real do sistema.",
            ],
        ),
    ]
    page_break_after_titles = {
        "1. Apresentacao do sistema",
        "4. Dashboard e visao geral",
        "7. Relatorios de habilitacoes",
        "9. Usuarios e permissoes",
    }
    for title, paragraphs in sections:
        story.append(Paragraph(title, section_title_style))
        for text in paragraphs:
            if text.startswith("## "):
                story.append(Paragraph(text[3:], subsection_style))
                continue
            if text.startswith("• "):
                story.append(Paragraph(text[2:], bullet_style, bulletText="•"))
                continue
            story.append(Paragraph(text, paragraph_style))

        if title in page_break_after_titles:
            story.append(PageBreak())
        else:
            story.append(Spacer(1, 1.2 * mm))

    story.append(
        Paragraph(
            "Versão deste manual: emitida automaticamente pelo sistema. Para validar vigência, consulte data/hora de emissão no cabeçalho deste documento.",
            note_style,
        )
    )

    footer = _build_pdf_footer_renderer(
        base_font=base_font,
        footer_left_text="Treinamentos Brasil vida • Guia do usuário",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value
