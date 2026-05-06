from __future__ import annotations

import csv
import io
from decimal import Decimal

from ..core.utils import format_competencia_label


def _as_int(value) -> int:
    return int(value or 0)


def serialize_habilitacoes_report(context: dict) -> dict:
    summary = context.get("summary", {})
    filtros = context.get("filtros", {})
    return {
        "summary": {
            "total_tripulantes": _as_int(summary.get("total_tripulantes")),
            "total_habilitacoes": _as_int(summary.get("total_habilitacoes")),
            "total_em_dia": _as_int(summary.get("total_em_dia")),
            "total_vencer_90": _as_int(summary.get("total_vencer_90")),
            "total_vencer_60": _as_int(summary.get("total_vencer_60")),
            "total_vencer_30": _as_int(summary.get("total_vencer_30")),
            "total_critico_15": _as_int(summary.get("total_critico_15")),
            "total_vencido": _as_int(summary.get("total_vencido")),
        },
        "filters": {
            "nome": filtros.get("nome") or "",
            "base": filtros.get("base") or "",
            "status": filtros.get("status") or "",
            "tipo": filtros.get("tipo") or "",
            "ordenacao": filtros.get("ordenacao") or "criticidade",
        },
        "options": {
            "status": list(context.get("status_options", [])),
            "tipos": [
                {
                    "id": int(item["id"]),
                    "nome": item.get("nome") or "",
                }
                for item in context.get("tipo_options", [])
            ],
            "bases": [
                {
                    "nome": item.get("nome") or "",
                    "uf": item.get("uf") or "",
                }
                for item in context.get("base_options", [])
            ],
        },
        "items": [
            {
                "tripulante_id": int(group["tripulante_id"]),
                "tripulante_nome": group.get("tripulante_nome") or "",
                "base": group.get("base") or "",
                "funcao_cargo": group.get("funcao_cargo") or "",
                "has_habilitacoes": bool(group.get("has_habilitacoes") or group.get("habilitacoes")),
                "habilitacoes": [
                    {
                        "treinamento_id": item.get("treinamento_id"),
                        "tipo_treinamento_id": item.get("tipo_treinamento_id"),
                        "habilitacao_nome": item.get("habilitacao_nome") or "",
                        "data_vencimento": item.get("data_vencimento") or "",
                        "days_remaining": item.get("days_remaining"),
                        "days_remaining_label": item.get("days_remaining_label") or "",
                        "status_key": item.get("status_key") or "",
                        "status_label": item.get("status_label") or "",
                        "pulse": bool(item.get("pulse")),
                        "is_placeholder": bool(item.get("is_placeholder")),
                    }
                    for item in group.get("habilitacoes", [])
                ],
            }
            for group in context.get("tripulantes_grouped", [])
        ],
    }


_HABILITACAO_STATUS_CLASS_BY_KEY = {
    "vencido": "status-critical",
    "critico_15": "status-red",
    "vencer_30": "status-red",
    "vencer_60": "status-orange",
    "vencer_90": "status-yellow",
    "em_dia": "status-green",
    "sem_vencimento": "status-gray",
    "sem_habilitacao": "status-gray",
}


HABILITACOES_CSV_COLUMNS = [
    "Tripulante",
    "Base",
    "Funcao/Cargo",
    "Habilitacao",
    "Data de vencimento",
    "Dias restantes",
    "Status",
]
HABILITACOES_CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
HABILITACOES_CSV_DELIMITER = ";"
HABILITACOES_CSV_BOM = "\ufeff"


def _habilitacoes_status_classes(report: dict) -> dict[str, str]:
    status_options = report.get("options", {}).get("status", [])
    return {
        str(item.get("key") or ""): item.get("badge_class")
        or item.get("status_class")
        or _HABILITACAO_STATUS_CLASS_BY_KEY.get(str(item.get("key") or ""), "status-gray")
        for item in status_options
        if item.get("key")
    }


