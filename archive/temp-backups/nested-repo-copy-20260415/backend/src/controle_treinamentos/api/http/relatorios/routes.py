from __future__ import annotations

from flask import request
from flask_login import current_user

from ....application.relatorios import (
    ProdutividadeConferenciaValidationError,
    get_habilitacoes_report_data,
    get_produtividade_report_data,
    set_produtividade_conferencia,
)
from ....auth import permission_required
from ....blueprints.relatorios import relatorios_bp
from ....core.http_utils import error_payload
from ....core.utils import json_response_with_etag
from ....db import get_db


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}
    return payload


@relatorios_bp.route("/api/v1/relatorios/habilitacoes", methods=["GET"])
@permission_required("relatorio_habilitacoes:view")
def api_relatorios_habilitacoes():
    payload = get_habilitacoes_report_data(
        get_db(),
        nome=request.args.get("nome", "").strip(),
        base=request.args.get("base", "").strip(),
        status=request.args.get("status", "").strip(),
        tipo=request.args.get("tipo", "").strip(),
        ordenacao=request.args.get("ordenacao", "").strip(),
    )
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "relatorio_habilitacoes_ok",
            "report": payload,
        },
        max_age=20,
    )


@relatorios_bp.route("/api/v1/relatorios/produtividade", methods=["GET"])
@permission_required("relatorio_produtividade:view")
def api_relatorios_produtividade():
    payload = get_produtividade_report_data(
        get_db(),
        competencia=request.args.get("competencia", "").strip(),
        nome=request.args.get("nome", "").strip(),
        base=request.args.get("base", "").strip(),
        funcao=request.args.get("funcao", "").strip(),
        categoria=request.args.get("categoria", "").strip(),
        ordenacao=request.args.get("ordenacao", "valor_final").strip(),
    )
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "relatorio_produtividade_ok",
            "report": payload,
        },
        max_age=20,
    )


@relatorios_bp.route("/api/v1/relatorios/produtividade/conferencias", methods=["POST"])
@permission_required("relatorio_produtividade:view")
def api_relatorios_produtividade_conferencias():
    payload = _json_payload()
    try:
        tripulante_id = int(payload.get("tripulante_id") or 0)
        if tripulante_id <= 0:
            raise ProdutividadeConferenciaValidationError("Tripulante inválido para conferência.", code="tripulante_not_found")
        result = set_produtividade_conferencia(
            get_db(),
            tripulante_id=tripulante_id,
            competencia=str(payload.get("competencia") or ""),
            action=str(payload.get("action") or ""),
            user_id=int(current_user.id),
        )
    except ValueError:
        return error_payload("Tripulante inválido para conferência.", status=400, code="tripulante_not_found")
    except ProdutividadeConferenciaValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "produtividade_conferencia_saved",
        "operation": result["operation"],
        "message": result["message"],
        "conferencia": result["conferencia"],
    }, 200
