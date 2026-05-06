from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
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


def decimal_to_currency(value: Decimal | int | float) -> str:
    numeric = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = f"{numeric:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


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


def build_produtividade_consolidado_pdf(
    *,
    competencia: str,
    filtros_aplicados: dict[str, str],
    summary: dict,
    rows: list[dict],
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
        title="Produtividade Consolidada",
        author="Treinamentos Brasil vida",
        subject="Relatório consolidado de bonificação/produtividade",
    )
    story: list = []
    base_font, bold_font, label_style, value_style = _build_pdf_brand_header(
        story,
        title="Produtividade Mensal Consolidada",
        subtitle=f"Competência {competencia}",
        emitted_at=emitted_at,
    )

    filtros_data = [
        [Paragraph("<b>Tripulante</b>", label_style), Paragraph(filtros_aplicados.get("nome", "-"), value_style)],
        [Paragraph("<b>Base</b>", label_style), Paragraph(filtros_aplicados.get("base", "-"), value_style)],
        [Paragraph("<b>Função</b>", label_style), Paragraph(filtros_aplicados.get("funcao", "-"), value_style)],
        [Paragraph("<b>Categoria</b>", label_style), Paragraph(filtros_aplicados.get("categoria", "-"), value_style)],
    ]
    filtros_table = Table(filtros_data, colWidths=[36 * mm, 52 * mm, 30 * mm, 58 * mm])
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

    summary_rows = [
        [Paragraph("<b>Indicador</b>", label_style), Paragraph("<b>Valor</b>", label_style)],
        [Paragraph("Tripulantes processados", value_style), Paragraph(str(summary.get("total_tripulantes", 0)), value_style)],
        [Paragraph("Total de missões", value_style), Paragraph(str(summary.get("total_missoes", 0)), value_style)],
        [Paragraph("Total de pernoites", value_style), Paragraph(str(summary.get("total_pernoites", 0)), value_style)],
        [Paragraph("Total pago por piso mínimo", value_style), Paragraph(decimal_to_currency(summary.get("total_pago_piso", 0)), value_style)],
        [Paragraph("Total pago por produtividade", value_style), Paragraph(decimal_to_currency(summary.get("total_pago_produtividade", 0)), value_style)],
        [Paragraph("Valor total consolidado", value_style), Paragraph(decimal_to_currency(summary.get("valor_total_consolidado", 0)), value_style)],
    ]
    summary_table = Table(summary_rows, colWidths=[95 * mm, 40 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
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

    detail_rows = [[
        Paragraph("<b>Tripulante</b>", label_style),
        Paragraph("<b>Base</b>", label_style),
        Paragraph("<b>Missões</b>", label_style),
        Paragraph("<b>Pernoites</b>", label_style),
        Paragraph("<b>Produtividade</b>", label_style),
        Paragraph("<b>Final</b>", label_style),
        Paragraph("<b>Critério</b>", label_style),
    ]]
    for row in rows:
        detail_rows.append(
            [
                Paragraph(str(row.get("tripulante_nome") or "-"), value_style),
                Paragraph(str(row.get("base") or "-"), value_style),
                Paragraph(str(row.get("total_missoes_validas") or 0), value_style),
                Paragraph(str((row.get("total_pernoites_cobertura") or 0) + (row.get("total_pernoites_operacionais_elegiveis") or 0)), value_style),
                Paragraph(decimal_to_currency(row.get("total_produtividade") or 0), value_style),
                Paragraph(decimal_to_currency(row.get("valor_final_mes") or 0), value_style),
                Paragraph(str(row.get("criterio_fechamento") or "-"), value_style),
            ]
        )
    if len(detail_rows) == 1:
        detail_rows.append([Paragraph("Nenhum registro para os filtros atuais.", value_style), "", "", "", "", "", ""])

    detail_table = Table(
        detail_rows,
        repeatRows=1,
        colWidths=[40 * mm, 22 * mm, 15 * mm, 18 * mm, 28 * mm, 28 * mm, 29 * mm],
    )
    detail_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(detail_table)

    footer = _build_pdf_footer_renderer(
        base_font=base_font,
        footer_left_text=f"Treinamentos Brasil vida • Produtividade consolidada • {competencia}",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value


def build_produtividade_tripulante_pdf(
    *,
    competencia: str,
    calculo: dict,
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
        title="Produtividade Individual",
        author="Treinamentos Brasil vida",
        subject="Relatório individual de bonificação/produtividade",
    )
    story: list = []
    base_font, bold_font, label_style, value_style = _build_pdf_brand_header(
        story,
        title=f"Produtividade Individual • {calculo.get('tripulante_nome', '-')}",
        subtitle=f"Competência {competencia}",
        emitted_at=emitted_at,
    )

    resumo_rows = [
        [Paragraph("<b>Item</b>", label_style), Paragraph("<b>Valor</b>", label_style)],
        [Paragraph("Tripulante", value_style), Paragraph(str(calculo.get("tripulante_nome") or "-"), value_style)],
        [Paragraph("Base / Perfil", value_style), Paragraph(f"{calculo.get('base') or '-'} • {str(calculo.get('funcao') or '-').title()} • {calculo.get('categoria') or '-'}", value_style)],
        [Paragraph("Piso mínimo", value_style), Paragraph(decimal_to_currency(calculo.get("piso_minimo_mensal") or 0), value_style)],
        [Paragraph("Produtividade apurada", value_style), Paragraph(decimal_to_currency(calculo.get("total_produtividade") or 0), value_style)],
        [Paragraph("Valor final mês", value_style), Paragraph(decimal_to_currency(calculo.get("valor_final_mes") or 0), value_style)],
        [Paragraph("Critério final", value_style), Paragraph(str(calculo.get("criterio_fechamento") or "-"), value_style)],
    ]
    resumo_table = Table(resumo_rows, colWidths=[78 * mm, 57 * mm])
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d9e6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(resumo_table)
    story.append(Spacer(1, 4 * mm))

    memoria_rows = [
        [Paragraph("<b>Memória de cálculo</b>", label_style), ""],
        [Paragraph("Total missões válidas", value_style), Paragraph(str(calculo.get("total_missoes_validas") or 0), value_style)],
        [Paragraph("Valor total missões", value_style), Paragraph(decimal_to_currency(calculo.get("valor_total_missoes") or 0), value_style)],
        [Paragraph("Pernoites cobertura", value_style), Paragraph(str(calculo.get("total_pernoites_cobertura") or 0), value_style)],
        [Paragraph("Valor pernoites cobertura", value_style), Paragraph(decimal_to_currency(calculo.get("valor_total_pernoites_cobertura") or 0), value_style)],
        [Paragraph("Pernoites operacionais elegíveis", value_style), Paragraph(str(calculo.get("total_pernoites_operacionais_elegiveis") or 0), value_style)],
        [Paragraph("Valor pernoites operacionais", value_style), Paragraph(decimal_to_currency(calculo.get("valor_total_pernoites_operacionais") or 0), value_style)],
        [Paragraph("Adicional idioma", value_style), Paragraph(decimal_to_currency(calculo.get("valor_idioma") or 0), value_style)],
        [Paragraph("Adicional instrutor", value_style), Paragraph(decimal_to_currency(calculo.get("valor_instrutor") or 0), value_style)],
        [Paragraph("Adicional checador", value_style), Paragraph(decimal_to_currency(calculo.get("valor_checador") or 0), value_style)],
        [Paragraph("Adicional excepcional", value_style), Paragraph(decimal_to_currency(calculo.get("valor_adicional_excepcional") or 0), value_style)],
    ]
    memoria_table = Table(memoria_rows, colWidths=[90 * mm, 45 * mm])
    memoria_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("SPAN", (0, 0), (1, 0)),
                ("FONTNAME", (0, 0), (0, 0), bold_font),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d9e6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(memoria_table)

    footer = _build_pdf_footer_renderer(
        base_font=base_font,
        footer_left_text=f"Treinamentos Brasil vida • Produtividade individual • {calculo.get('tripulante_nome', '-')}",
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
            "Sumário executivo do manual",
            [
                "Este manual foi escrito para ser o documento oficial de treinamento e consulta do sistema Treinamentos Brasil vida. O material foi estruturado para atender tanto quem está iniciando quanto quem já atua diariamente na operação.",
                "A leitura recomendada para novos usuários é sequencial, do item 1 ao item 17. Para usuários experientes, o manual também funciona como referência rápida por tema: cadastros, operações, vencimentos, produtividade, relatórios, dashboards e administração de acesso.",
                "## Estrutura de leitura",
                "• 1. Apresentação do sistema",
                "• 2. Estrutura geral e navegação",
                "• 3. Acesso ao sistema",
                "• 4. Dashboard e visão geral",
                "• 5. Cadastros",
                "• 6. Operações",
                "• 7. Habilitações e vencimentos",
                "• 8. Bônus, produtividade e bonificação",
                "• 9. Relatórios",
                "• 10. Dashboards e painéis TV",
                "• 11. PDFs e documentos gerados",
                "• 12. Usuários e permissões",
                "• 13. Fluxo operacional recomendado",
                "• 14. Erros comuns e prevenção",
                "• 15. Solução de problemas",
                "• 16. Glossário operacional",
                "• 17. Padrão de governança e atualização contínua",
            ],
        ),
        (
            "1. Apresentação do sistema",
            [
                "O Treinamentos Brasil vida é uma plataforma operacional desenhada para centralizar processos críticos da operação de tripulação. Em vez de manter controles dispersos em planilhas, mensagens e anotações não rastreáveis, o sistema organiza dados de cadastros, treinamentos, vencimentos, missões, pernoites, produtividade e auditoria em um único ambiente.",
                "Na prática, o sistema resolve cinco problemas recorrentes de operação: falta de visão consolidada de vencimentos, risco de perda de prazo de habilitação, dificuldade de fechamento de produtividade mensal, baixa rastreabilidade dos lançamentos e inconsistência entre setores (operação, gestão e administração).",
                "A arquitetura do produto foi construída para conectar eventos operacionais e decisões gerenciais. O que é lançado em cadastros e operações alimenta relatórios, dashboards e painel TV, que por sua vez orientam ações corretivas e preventivas. Essa lógica reduz retrabalho e aumenta a confiabilidade do processo de fechamento.",
                "O sistema é usado por perfis com responsabilidades diferentes. Usuários de perfil operacional registram e atualizam dados do dia a dia (missões, pernoites, treinamentos e cadastros). Perfis de gestão analisam indicadores, criticidades e relatórios para tomada de decisão. Perfis administrativos definem permissões, monitoramento, backup e trilha de auditoria.",
                "Outro ponto central é a previsibilidade. O sistema aplica regras padronizadas para classificar vencimentos e calcular produtividade, diminuindo decisões subjetivas ou interpretações divergentes entre equipes. Como resultado, a organização ganha governança de processo e segurança operacional.",
                "Por fim, o produto também foi desenhado para comunicação institucional. Os relatórios e PDFs gerados seguem identidade visual corporativa e estrutura de leitura clara, permitindo compartilhar resultados com diretoria, coordenação e áreas de controle com confiabilidade e contexto técnico.",
            ],
        ),
        (
            "2. Estrutura geral do sistema e navegação",
            [
                "A navegação do sistema foi organizada por domínio funcional. Isso significa que as telas não são apresentadas em ordem aleatória, mas por natureza de uso: monitoramento (Dashboards), lançamento operacional (Operações), consulta analítica (Relatórios), base mestre (Cadastros) e governança de acesso/infraestrutura (Usuários).",
                "## 2.1 Lógica do menu lateral",
                "A barra lateral esquerda é o ponto principal de navegação. Ela concentra os grupos de módulos em formato expansível. Esse modelo evita poluição visual e permite que cada usuário visualize apenas o que realmente utiliza, melhorando foco e velocidade de uso.",
                "Dashboards concentra visão gerencial e painéis de acompanhamento contínuo. Operações concentra lançamentos de missão, pernoite e gestão de bases. Relatórios consolida visão analítica e emissão formal de dados. Cadastros armazena entidades-base da plataforma. Usuários reúne administração de contas, permissões, notificações, backup, monitoramento e auditoria.",
                "## 2.2 Como identificar onde você está",
                "O sistema destaca o grupo pai ativo e a tela ativa dentro do menu. Além disso, cada página possui título principal e subtítulo contextual no topo. Sempre que houver dúvida de contexto, valide primeiro o cabeçalho da tela e depois o item realçado no menu.",
                "## 2.3 Permissões e visibilidade de menu",
                "A visibilidade do menu respeita as permissões do usuário autenticado. Se uma aba não aparece, isso significa ausência de permissão para visualização. Mesmo quando uma rota existe, o backend também valida autorização. Portanto, não é possível liberar acesso apenas editando URL manualmente.",
                "## 2.4 Navegação recomendada no dia a dia",
                "Para rotina operacional, a sequência recomendada é: Dashboard para diagnóstico inicial -> Operações para correções ou lançamentos -> Relatórios para conferência -> Dashboards/Painel TV para monitoramento contínuo. Esse fluxo reduz divergências e garante visão de antes e depois de cada lançamento.",
                "## 2.5 Boas práticas de navegação",
                "• Evite abrir múltiplas abas com filtros distintos sem identificar cada contexto.",
                "• Antes de exportar um relatório, revise a seção de filtros na própria tela.",
                "• Em telas com botão de colapso de filtros no mobile, sempre confirme se o filtro foi aplicado de fato (não apenas preenchido).",
            ],
        ),
        (
            "3. Acesso ao sistema",
            [
                "## 3.1 Login e autenticação",
                "O acesso é feito com usuário e senha cadastrados no módulo de administração. Ao autenticar, a sessão é iniciada e as permissões são carregadas automaticamente. Isso define quais módulos serão exibidos no menu e quais ações estarão disponíveis em cada tela.",
                "Em caso de erro de autenticação, revise primeiro credenciais digitadas e teclado (maiúsculas, idioma e autocorreção em mobile). Persistindo o erro, valide com o administrador se a conta está ativa e se não houve troca de senha.",
                "## 3.2 Encerramento de sessão (logout)",
                "O logout deve ser feito pelo botão 'Sair' na barra lateral. Esse processo encerra a sessão de forma segura no servidor e reduz risco de uso indevido em dispositivos compartilhados.",
                "## 3.3 Comportamento de permissão",
                "Permissão é aplicada em duas camadas: interface e backend. Na interface, módulos sem acesso não aparecem. No backend, rotas sensíveis bloqueiam execução de ações sem autorização, mesmo que alguém tente acessar diretamente por URL.",
                "## 3.4 Erros comuns de acesso e correção",
                "• Tela em branco ou acesso negado: normalmente indica perfil sem permissão para aquela rota.",
                "• Não encontra aba no menu: validar permissões de visualização do módulo e submódulo.",
                "• Não consegue salvar dados: validar permissão de edição/criação no recurso específico.",
                "## 3.5 Segurança de credenciais",
                "Nunca compartilhe usuário e senha entre pessoas. A auditoria do sistema registra ações por usuário; contas compartilhadas quebram rastreabilidade e responsabilidade operacional. Recomenda-se troca periódica de senha e encerramento de sessão ao final de cada turno.",
                "<b>Nota operacional:</b> toda conta deve refletir uma pessoa real responsável por suas ações no sistema. Isso é essencial para conformidade e auditoria interna.",
            ],
        ),
        (
            "4. Dashboard / visão geral",
            [
                "O Dashboard é a tela de diagnóstico rápido da operação. O objetivo principal é transformar dados distribuídos em um panorama imediato de prioridade. Em poucos segundos, o usuário deve conseguir responder: o que está vencido, o que está próximo de vencer e qual ação precisa ser tomada agora.",
                "## 4.1 Interpretação dos cards e indicadores",
                "Os cards de topo mostram volume e criticidade. Eles não substituem o detalhe analítico, mas orientam foco. Exemplo: aumento de vencidos exige abrir imediatamente listas críticas e agir sobre registros de maior risco.",
                "## 4.2 Alertas e ação preventiva",
                "Os blocos de alerta foram desenhados para reduzir latência decisória. Quando um indicador crítico sobe, a navegação por atalho permite sair do diagnóstico e ir direto para a execução (edição de treinamento, ajuste de registro ou conferência de lançamento).",
                "## 4.3 Leitura por prioridade",
                "A ordem de leitura recomendada é: vencidos -> críticos próximos -> atenção intermediária -> situação regular. Isso evita que casos graves sejam mascarados por volume de dados menos urgentes.",
                "## 4.4 Relação com demais módulos",
                "O Dashboard é alimentado por cadastros e operações. Se houver inconsistência de dados no painel, a origem do problema normalmente está em lançamento incompleto, data inválida, tipo de registro incorreto ou ausência de vínculo entre entidades.",
                "## 4.5 Uso gerencial e operacional",
                "Gestão usa dashboard para priorização macro. Operação usa para executar tratativa pontual. Esse uso combinado transforma o dashboard em ferramenta de coordenação diária, não apenas visualização passiva.",
            ],
        ),
        (
            "5. Cadastros",
            [
                "Cadastros são a base estrutural do sistema. Quando um cadastro está incompleto ou inconsistente, relatórios, cálculos e alertas ficam comprometidos. Por isso, cadastros devem seguir padrão mínimo de qualidade e revisão periódica.",
                "## 5.1 Cadastro de tripulantes",
                "O cadastro de tripulantes concentra identidade operacional e parâmetros que impactam diretamente produtividade e elegibilidade de adicionais. Esse é um dos cadastros mais sensíveis da plataforma.",
                "Campo <b>Nome</b>: deve refletir o nome de uso operacional e institucional. Evite abreviações que possam gerar ambiguidade em relatórios e auditoria.",
                "Campo <b>Base</b>: define localização operacional principal do tripulante e influencia agrupamentos em dashboards e relatórios.",
                "Campo <b>Função operacional</b>: determina papel no cálculo (ex.: comandante, copiloto, outro). Escolha incorreta altera piso mínimo e valor por missão.",
                "Campo <b>Categoria operacional</b>: classifica regras de cálculo (A, B ou N/A). Tripulantes N/A podem ficar fora de determinados fluxos de bonificação dependendo da regra ativa.",
                "Campo <b>SDEA ativo</b>: habilita adicional mensal de idioma quando aplicável.",
                "Campo <b>Instrutor designado</b>: habilita adicional fixo de instrutoria no período.",
                "Campo <b>Checador designado</b>: habilita adicional fixo de checagem; a regra evita acumulações indevidas fora do padrão parametrizado.",
                "Campo <b>Status ativo/inativo</b>: controla disponibilidade do tripulante na operação e evita uso indevido em apuração mensal.",
                "Campo <b>Elegível para adicional excepcional</b>: indica se o tripulante pode receber regra excepcional parametrizada ou lançamento manual.",
                "## 5.2 Cadastro de equipamentos",
                "Equipamentos padronizam contexto técnico dos treinamentos e dão rastreabilidade à habilitação. Cadastre nome oficial, mantenha status ativo/inativo e evite múltiplos registros para o mesmo equipamento com grafia diferente.",
                "## 5.3 Cadastro de tipos de treinamento",
                "Define natureza do treinamento, periodicidade e exigência de equipamento. Esse cadastro influencia cálculo automático de vencimento quando a data de realização é informada.",
                "## 5.4 Cadastro de treinamentos realizados",
                "Relaciona tripulante, tipo e equipamento. Permite vencimento automático ou manual e suporta anexos PDF comprobatórios (quando habilitado no fluxo). Erro em data de realização, modo de vencimento ou tipo impacta diretamente criticidade e envio de alertas.",
                "## 5.5 Boas práticas cadastrais",
                "• Padronize escrita de nomes e contratantes.",
                "• Evite campos livres para informação que já possui campo estruturado.",
                "• Revise registros inativos periodicamente para não contaminar análises.",
                "• Sempre valide se o cadastro novo realmente não existe antes de criar.",
            ],
        ),
        (
            "6. Operações",
            [
                "O módulo Operações materializa o que aconteceu na atividade real. Essa camada é essencial para a qualidade da produtividade mensal. Se o lançamento operacional falhar, o fechamento financeiro e gerencial ficará incorreto.",
                "## 6.1 Missões",
                "A missão representa o chamado operacional. O registro deve conter identificador do voo/chamado, contratante, período, origem, destino, tipo de operação e equipe vinculada. Essa estrutura evita contagem por trecho e preserva lógica de missão consolidada.",
                "Regra central: uma missão não deve ser duplicada por etapas da mesma operação. O sistema considera consolidação por identificador operacional e contratante conforme regra vigente.",
                "Campo 'conta como missão válida' deve ser utilizado com critério. Nem todo deslocamento operacional representa missão elegível para bonificação.",
                "## 6.2 Pernoites",
                "Pernoites devem ser registrados por tripulante, com data, tipo e quantidade. O tipo precisa distinguir <b>cobertura de base</b> de <b>pernoite operacional comum</b>, pois cada um pode ter tratamento financeiro diferente.",
                "Quando uma missão gera pernoite para toda equipe, pode-se usar lançamento automático vinculado à missão para reduzir retrabalho. Ainda assim, é responsabilidade do usuário confirmar se a data e o tipo foram aplicados corretamente.",
                "## 6.3 Gestão de bases",
                "A gestão de bases oferece visão espacial e operacional da equipe por base. É útil para tratar concentração de risco, distribuição de pendências e criticidade por localidade.",
                "## 6.4 Relação entre operações e produtividade",
                "Missões e pernoites são insumos diretos da engine de produtividade. Lançamento fora da competência correta, tipo inadequado de pernoite ou missão sem vínculo de tripulante causam divergência de apuração.",
                "## 6.5 Exemplo prático de rotina operacional",
                "Exemplo: no fechamento de um dia, a equipe lança missão do chamado X, vincula tripulantes, confirma se conta para produtividade, registra pernoites derivados e revisa no relatório do mês se os eventos entraram na competência correta.",
            ],
        ),
        (
            "7. Habilitações e vencimentos",
            [
                "Habilitação é o registro de capacidade técnica com validade temporal. O sistema acompanha o ciclo de vencimento e classifica criticidade para orientar ação preventiva antes da quebra de conformidade operacional.",
                "## 7.1 Lógica de criticidade visual",
                "As cores traduzem urgência: verde (mais de 90 dias), amarelo (até 90 dias), laranja (até 60 dias), vermelho (até 30 dias), vermelho pulsante (até 15 dias) e vencido (criticidade máxima).",
                "Quando não há data válida de vencimento, o sistema apresenta estado neutro para indicar necessidade de regularização cadastral. Estado neutro não é estado seguro; é estado sem base suficiente para avaliação de risco.",
                "## 7.2 Vencimento mais crítico por tripulante",
                "Em listas de tripulantes e indicadores visuais de foto/avatar, o sistema considera a habilitação mais crítica (a que vence primeiro ou já venceu). Isso facilita priorização sem exigir leitura de todos os registros de imediato.",
                "## 7.3 Consolidação por tripulante",
                "No relatório consolidado, cada tripulante é apresentado com todas as habilitações relevantes. A combinação entre agrupamento por pessoa e detalhe por habilitação permite agir no macro e no micro sem perder contexto.",
                "## 7.4 Impacto operacional",
                "Vencimentos críticos afetam escala, risco de indisponibilidade e necessidade de regularização imediata. A recomendação é rotina de conferência diária para críticos e vencidos, e semanal para janelas de 30, 60 e 90 dias.",
                "## 7.5 Erros que distorcem a visão de vencimento",
                "• Data de realização sem periodicidade corretamente definida no tipo de treinamento.",
                "• Data de vencimento manual lançada com formato ou ano incorreto.",
                "• Treinamento cadastrado para tripulante ou equipamento errado.",
                "• Registro duplicado sem invalidação do anterior.",
            ],
        ),
        (
            "8. Bônus / produtividade / bonificação",
            [
                "Esta é a seção mais crítica do manual. A produtividade mensal depende de regras que combinam perfil do tripulante, lançamentos operacionais e parâmetros financeiros. A boa prática é sempre conferir memória de cálculo, não apenas o valor final.",
                "## 8.1 Conceito de competência",
                "Competência é o mês de referência da apuração (formato YYYY-MM). Todos os eventos considerados no cálculo precisam estar corretamente posicionados nesse período.",
                "## 8.2 Entradas obrigatórias da engine",
                "A engine considera: tripulante, categoria operacional, função, missões válidas, pernoites elegíveis, SDEA ativo, instrutor ativo, checador ativo, elegibilidade para adicional excepcional, piso mínimo aplicável e parâmetros de valor por parcela.",
                "## 8.3 Regra de fechamento",
                "A regra final é: <b>valor_final_mes = max(piso_minimo_mensal, total_produtividade)</b>. Isso garante piso quando produtividade for menor e premia produtividade quando ultrapassar o piso.",
                "## 8.4 Composição da produtividade",
                "Total de produtividade pode incluir: valor de missões, valor de pernoites de cobertura, valor de pernoites operacionais elegíveis (quando regra ativa), adicional de idioma (SDEA), adicional de instrutor, adicional de checador e adicional excepcional (manual ou parametrizado).",
                "## 8.5 Categoria e função",
                "Categoria A e B possuem parâmetros distintos de piso e valor por missão/pernoite. Função (comandante/copiloto/outro) também altera regra aplicável. Cadastro incorreto de categoria/função é causa clássica de valor final divergente.",
                "## 8.6 Missão válida e anti-duplicidade",
                "A missão não deve ser contada por trecho. A consolidação por identificador e contratante impede duplicidade indevida. Sempre confirme se registros da mesma operação não foram lançados como missões independentes.",
                "## 8.7 Pernoites elegíveis",
                "Pernoites de cobertura e pernoites operacionais têm natureza diferente. Se a regra operacional comum exige contagem a partir do segundo dia, a engine respeita essa configuração. Por isso, classificar tipo de pernoite corretamente é obrigatório.",
                "## 8.8 Adicional excepcional",
                "Adicional excepcional deve ser tratado como regra controlada, não improvisada. Sempre que houver lançamento manual, registrar justificativa interna e manter rastreabilidade para auditoria.",
                "## 8.9 Memória de cálculo",
                "A memória de cálculo exibe cada parcela usada na apuração, critérios de validação e critério final de fechamento. Essa memória é o principal instrumento de conferência técnica e transparência com a gestão.",
                "## 8.10 Exemplo didático 1 (fechamento por piso)",
                "Tripulante categoria A, função comandante, com poucas missões no mês. Piso = R$ 3.000,00. Produtividade apurada = R$ 2.400,00. Valor final = R$ 3.000,00 por critério de piso mínimo.",
                "## 8.11 Exemplo didático 2 (fechamento por produtividade)",
                "Tripulante categoria B, função comandante, com alto volume operacional. Piso = R$ 6.000,00. Produtividade apurada = R$ 8.200,00. Valor final = R$ 8.200,00 por critério de produtividade apurada.",
                "## 8.12 Exemplo didático 3 (divergência por cadastro)",
                "Se o tripulante foi cadastrado como categoria N/A por engano, a engine pode não aplicar piso/cálculo esperado. Resultado: valor final abaixo da expectativa. Correção: ajustar categoria e recalcular competência.",
                "## 8.13 Conferência operacional recomendada",
                "Antes de validar o fechamento, conferir em sequência: categoria e função do tripulante, total de missões, total de pernoites por tipo, flags de adicionais ativos, adicional excepcional aplicado e critério final.",
            ],
        ),
        (
            "9. Relatórios",
            [
                "Relatórios existem para converter dados em decisão. O uso correto depende de três pontos: seleção de filtros, leitura da estrutura de saída e validação de coerência com lançamentos operacionais.",
                "## 9.1 Relatório individual",
                "Indicado para conferência detalhada por pessoa. Mostra memória de cálculo, eventos considerados, parcelas e valor final. É o primeiro relatório a consultar quando há divergência individual.",
                "## 9.2 Relatório geral de produtividade",
                "Indicado para fechamento mensal e visão comparativa da equipe. Permite ordenar por valor final, produtividade, base e nome, além de aplicar filtros de competência, função, categoria e base.",
                "## 9.3 Consolidado de habilitações",
                "Indicado para gestão preventiva de vencimentos. Agrupa por tripulante e lista habilitações com data, dias restantes e status. Deve ser usado para priorizar tratativas e organizar regularização.",
                "## 9.4 Como aplicar filtros corretamente",
                "Sempre aplique filtros antes de interpretar totais. Filtro preenchido e não aplicado ainda não altera resultado. Após aplicar, confirme no topo da tela se os dados correspondem ao contexto esperado.",
                "## 9.5 Validação de consistência",
                "Se um total parecer incoerente, valide: período, status, base, duplicidade de lançamentos e categoria/função. Em produtividade, valide também se houve mudança cadastral no meio da competência.",
                "## 9.6 Uso para decisão",
                "Relatórios apoiam decisão operacional (o que corrigir hoje), gerencial (prioridade por base/equipe) e administrativa (fechamento e auditoria). Relatório sem análise contextual vira apenas arquivo; relatório com conferência vira governança.",
            ],
        ),
        (
            "10. Dashboards e painéis TV",
            [
                "Dashboard convencional e painel TV têm propósitos diferentes. O dashboard padrão é interativo e analítico. O painel TV é de monitoramento contínuo, leitura à distância e foco em criticidade imediata.",
                "## 10.1 Painel TV de vencimentos",
                "Mostra totais consolidados, próximos vencimentos, críticos e vencidos com destaque visual forte. Deve ser usado em ambiente de acompanhamento constante para prevenção de risco operacional.",
                "## 10.2 Painel TV de produtividade",
                "Exibe indicadores da competência, rankings e blocos de desempenho. O objetivo não é detalhar linha a linha, mas apresentar sinal executivo para tomada de decisão rápida.",
                "## 10.3 Leitura operacional dos painéis",
                "Cards de topo respondem 'quanto'. Rankings e listas respondem 'onde' e 'quem'. Alertas respondem 'o que precisa de ação agora'.",
                "## 10.4 Boas práticas de exibição contínua",
                "• Usar tela dedicada em modo cheio.",
                "• Garantir atualização automática ativa.",
                "• Evitar uso de scroll manual para monitoramento TV.",
                "• Revisar diariamente se os dados do painel refletem lançamentos mais recentes.",
            ],
        ),
        (
            "11. PDFs e documentos gerados",
            [
                "O sistema gera PDFs oficiais para consolidados e relatórios individuais. Diferente de 'print de tela', o PDF oficial é construído com dados estruturados, paginação, cabeçalho corporativo e controle de emissão.",
                "## 11.1 Quando gerar cada documento",
                "Consolidado de habilitações: para reunião de criticidade e plano de regularização. Consolidado de produtividade: para fechamento mensal da equipe. Individual de produtividade: para conferência específica por tripulante.",
                "## 11.2 Checklist antes de compartilhar",
                "• Validar filtros aplicados e competência.",
                "• Validar data/hora de emissão.",
                "• Validar se o total exibido no PDF bate com a tela de origem.",
                "• Confirmar se não há registros pendentes de atualização no mesmo período.",
                "## 11.3 Uso institucional",
                "Para documentação oficial, sempre utilize PDF emitido pelo sistema após conferência. Evite versões intermediárias, prints ou arquivos exportados antes da validação final do responsável.",
                "## 11.4 Riscos de uso indevido",
                "Compartilhar relatório sem validar filtro é um erro frequente. Outro risco é usar PDF antigo para decisão atual. Sempre confira competência, emissão e escopo antes de enviar.",
            ],
        ),
        (
            "12. Usuários e permissões",
            [
                "Usuários e permissões definem fronteira de responsabilidade do sistema. Uma boa configuração reduz risco de acesso indevido e evita alterações por pessoas sem atribuição operacional para aquela área.",
                "## 12.1 Cadastro e edição de usuários",
                "Ao criar usuário, informe dados de identificação, status da conta e perfil inicial. Em edição, revise permissões por módulo e submódulo de acordo com função real da pessoa na organização.",
                "## 12.2 Permissões por aba e subaba",
                "O controle pode distinguir visualização, criação, edição e exclusão (quando aplicável). A recomendação é liberar apenas o mínimo necessário para execução da função.",
                "## 12.3 Efeito das permissões na navegação",
                "A sidebar reflete permissões ativas. Itens não autorizados não aparecem. Mesmo assim, backend também impede execução direta por URL sem autorização.",
                "## 12.4 Riscos de permissões mal configuradas",
                "Permissão excessiva aumenta risco de exclusões acidentais e alterações indevidas. Permissão insuficiente trava operação e gera retrabalho por dependência desnecessária de administradores.",
                "## 12.5 Boas práticas administrativas",
                "• Revisar permissões mensalmente.",
                "• Remover acesso imediatamente em desligamento/mudança de função.",
                "• Evitar contas genéricas compartilhadas.",
                "• Registrar responsável pela aprovação de acessos críticos.",
            ],
        ),
        (
            "13. Fluxo operacional recomendado",
            [
                "A rotina recomendada abaixo ajuda a manter consistência e previsibilidade. O objetivo é evitar acúmulo de correções no fechamento mensal.",
                "## 13.1 Rotina diária",
                "1) Abrir Dashboard e identificar críticos/vencidos. 2) Registrar missões e pernoites do dia. 3) Validar se treinamentos lançados refletem documentos recebidos. 4) Revisar alertas de vencimento imediato.",
                "## 13.2 Rotina semanal",
                "1) Revisar consolidado de habilitações por base. 2) Verificar pendências sem data de vencimento. 3) Validar consistência de tripulantes ativos/inativos. 4) Auditar amostra de lançamentos operacionais.",
                "## 13.3 Fechamento mensal",
                "1) Confirmar competência. 2) Conferir lançamentos de missão e pernoite no período. 3) Revisar flags de adicionais (SDEA/instrutor/checador). 4) Validar adicional excepcional. 5) Emitir consolidado e individuais. 6) Marcar relatórios como conferidos pelo responsável.",
                "## 13.4 Governança de envio e documentação",
                "Após conferência, emitir PDFs oficiais e arquivar conforme política interna. Em paralelo, manter log de ações e histórico de backup atualizado para rastreabilidade.",
            ],
        ),
        (
            "14. Erros comuns e como evitar",
            [
                "## 14.1 Cadastro incompleto de tripulante",
                "Como acontece: usuário preenche nome e base, mas deixa categoria/função incorreta. Impacto: cálculo de produtividade inconsistente. Como evitar: checklist obrigatório no cadastro inicial e revisão por responsável.",
                "## 14.2 Missão duplicada por trecho",
                "Como acontece: mesma operação é lançada em múltiplas linhas independentes. Impacto: supercontagem de missão. Como evitar: padronizar identificador operacional + contratante e revisar duplicidade antes de salvar.",
                "## 14.3 Pernoite em tipo errado",
                "Como acontece: cobertura de base lançada como operacional comum (ou inverso). Impacto: valor de adicional distorcido. Como evitar: treinar equipe na diferença de tipologia e revisar amostragem semanal.",
                "## 14.4 Vencimento manual inconsistente",
                "Como acontece: data manual preenchida com ano incorreto ou fora de padrão. Impacto: alerta falso ou ausência de alerta real. Como evitar: validação dupla antes de salvar e revisão em relatório consolidado.",
                "## 14.5 Interpretação incorreta de relatório",
                "Como acontece: usuário analisa resultado sem observar filtro aplicado. Impacto: decisão baseada em escopo errado. Como evitar: confirmar filtros no topo da tela e no cabeçalho do PDF.",
                "## 14.6 Permissões inadequadas",
                "Como acontece: usuário operacional recebe acesso administrativo amplo. Impacto: risco de alteração indevida em usuários, backups e configurações críticas. Como evitar: política de menor privilégio e revisão periódica.",
            ],
        ),
        (
            "15. Solução de problemas",
            [
                "Esta seção orienta diagnóstico prático quando algo parecer inconsistente. A regra é sempre começar pelo contexto (competência, filtros, permissões) antes de concluir que o sistema está com erro.",
                "## 15.1 Relatório sem dados",
                "Possíveis causas: filtro restritivo, competência sem lançamentos, usuário sem permissão de visualização completa. O que verificar: filtros ativos, data de referência e perfil do usuário.",
                "## 15.2 Produtividade zerada ou muito baixa",
                "Possíveis causas: missões não marcadas como válidas, pernoites ausentes/errados, tripulante inativo, categoria/função incorreta. O que verificar: memória de cálculo do relatório individual e registros operacionais do mês.",
                "## 15.3 Vencimentos não aparecem em notificações",
                "Possíveis causas: data de vencimento ausente, destinatário inativo, rotina diária não executada, regras de janela de envio. O que verificar: cadastro de treinamento, destinatários ativos e histórico de execução.",
                "## 15.4 Falha em backup",
                "Possíveis causas: diretório sem permissão, storage indisponível, credencial de ambiente ausente. O que verificar: tela de backups, logs da rotina e variáveis de ambiente configuradas.",
                "## 15.5 Erro de acesso em página específica",
                "Possíveis causas: permissão ausente para a rota, conta inativa, sessão expirada. O que verificar: perfil do usuário, permissões por módulo e reautenticação.",
                "## 15.6 Quando acionar suporte interno",
                "Acione suporte quando: houver divergência persistente após conferência de dados, falha recorrente de rotina automática, erro de permissão sem causa aparente ou inconsistência estrutural entre telas.",
                "<b>Nota de suporte:</b> ao reportar problema, inclua usuário, horário, tela, filtro aplicado, competência e passos exatos para reproduzir. Isso reduz tempo de diagnóstico.",
            ],
        ),
        (
            "16. Glossário completo",
            [
                "## Conceitos de operação",
                "• <b>Competência:</b> mês de referência da apuração de produtividade.",
                "• <b>Missão:</b> chamado operacional consolidado por identificador e contratante.",
                "• <b>Pernoite:</b> permanência operacional com classificação por tipo.",
                "• <b>Cobertura de base:</b> pernoite elegível para regra específica de adicional de cobertura.",
                "## Conceitos de cálculo e gestão",
                "• <b>Categoria operacional:</b> classificação (A, B ou N/A) que altera parâmetros de piso e produtividade.",
                "• <b>Piso mínimo:</b> valor garantido mensal quando produtividade apurada não alcança o mínimo configurado.",
                "• <b>Produtividade apurada:</b> soma das parcelas elegíveis da competência.",
                "• <b>Bonificação:</b> resultado financeiro final após aplicação das regras.",
                "• <b>Memória de cálculo:</b> detalhamento das parcelas e validações utilizadas pela engine.",
                "## Conceitos de vencimento e monitoramento",
                "• <b>Habilitação:</b> qualificação com validade temporal vinculada ao tripulante.",
                "• <b>Vencimento:</b> data limite de validade da habilitação.",
                "• <b>Criticidade:</b> nível de urgência conforme proximidade do vencimento.",
                "• <b>Dashboard:</b> visão analítica e interativa para decisão.",
                "• <b>Painel TV:</b> visão contínua para monitoramento à distância.",
                "## Conceitos administrativos",
                "• <b>Permissão:</b> autorização para visualizar ou executar ações em módulos específicos.",
                "• <b>Log de ações:</b> histórico auditável de eventos relevantes do sistema.",
                "• <b>Backup:</b> cópia de segurança para recuperação de dados em caso de falha.",
            ],
        ),
        (
            "17. Governança, atualização e uso institucional do manual",
            [
                "Este manual deve ser tratado como documento vivo. Sempre que houver mudança de regra de negócio, nova tela, ajuste de cálculo ou alteração de permissão, a versão oficial deve ser atualizada para refletir o comportamento real do sistema.",
                "A recomendação é manter revisão formal em ciclo regular (ex.: mensal ou por release), com validação conjunta entre operação, gestão e administração técnica. Isso evita descompasso entre sistema e procedimento escrito.",
                "Para treinamento de novos usuários, usar este manual em conjunto com demonstração prática no ambiente homologado. Para usuários experientes, utilizar como base de conferência, padronização e solução de dúvida operacional.",
                "Fechamentos mensais, auditorias internas e compartilhamentos institucionais devem sempre se apoiar em processos descritos aqui: dados consistentes, conferência de filtros, revisão de memória de cálculo e emissão formal de documentos.",
                "Encerramento: ao seguir este manual, a organização reduz risco operacional, aumenta rastreabilidade e melhora previsibilidade de decisão. O ganho principal não é apenas técnico, mas de governança e confiabilidade do processo.",
            ],
        ),
    ]

    page_break_after_titles = {
        "1. Apresentação do sistema",
        "4. Dashboard / visão geral",
        "8. Bônus / produtividade / bonificação",
        "12. Usuários e permissões",
        "15. Solução de problemas",
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
