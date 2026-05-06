from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def _normalized_habilitacoes_filters(raw_filters: Mapping[str, str | None]) -> dict[str, str]:
    return {
        "nome": str(raw_filters.get("nome", "") or "").strip(),
        "base": str(raw_filters.get("base", "") or "").strip(),
        "status": str(raw_filters.get("status", "") or "").strip(),
        "tipo": str(raw_filters.get("tipo", "") or "").strip(),
        "ordenacao": str(raw_filters.get("ordenacao", "") or "").strip(),
    }


def _load_habilitacoes_report(
    *,
    raw_filters: Mapping[str, str | None],
    get_db_fn: Callable[[], Any],
    report_loader: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    filters = _normalized_habilitacoes_filters(raw_filters)
    return report_loader(
        get_db_fn(),
        nome=filters["nome"],
        base=filters["base"],
        status=filters["status"],
        tipo=filters["tipo"],
        ordenacao=filters["ordenacao"],
    )


def get_treinamentos_consolidado_context(
    *,
    raw_filters: Mapping[str, str | None],
    get_db_fn: Callable[[], Any],
    report_loader: Callable[..., dict[str, Any]],
    html_context_builder: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    report = _load_habilitacoes_report(
        raw_filters=raw_filters,
        get_db_fn=get_db_fn,
        report_loader=report_loader,
    )
    return html_context_builder(report)


def get_treinamentos_consolidado_relatorio_context(
    *,
    raw_filters: Mapping[str, str | None],
    get_db_fn: Callable[[], Any],
    report_loader: Callable[..., dict[str, Any]],
    print_context_builder: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    report = _load_habilitacoes_report(
        raw_filters=raw_filters,
        get_db_fn=get_db_fn,
        report_loader=report_loader,
    )
    return print_context_builder(report)


def build_treinamentos_consolidado_pdf_export(
    *,
    raw_filters: Mapping[str, str | None],
    now,
    get_db_fn: Callable[[], Any],
    report_loader: Callable[..., dict[str, Any]],
    export_payload_builder: Callable[[dict[str, Any]], dict[str, Any]],
    pdf_builder: Callable[..., bytes],
    safe_pdf_filename_fn: Callable[..., str],
    audit_document_generation_fn: Callable[..., Any],
    pdf_policy,
) -> dict[str, Any]:
    report = _load_habilitacoes_report(
        raw_filters=raw_filters,
        get_db_fn=get_db_fn,
        report_loader=report_loader,
    )
    export_payload = export_payload_builder(report)
    pdf_bytes = pdf_builder(
        summary=export_payload["summary"],
        tripulantes_grouped=export_payload["tripulantes_grouped"],
        filtros_aplicados=export_payload["filtros_aplicados"],
        emitted_at=export_payload["emitted_at"],
    )
    filename = safe_pdf_filename_fn(
        f"consolidado_habilitacoes_{now.strftime('%Y%m%d_%H%M%S')}.pdf",
        fallback="consolidado_habilitacoes.pdf",
    )
    audit_document_generation_fn(
        policy=pdf_policy,
        filename=filename,
        filters=export_payload["filtros_aplicados"],
        details={
            "summary": export_payload["summary"],
            "groups_count": len(export_payload["tripulantes_grouped"]),
        },
        commit=True,
    )
    return {
        "filename": filename,
        "pdf_bytes": pdf_bytes,
    }


def build_treinamentos_consolidado_csv_export(
    *,
    raw_filters: Mapping[str, str | None],
    now,
    get_db_fn: Callable[[], Any],
    report_loader: Callable[..., dict[str, Any]],
    csv_export_builder: Callable[[dict[str, Any]], dict[str, Any]],
    export_payload_builder: Callable[[dict[str, Any]], dict[str, Any]],
    audit_document_generation_fn: Callable[..., Any],
) -> dict[str, Any]:
    report = _load_habilitacoes_report(
        raw_filters=raw_filters,
        get_db_fn=get_db_fn,
        report_loader=report_loader,
    )
    csv_export = csv_export_builder(report)
    export_payload = export_payload_builder(report)
    filename = f"consolidado_habilitacoes_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    audit_document_generation_fn(
        policy_key="habilitacoes_export_csv",
        kind="csv_export",
        domain="relatorios.habilitacoes",
        renderer="habilitacoes_report_to_csv_export",
        filename=filename,
        filters=export_payload["filtros_aplicados"],
        details={
            "summary": export_payload["summary"],
            "groups_count": len(export_payload["tripulantes_grouped"]),
        },
        commit=True,
    )
    return {
        "content": csv_export["content"],
        "content_type": csv_export["content_type"],
        "filename": filename,
    }
