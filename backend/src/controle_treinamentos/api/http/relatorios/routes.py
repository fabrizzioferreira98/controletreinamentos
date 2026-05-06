from __future__ import annotations

from flask import request

from ....application.relatorios import get_habilitacoes_report_data
from ....auth import permission_required
from ....blueprints.relatorios import relatorios_bp
from ....core.utils import json_response_with_etag
from ....db import get_db


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
