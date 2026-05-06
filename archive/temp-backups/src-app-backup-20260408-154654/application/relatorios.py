from __future__ import annotations

from datetime import datetime

from flask_login import current_user

from ..constants import TRIPULANTE_FUNCAO_OPTIONS
from ..contracts.relatorios import (
    serialize_habilitacoes_report,
    serialize_produtividade_conferencia,
    serialize_produtividade_report,
)
from ..core.audit_utils import audit_event
from ..db import fetch_unique_bases
from ..produtividade import BONIFICACAO_CATEGORIAS_ATIVAS, calculate_competencia_consolidada, parse_competencia
from ..repositories.dashboard_cache import build_habilitacoes_consolidadas_context, clear_panel_cache, get_panel_cache, set_panel_cache
from ..repositories.queries import fetch_competencias_disponiveis, fetch_produtividade_conferencias_map


class ProdutividadeConferenciaValidationError(ValueError):
    def __init__(self, message: str, *, status: int = 400, code: str = "produtividade_conferencia_invalid"):
        super().__init__(message)
        self.status = status
        self.code = code


def get_habilitacoes_report_data(
    db,
    *,
    nome: str = "",
    base: str = "",
    status: str = "",
    tipo: str = "",
    ordenacao: str = "",
) -> dict:
    cache_key = (
        f"api:relatorios:habilitacoes:{nome.lower()}:{base.lower()}:"
        f"{status.lower()}:{tipo.lower()}:{ordenacao.lower()}"
    )
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    payload = serialize_habilitacoes_report(
        build_habilitacoes_consolidadas_context(
            db,
            nome=nome,
            base=base,
            status=status,
            tipo=tipo,
            ordenacao=ordenacao,
        )
    )
    payload["emitted_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    set_panel_cache(cache_key, payload)
    return payload


def get_produtividade_report_data(
    db,
    *,
    competencia: str = "",
    nome: str = "",
    base: str = "",
    funcao: str = "",
    categoria: str = "",
    ordenacao: str = "valor_final",
) -> dict:
    normalized_competencia = parse_competencia(competencia)
    cache_key = (
        f"api:relatorios:produtividade:{normalized_competencia}:{nome.lower()}:{base.lower()}:"
        f"{funcao.lower()}:{categoria.lower()}:{ordenacao.lower()}"
    )
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached

    context = calculate_competencia_consolidada(
        db,
        competencia=normalized_competencia,
        base=base,
        funcao=funcao,
        categoria=categoria,
        nome=nome,
    )
    rows = context["rows"]
    if ordenacao == "produtividade":
        rows.sort(key=lambda item: (item["total_produtividade"], item["valor_final_mes"]), reverse=True)
    elif ordenacao == "nome":
        rows.sort(key=lambda item: item["tripulante_nome"].lower())
    elif ordenacao == "base":
        rows.sort(key=lambda item: (item["base"], item["tripulante_nome"].lower()))

    conferencias_map = fetch_produtividade_conferencias_map(
        db,
        competencia=context["competencia"],
        tripulante_ids=[row["tripulante_id"] for row in rows],
    )
    for row in rows:
        row["conferencia"] = conferencias_map.get(row["tripulante_id"])

    competencias_disponiveis = fetch_competencias_disponiveis(db)
    if context["competencia"] not in competencias_disponiveis:
        competencias_disponiveis.insert(0, context["competencia"])
    bases = [row["nome"] for row in fetch_unique_bases(db)]

    payload = serialize_produtividade_report(
        competencia=context["competencia"],
        summary=context["summary"],
        rows=rows,
        filtros={
            "nome": nome,
            "base": base,
            "funcao": funcao,
            "categoria": categoria,
            "ordenacao": ordenacao,
        },
        competencias_disponiveis=competencias_disponiveis,
        bases=bases,
        funcoes=TRIPULANTE_FUNCAO_OPTIONS,
        categorias=BONIFICACAO_CATEGORIAS_ATIVAS,
        emitted_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
    set_panel_cache(cache_key, payload)
    return payload


def set_produtividade_conferencia(
    db,
    *,
    tripulante_id: int,
    competencia: str,
    action: str,
    user_id: int,
) -> dict:
    normalized_competencia = parse_competencia(competencia)
    normalized_action = (action or "").strip().lower()
    if normalized_action not in {"mark", "unmark"}:
        raise ProdutividadeConferenciaValidationError("Ação de conferência inválida.")

    tripulante = db.execute("SELECT id FROM tripulantes WHERE id = %s", (tripulante_id,)).fetchone()
    if not tripulante:
        raise ProdutividadeConferenciaValidationError("Tripulante inválido para conferência.", code="tripulante_not_found")

    if normalized_action == "mark":
        previous = db.execute(
            "SELECT * FROM produtividade_conferencias WHERE tripulante_id = %s AND competencia = %s",
            (tripulante_id, normalized_competencia),
        ).fetchone()
        db.execute(
            """
            INSERT INTO produtividade_conferencias (tripulante_id, competencia, conferido_por, conferido_em)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (tripulante_id, competencia)
            DO UPDATE SET conferido_por = EXCLUDED.conferido_por, conferido_em = NOW()
            """,
            (tripulante_id, normalized_competencia, int(user_id)),
        )
        current = db.execute(
            """
            SELECT
                pc.tripulante_id,
                pc.competencia,
                pc.conferido_por,
                pc.conferido_em,
                u.nome AS conferido_por_nome
            FROM produtividade_conferencias pc
            JOIN usuarios u ON u.id = pc.conferido_por
            WHERE pc.tripulante_id = %s AND pc.competencia = %s
            """,
            (tripulante_id, normalized_competencia),
        ).fetchone()
        audit_event(
            db,
            "produtividade_conferencia",
            tripulante_id,
            "update" if previous else "create",
            anterior=dict(previous) if previous else None,
            novo=dict(current) if current else None,
            observacao=f"competencia={normalized_competencia}",
        )
        db.commit()
        clear_panel_cache("produtividade:")
        clear_panel_cache("api:relatorios:produtividade:")
        return {
            "operation": "marked",
            "message": "Conferência registrada com sucesso.",
            "conferencia": serialize_produtividade_conferencia(dict(current)),
        }

    previous = db.execute(
        """
        SELECT
            pc.tripulante_id,
            pc.competencia,
            pc.conferido_por,
            pc.conferido_em,
            u.nome AS conferido_por_nome
        FROM produtividade_conferencias pc
        JOIN usuarios u ON u.id = pc.conferido_por
        WHERE pc.tripulante_id = %s AND pc.competencia = %s
        """,
        (tripulante_id, normalized_competencia),
    ).fetchone()
    if previous:
        db.execute(
            "DELETE FROM produtividade_conferencias WHERE tripulante_id = %s AND competencia = %s",
            (tripulante_id, normalized_competencia),
        )
        audit_event(
            db,
            "produtividade_conferencia",
            tripulante_id,
            "delete",
            anterior=dict(previous),
            observacao=f"competencia={normalized_competencia}",
        )
        db.commit()
    clear_panel_cache("produtividade:")
    clear_panel_cache("api:relatorios:produtividade:")
    return {
        "operation": "unmarked",
        "message": "Conferência removida.",
        "conferencia": None,
    }