def _habilitacoes_report_group_to_legacy_group(group: dict, *, status_classes: dict[str, str]) -> dict:
    return {
        "tripulante_id": int(group["tripulante_id"]),
        "tripulante_nome": group.get("tripulante_nome") or "",
        "base": group.get("base") or "",
        "funcao_cargo": group.get("funcao_cargo") or "",
        "has_habilitacoes": bool(group.get("has_habilitacoes") or group.get("habilitacoes")),
        "habilitacoes": [
            {
                "treinamento_id": item.get("treinamento_id"),
                "tipo_treinamento_id": item.get("tipo_treinamento_id"),
                "habilitacao_nome": item.get("habilitacao_nome") or "",
                "data_vencimento": item.get("data_vencimento") or "",
                "days_remaining": item.get("days_remaining"),
                "days_remaining_label": item.get("days_remaining_label") or "",
                "status_key": item.get("status_key") or "",
                "status_label": item.get("status_label") or "",
                "status_class": status_classes.get(item.get("status_key"))
                or _HABILITACAO_STATUS_CLASS_BY_KEY.get(item.get("status_key"), "status-gray"),
                "pulse": bool(item.get("pulse")),
                "is_placeholder": bool(item.get("is_placeholder")),
            }
            for item in group.get("habilitacoes", [])
        ],
    }


def _habilitacoes_legacy_groups(report: dict) -> list[dict]:
    status_classes = _habilitacoes_status_classes(report)
    return [
        _habilitacoes_report_group_to_legacy_group(group, status_classes=status_classes)
        for group in report.get("items", [])
    ]


def _habilitacoes_display_filters(report: dict) -> dict[str, str]:
    filters = report.get("filters", {})
    return {
        "nome": _display_filter(filters.get("nome")),
        "base": _display_filter(filters.get("base")),
        "status": _display_filter(filters.get("status")),
        "tipo": _display_filter(filters.get("tipo")),
        "ordenacao": _display_filter(filters.get("ordenacao"), "criticidade"),
    }


def habilitacoes_report_to_html_context(report: dict) -> dict:
    options = report.get("options", {})
    return {
        "tripulantes_grouped": _habilitacoes_legacy_groups(report),
        "summary": dict(report.get("summary", {})),
        "status_options": list(options.get("status", [])),
        "tipo_options": list(options.get("tipos", [])),
        "base_options": list(options.get("bases", [])),
        "filtros": dict(report.get("filters", {})),
        "emitted_at": report.get("emitted_at") or "",
    }


def habilitacoes_report_to_print_context(report: dict) -> dict:
    context = habilitacoes_report_to_html_context(report)
    context["filtros_aplicados"] = _habilitacoes_display_filters(report)
    return context


def habilitacoes_report_to_export_payload(report: dict) -> dict:
    groups = _habilitacoes_legacy_groups(report)
    return {
        "summary": dict(report.get("summary", {})),
        "tripulantes_grouped": groups,
        "filtros_aplicados": _habilitacoes_display_filters(report),
        "emitted_at": report.get("emitted_at") or "",
    }


def _habilitacoes_report_to_csv_rows(report: dict) -> list[list[str]]:
    rows = []
    groups = _habilitacoes_legacy_groups(report)
    for group in groups:
        for item in group["habilitacoes"]:
            if item.get("is_placeholder"):
                continue
            rows.append(
                [
                    group.get("tripulante_nome") or "-",
                    group.get("base") or "-",
                    group.get("funcao_cargo") or "-",
                    item.get("habilitacao_nome") or "-",
                    item.get("data_vencimento") or "Sem vencimento informado",
                    item.get("days_remaining_label") or "Sem vencimento informado",
                    item.get("status_label") or "-",
                ]
            )
    return rows


def habilitacoes_report_to_csv_export(report: dict) -> dict:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=HABILITACOES_CSV_DELIMITER)
    writer.writerow(HABILITACOES_CSV_COLUMNS)
    writer.writerows(_habilitacoes_report_to_csv_rows(report))
    return {
        "content": f"{HABILITACOES_CSV_BOM}{output.getvalue()}",
        "content_type": HABILITACOES_CSV_CONTENT_TYPE,
        "columns": list(HABILITACOES_CSV_COLUMNS),
        "delimiter": HABILITACOES_CSV_DELIMITER,
    }


def _display_filter(value, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text or fallback
