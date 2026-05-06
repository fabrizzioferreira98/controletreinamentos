from __future__ import annotations

from flask import request

from ....application.operacoes import get_pernoite_read_model, list_pernoites_read_model
from ....auth import permission_required
from ....blueprints.operacoes import operacoes_bp
from ....core.domain_errors import DomainError
from ....core.http_utils import domain_error_payload
from ....core.utils import json_response_with_etag


def _handle_domain_error(exc: Exception):
    if isinstance(exc, DomainError):
        return domain_error_payload(exc)
    raise exc


@operacoes_bp.route("/api/v1/operacoes/pernoites", methods=["GET"])
@permission_required("pernoites:view")
def api_operacoes_pernoites_list():
    payload = list_pernoites_read_model(
        tipo=request.args.get("tipo", "").strip(),
        tripulante=request.args.get("tripulante", "").strip(),
        page=request.args.get("page", default=1),
        per_page=request.args.get("per_page", default=20),
    )
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "operacoes_pernoites_list_ok",
            "pernoites": payload,
        },
        max_age=15,
    )


@operacoes_bp.route("/api/v1/operacoes/pernoites/<int:pernoite_id>", methods=["GET"])
@permission_required("pernoites:view")
def api_operacoes_pernoite_detail(pernoite_id: int):
    try:
        payload = get_pernoite_read_model(pernoite_id=pernoite_id)
    except DomainError as exc:
        return _handle_domain_error(exc)
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "operacoes_pernoite_ok",
            "pernoite": payload["item"],
        },
        max_age=15,
    )
