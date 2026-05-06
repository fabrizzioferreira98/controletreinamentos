from __future__ import annotations

import re

from flask import Response, g, request, send_file
from flask_login import current_user

from ....application.financeiro_bonificacoes import (
    detalhar_bonificacao_horaria,
    detalhar_bonificacao_produtividade_por_tripulante,
    listar_bonificacoes_horarias,
    listar_bonificacoes_produtividade,
)
from ....application.financeiro_competencias import (
    detalhar_competencia_financeira,
    fechar_competencia_financeira,
    reabrir_competencia_financeira,
    recalcular_competencia_financeira,
)
from ....application.financeiro_feriados import (
    atualizar_feriado_nacional,
    criar_feriado_nacional,
    listar_feriados_nacionais,
)
from ....application.financeiro_horas_totais_voadas import (
    consolidar_horas_totais_voadas,
    exportar_horas_totais_voadas_pdf,
)
from ....application.financeiro_produtividade_relatorio_geral import (
    consolidar_relatorio_geral_produtividade,
    exportar_relatorio_geral_produtividade_pdf,
)
from ....application.financeiro_lancamentos_jornada import (
    atualizar_linha_jornada,
    consolidar_produtividade_jornada,
    criar_linha_jornada,
    exportar_extrato_periodo_pdf,
    exportar_grade_jornada_pdf,
    gerar_extrato_periodo_jornada,
    listar_grade_jornada,
    preview_linha_jornada,
    recalcular_grade_jornada,
    recalcular_linha_jornada,
)
from ....application.financeiro_missoes import (
    atualizar_missao_operacional,
    cancelar_missao_operacional,
    criar_missao_operacional,
    detalhar_missao_operacional,
    excluir_missao_operacional,
    listar_missoes_operacionais,
    preview_missao_operacional,
    recalcular_missao_operacional,
)
from ....application.financeiro_observabilidade import (
    listar_divergencias_financeiras,
    listar_eventos_auditoria_financeira,
)
from ....application.financeiro_parametros import (
    atualizar_parametro_financeiro,
    criar_parametro_financeiro,
    listar_parametros_financeiros,
)
from ....application.financeiro_preflight import (
    preflight_calculo_competencia,
    preflight_calculo_missao,
)
from ....application.financeiro_relatorios import (
    gerar_relatorio_financeiro_competencia_pdf,
    gerar_relatorio_financeiro_individual_pdf,
)
from ....auth import permission_required
from ....blueprints.financeiro import financeiro_bp
from ....core.domain_errors import DomainError, DomainValidationError
from ....core.http_utils import domain_error_payload, error_payload, get_page_arg

_MISSION_PATCH_FIELDS = {
    "competencia",
    "data_missao",
    "cavok_numero_voo",
    "contratante",
    "chamado",
    "aeronave_id",
    "categoria_financeira_aeronave",
    "horario_apresentacao",
    "horario_abandono",
    "trecho",
    "houve_pernoite",
    "quantidade_pernoites",
    "cobertura_base",
    "operacao_especial",
    "status",
    "observacoes",
    "motivo",
    "reason",
}

_COMPETENCIA_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

_PARAMETER_PATCH_FIELDS = {
    "valor",
    "unidade",
    "status",
    "vigencia_inicio",
    "vigencia_fim",
    "funcao",
    "categoria",
    "motivo",
    "reason",
    "tipo",
}

_HOLIDAY_PATCH_FIELDS = {
    "data",
    "nome",
    "tipo",
    "status",
    "localidade",
}

_PDF_EOF_MARKER = b"%%EOF"
_PDF_EOF_SCAN_BYTES = 4096


def _safe_pdf_filename(filename: str | None) -> str:
    value = str(filename or "relatorio.pdf").replace("\r", "").replace("\n", "").replace('"', "").strip()
    return value or "relatorio.pdf"


def _validated_pdf_attachment_bytes(content: bytes, *, document_policy: str) -> bytes:
    data = bytes(content or b"")
    if not data:
        raise DomainError("PDF gerado vazio.", status=500, code=f"{document_policy}_empty")
    if not data.startswith(b"%PDF"):
        raise DomainError("PDF gerado sem assinatura valida.", status=500, code=f"{document_policy}_invalid_signature")
    if _PDF_EOF_MARKER not in data[-_PDF_EOF_SCAN_BYTES:]:
        raise DomainError("PDF gerado incompleto.", status=500, code=f"{document_policy}_incomplete")
    return data


def _pdf_attachment_response(
    *,
    content: bytes,
    filename: str,
    mimetype: str = "application/pdf",
    document_policy: str,
) -> Response:
    data = _validated_pdf_attachment_bytes(content, document_policy=document_policy)
    safe_filename = _safe_pdf_filename(filename)
    response = Response(data, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    response.headers["Content-Length"] = str(len(data))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Document-Policy"] = document_policy
    return response


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}
    return payload


def _actor_user_id() -> int:
    return int(getattr(current_user, "id", 0) or 0)


def _page_size_arg() -> int:
    raw = request.args.get("page_size", "100").strip()
    try:
        page_size = int(raw)
    except ValueError:
        return 100
    return max(1, min(page_size, 100))


def _optional_int_arg(name: str):
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _bool_arg(name: str, *, default: bool = False) -> bool:
    raw = request.args.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "sim", "yes", "on"}


def _validate_competencia_or_raise(competencia: str) -> str:
    value = str(competencia or "").strip()
    if not _COMPETENCIA_RE.match(value):
        raise DomainValidationError(
            "Competencia invalida. Use o formato YYYY-MM.",
            code="finance_invalid_competence",
            details={
                "field": "competencia",
                "value": value or None,
                "expected_format": "YYYY-MM",
            },
        )
    return value


def _validate_patch_payload_or_raise(payload: dict, *, allowed_fields: set[str], code: str, entity_label: str) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise DomainValidationError(
            f"Payload de atualizacao de {entity_label} vazio ou invalido.",
            code=code,
            details={
                "allowed_fields": sorted(allowed_fields),
                "invalid_fields": [],
            },
        )

    invalid_fields = sorted(key for key in payload if key not in allowed_fields)
    if invalid_fields:
        raise DomainValidationError(
            f"Payload de atualizacao de {entity_label} contem campos nao permitidos.",
            code=code,
            details={
                "allowed_fields": sorted(allowed_fields),
                "invalid_fields": invalid_fields,
            },
        )

    return payload


def _success_payload(*, status: int, code: str, message: str, **payload):
    response = {
        "success": True,
        "status": status,
        "code": code,
        "message": message,
        "request_id": getattr(g, "request_id", None),
        "correlation_id": getattr(g, "correlation_id", None),
    }
    response.update(payload)
    return response, status


@financeiro_bp.route("/api/v1/financeiro/missoes", methods=["GET"])
@permission_required("finance:missions:read")
def api_finance_missions_list():
    competencia = request.args.get("competencia", "").strip()
    if not competencia:
        return error_payload(
            "Competencia e obrigatoria para listar missoes operacionais.",
            status=400,
            code="finance_missions_competencia_required",
        )
    page = get_page_arg()
    page_size = _page_size_arg()
    status_filter = request.args.get("status", "").strip() or None
    result = listar_missoes_operacionais(
        competencia=competencia,
        status=status_filter,
        page=page,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return _success_payload(
        status=200,
        code="finance_missions_list_ok",
        message="Missoes operacionais listadas com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={"competencia": competencia, "status": status_filter},
    )


@financeiro_bp.route("/api/v1/financeiro/missoes", methods=["POST"])
@permission_required("finance:missions:create")
def api_finance_missions_create():
    try:
        mission = criar_missao_operacional(_json_payload(), actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=201,
        code="finance_mission_created",
        message="Missao operacional criada com sucesso.",
        mission=mission,
        participants=mission.get("participantes", []),
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/preview", methods=["POST"])
@permission_required("finance:missions:read")
def api_finance_mission_preview():
    try:
        preview = preview_missao_operacional(_json_payload())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_mission_preview_ok",
        message="Previa financeira gerada sem persistencia.",
        preview=preview,
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/<int:mission_id>", methods=["GET"])
@permission_required("finance:missions:read")
def api_finance_mission_detail(mission_id: int):
    try:
        mission = detalhar_missao_operacional(mission_id)
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_mission_detail_ok",
        message="Missao operacional encontrada.",
        mission=mission,
        participants=mission.get("participantes", []),
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/<int:mission_id>", methods=["PATCH"])
@permission_required("finance:missions:update")
def api_finance_mission_update(mission_id: int):
    payload = {key: value for key, value in _json_payload().items() if key in _MISSION_PATCH_FIELDS}
    try:
        mission = atualizar_missao_operacional(mission_id, payload, actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_mission_updated",
        message="Missao operacional atualizada com sucesso.",
        mission=mission,
        participants=mission.get("participantes", []),
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/<int:mission_id>/recalcular", methods=["POST"])
@permission_required("finance:missions:recalculate")
def api_finance_mission_recalculate(mission_id: int):
    try:
        result = recalcular_missao_operacional(mission_id, actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_mission_recalculated",
        message="Missao operacional recalculada com sucesso.",
        mission=result["mission"],
        calculations=result["calculations"],
        mission_id=result["mission_id"],
        competence=result["competence"],
        calculation_status=result["calculation_status"],
        recalculated_at=result["recalculated_at"],
        affected_calculations=result["affected_calculations"],
        warnings=result["warnings"],
        errors=result["errors"],
        current_result=result["current_result"],
        audit_event_id=result.get("audit_event_id"),
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/<int:mission_id>/preflight-calculo", methods=["GET"])
@permission_required("finance:missions:read")
def api_finance_mission_preflight_calculo(mission_id: int):
    result = preflight_calculo_missao(mission_id)
    if result["calculavel"]:
        message = "Preflight de missao concluido: missao apta para recalculo."
    else:
        message = "Preflight de missao concluido: bloqueios operacionais encontrados."
    return _success_payload(
        status=200,
        code="finance_mission_preflight_ok",
        message=message,
        data=result,
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/<int:mission_id>/cancelar", methods=["POST"])
@permission_required("finance:missions:cancel")
def api_finance_mission_cancel(mission_id: int):
    payload = _json_payload()
    try:
        result = cancelar_missao_operacional(
            mission_id,
            actor_user_id=_actor_user_id(),
            motivo=payload.get("motivo") or payload.get("reason"),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_mission_cancelled",
        message="Missao operacional cancelada com sucesso.",
        **result,
    )


@financeiro_bp.route("/api/v1/financeiro/missoes/<int:mission_id>", methods=["DELETE"])
@permission_required("finance:missions:delete")
def api_finance_mission_delete(mission_id: int):
    payload = _json_payload()
    try:
        result = excluir_missao_operacional(
            mission_id,
            actor_user_id=_actor_user_id(),
            motivo=payload.get("motivo") or payload.get("reason"),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_mission_deleted",
        message="Missao operacional excluida com sucesso.",
        **result,
    )


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_journey_grid_list():
    try:
        validated_competencia = _validate_competencia_or_raise(request.args.get("competencia", "").strip())
        page = get_page_arg()
        page_size = _page_size_arg()
        result = listar_grade_jornada(
            competencia=validated_competencia,
            funcao=request.args.get("funcao", "").strip() or None,
            tripulante_id=_optional_int_arg("tripulante_id"),
            status=request.args.get("status", "").strip() or None,
            page=page,
            limit=page_size,
            offset=(page - 1) * page_size,
            actor_user_id=_actor_user_id(),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_journey_grid_ok",
        message="Grade mensal de lancamentos de jornada carregada com sucesso.",
        contexto=result["contexto"],
        indicadores=result["indicadores"],
        linhas=result["linhas"],
        produtividade=result["produtividade"],
        permissoes=result["permissoes"],
        status_competencia=result["status_competencia"],
        pagination=result["pagination"],
        filters=result["filters"],
    )


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada", methods=["POST"])
@permission_required("finance:missions:create")
def api_finance_journey_line_create():
    try:
        result = criar_linha_jornada(_json_payload(), actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=201,
        code="finance_journey_line_created",
        message="Linha de jornada criada com sucesso.",
        linha=result["linha"],
        mission=result["mission"],
        recalculation=result.get("recalculation"),
    )


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada/preview", methods=["POST"])
@permission_required("finance:bonuses:read")
def api_finance_journey_line_preview():
    try:
        preview = preview_linha_jornada(_json_payload())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_journey_preview_ok",
        message="Preview da linha de jornada gerado sem persistencia.",
        preview=preview,
    )


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada/recalcular-grade", methods=["POST"])
@permission_required("finance:periods:recalculate")
def api_finance_journey_grid_recalculate():
    try:
        result = recalcular_grade_jornada(_json_payload(), actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_journey_grid_recalculated",
        message="Grade de jornada recalculada com sucesso.",
        contexto=result["contexto"],
        indicadores=result["indicadores"],
        linhas=result["linhas"],
        produtividade=result["produtividade"],
        permissoes=result["permissoes"],
        status_competencia=result["status_competencia"],
        recalculation=result["recalculation"],
        filters=result["filters"],
    )


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada.pdf", methods=["GET"])
@permission_required("finance:exports:create")
def api_finance_journey_grid_pdf():
    try:
        validated_competencia = _validate_competencia_or_raise(request.args.get("competencia", "").strip())
        report = exportar_grade_jornada_pdf(
            competencia=validated_competencia,
            funcao=request.args.get("funcao", "").strip() or None,
            tripulante_id=_optional_int_arg("tripulante_id"),
            status=request.args.get("status", "").strip() or None,
            actor_user_id=_actor_user_id(),
            request_id=getattr(g, "request_id", None) or "",
            correlation_id=getattr(g, "correlation_id", None) or "",
            source_endpoint=request.path,
        )
        return _pdf_attachment_response(
            content=report["content"],
            filename=report["filename"],
            mimetype=report["mimetype"],
            document_policy="finance_journey_grid_pdf",
        )
    except DomainError as exc:
        return domain_error_payload(exc)


@financeiro_bp.route("/api/v1/financeiro/horas-totais-voadas", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_total_flight_hours():
    try:
        result = consolidar_horas_totais_voadas(
            competencia=request.args.get("competencia", "").strip(),
            funcao=request.args.get("funcao", "").strip(),
            org_id=request.args.get("org_id", "").strip() or None,
            incluir_zerados=_bool_arg("incluir_zerados", default=True),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_total_flight_hours_ok",
        message="Relatorio de horas totais voadas consolidado com sucesso.",
        contexto=result["contexto"],
        linhas=result["linhas"],
        totais=result["totais"],
        filters=result["filters"],
    )


@financeiro_bp.route("/api/v1/financeiro/horas-totais-voadas.pdf", methods=["GET"])
@permission_required("finance:exports:create")
def api_finance_total_flight_hours_pdf():
    try:
        result = exportar_horas_totais_voadas_pdf(
            competencia=request.args.get("competencia", "").strip(),
            funcao=request.args.get("funcao", "").strip(),
            org_id=request.args.get("org_id", "").strip() or None,
            incluir_zerados=_bool_arg("incluir_zerados", default=True),
            actor_user_id=_actor_user_id(),
            request_id=getattr(g, "request_id", "") or "",
            correlation_id=getattr(g, "correlation_id", "") or "",
            source_endpoint=request.path,
        )
        return _pdf_attachment_response(
            content=result["content"],
            filename=result["filename"],
            mimetype=result["mimetype"],
            document_policy="finance_total_flight_hours_pdf",
        )
    except DomainError as exc:
        return domain_error_payload(exc)


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada/<int:linha_id>", methods=["PATCH"])
@permission_required("finance:missions:update")
def api_finance_journey_line_update(linha_id: int):
    try:
        result = atualizar_linha_jornada(linha_id, _json_payload(), actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_journey_line_updated",
        message="Linha de jornada atualizada com sucesso.",
        linha=result["linha"],
        mission=result["mission"],
        recalculation=result.get("recalculation"),
    )


@financeiro_bp.route("/api/v1/financeiro/lancamentos-jornada/<int:linha_id>/recalcular", methods=["POST"])
@permission_required("finance:missions:recalculate")
def api_finance_journey_line_recalculate(linha_id: int):
    try:
        result = recalcular_linha_jornada(linha_id, actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_journey_line_recalculated",
        message="Linha de jornada recalculada com sucesso.",
        linha=result["linha"],
        recalculation=result["recalculation"],
    )


@financeiro_bp.route("/api/v1/financeiro/bonificacoes/horaria", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_hourly_bonuses_list():
    page = get_page_arg()
    page_size = _page_size_arg()
    result = listar_bonificacoes_horarias(
        competencia=request.args.get("competencia", "").strip() or None,
        missao_operacional_id=_optional_int_arg("missao_operacional_id"),
        tripulante_id=_optional_int_arg("tripulante_id"),
        funcao=request.args.get("funcao", "").strip() or None,
        status=request.args.get("status", "").strip() or None,
        page=page,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return _success_payload(
        status=200,
        code="finance_hourly_bonuses_list_ok",
        message="Bonificacoes horarias listadas com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={
            "competencia": request.args.get("competencia", "").strip() or None,
            "missao_operacional_id": _optional_int_arg("missao_operacional_id"),
            "tripulante_id": _optional_int_arg("tripulante_id"),
            "funcao": request.args.get("funcao", "").strip() or None,
            "status": request.args.get("status", "").strip() or None,
        },
    )


@financeiro_bp.route("/api/v1/financeiro/bonificacoes/horaria/<int:calculation_id>", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_hourly_bonus_detail(calculation_id: int):
    try:
        calculation = detalhar_bonificacao_horaria(calculation_id)
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_hourly_bonus_detail_ok",
        message="Bonificacao horaria encontrada.",
        calculation=calculation,
    )


@financeiro_bp.route("/api/v1/financeiro/bonificacoes/produtividade", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_productivity_bonuses_list():
    page = get_page_arg()
    page_size = _page_size_arg()
    result = listar_bonificacoes_produtividade(
        competencia=request.args.get("competencia", "").strip() or None,
        tripulante_id=_optional_int_arg("tripulante_id"),
        funcao=request.args.get("funcao", "").strip() or None,
        status=request.args.get("status", "").strip() or None,
        page=page,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return _success_payload(
        status=200,
        code="finance_productivity_bonuses_list_ok",
        message="Bonificacoes por funcao/produtividade listadas com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={
            "competencia": request.args.get("competencia", "").strip() or None,
            "tripulante_id": _optional_int_arg("tripulante_id"),
            "funcao": request.args.get("funcao", "").strip() or None,
            "status": request.args.get("status", "").strip() or None,
        },
    )


@financeiro_bp.route("/api/v1/financeiro/produtividade/consolidado", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_productivity_consolidated():
    try:
        competencia = _validate_competencia_or_raise(request.args.get("competencia", "").strip())
        result = consolidar_produtividade_jornada(
            competencia=competencia,
            funcao=request.args.get("funcao", "").strip() or None,
            tripulante_id=_optional_int_arg("tripulante_id"),
            actor_user_id=_actor_user_id(),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_productivity_consolidated_ok",
        message="Consolidado de produtividade carregado com sucesso.",
        contexto=result["contexto"],
        indicadores=result["indicadores"],
        linhas_por_tripulante=result["linhas_por_tripulante"],
        totais_por_funcao=result["totais_por_funcao"],
        alertas=result["alertas"],
        bloqueios=result["bloqueios"],
        condicoes_especiais=result["condicoes_especiais"],
        filters=result["filters"],
    )


@financeiro_bp.route("/api/v1/financeiro/produtividade/relatorio-geral", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_productivity_general_report():
    try:
        result = consolidar_relatorio_geral_produtividade(
            competencia=request.args.get("competencia", "").strip(),
            funcao=request.args.get("funcao", "").strip(),
            org_id=request.args.get("org_id", "").strip() or None,
            incluir_zerados=_bool_arg("incluir_zerados", default=True),
            categoria=request.args.get("categoria", "").strip() or None,
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_productivity_general_report_ok",
        message="Relatorio geral de produtividade consolidado com sucesso.",
        competencia=result["competencia"],
        funcao=result["funcao"],
        titulo=result["titulo"],
        totais=result["totais"],
        items=result["items"],
        pendencias=result["pendencias"],
        contexto=result["contexto"],
        filters=result["filters"],
    )


@financeiro_bp.route("/api/v1/financeiro/produtividade/relatorio-geral.pdf", methods=["GET"])
@permission_required("finance:exports:create")
def api_finance_productivity_general_report_pdf():
    try:
        result = exportar_relatorio_geral_produtividade_pdf(
            competencia=request.args.get("competencia", "").strip(),
            funcao=request.args.get("funcao", "").strip(),
            org_id=request.args.get("org_id", "").strip() or None,
            incluir_zerados=_bool_arg("incluir_zerados", default=True),
            categoria=request.args.get("categoria", "").strip() or None,
            actor_user_id=_actor_user_id(),
            request_id=getattr(g, "request_id", "") or "",
            correlation_id=getattr(g, "correlation_id", "") or "",
            source_endpoint=request.path,
        )
        return _pdf_attachment_response(
            content=result["content"],
            filename=result["filename"],
            mimetype=result["mimetype"],
            document_policy="finance_productivity_general_report_pdf",
        )
    except DomainError as exc:
        return domain_error_payload(exc)


@financeiro_bp.route("/api/v1/financeiro/extrato-periodo", methods=["GET"])
@permission_required("finance:bonuses:read")
def api_finance_period_extract():
    try:
        result = gerar_extrato_periodo_jornada(
            data_inicio=request.args.get("data_inicio", "").strip(),
            data_fim=request.args.get("data_fim", "").strip(),
            tripulante_id=_optional_int_arg("tripulante_id"),
            funcao=request.args.get("funcao", "").strip() or None,
            tipo=request.args.get("tipo", "").strip() or None,
            actor_user_id=_actor_user_id(),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_period_extract_ok",
        message="Extrato por periodo carregado com sucesso.",
        contexto=result["contexto"],
        linhas=result["linhas"],
        subtotais=result["subtotais"],
        total_geral=result["total_geral"],
        alertas=result["alertas"],
        filters=result["filters"],
    )


@financeiro_bp.route("/api/v1/financeiro/extrato-periodo.pdf", methods=["GET"])
@permission_required("finance:exports:create")
def api_finance_period_extract_pdf():
    try:
        result = exportar_extrato_periodo_pdf(
            data_inicio=request.args.get("data_inicio", "").strip(),
            data_fim=request.args.get("data_fim", "").strip(),
            tripulante_id=_optional_int_arg("tripulante_id"),
            funcao=request.args.get("funcao", "").strip() or None,
            tipo=request.args.get("tipo", "").strip() or None,
            actor_user_id=_actor_user_id(),
            request_id=getattr(g, "request_id", "") or "",
            correlation_id=getattr(g, "correlation_id", "") or "",
        )
        return _pdf_attachment_response(
            content=result["content"],
            filename=result["filename"],
            mimetype=result["mimetype"],
            document_policy="finance_period_extract_pdf",
        )
    except DomainError as exc:
        return domain_error_payload(exc)


@financeiro_bp.route(
    "/api/v1/financeiro/bonificacoes/produtividade/<int:tripulante_id>",
    methods=["GET"],
)
@permission_required("finance:bonuses:read")
def api_finance_productivity_bonus_by_tripulante(tripulante_id: int):
    try:
        calculation = detalhar_bonificacao_produtividade_por_tripulante(
            tripulante_id,
            competencia=request.args.get("competencia", "").strip() or None,
            funcao=request.args.get("funcao", "").strip() or None,
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_productivity_bonus_detail_ok",
        message="Bonificacao por funcao/produtividade encontrada.",
        calculation=calculation,
    )


@financeiro_bp.route("/api/v1/financeiro/relatorios/individual.pdf", methods=["GET"])
@permission_required("finance:exports:create")
def api_finance_individual_report_pdf():
    tipo = request.args.get("tipo", "").strip().lower()
    if tipo not in {"horaria", "produtividade"}:
        return error_payload(
            "Tipo de relatorio individual invalido.",
            status=400,
            code="finance_individual_report_invalid_type",
        )
    formato = request.args.get("formato", "pdf").strip().lower() or "pdf"
    if formato != "pdf":
        return error_payload(
            "Formato invalido para relatorio individual.",
            status=400,
            code="finance_individual_report_invalid_format",
        )
    raw_tripulante_id = request.args.get("tripulante_id", "").strip()
    try:
        tripulante_id = int(raw_tripulante_id)
    except ValueError:
        tripulante_id = 0
    if tripulante_id <= 0:
        return error_payload(
            "tripulante_id e obrigatorio.",
            status=400,
            code="finance_individual_report_tripulante_required",
        )
    funcao = request.args.get("funcao", "").strip() or None
    if funcao and funcao not in {"comandante", "copiloto"}:
        return error_payload(
            "Funcao operacional invalida.",
            status=400,
            code="finance_individual_report_invalid_funcao",
        )
    status_filter = request.args.get("status", "").strip() or None
    if status_filter and status_filter not in {"calculado", "recalculo_pendente", "obsoleto"}:
        return error_payload(
            "Status de calculo invalido.",
            status=400,
            code="finance_individual_report_invalid_status",
        )
    try:
        validated_competencia = _validate_competencia_or_raise(request.args.get("competencia", "").strip())
        report = gerar_relatorio_financeiro_individual_pdf(
            tipo=tipo,
            competencia=validated_competencia,
            tripulante_id=tripulante_id,
            funcao=funcao,
            status=status_filter,
            incluir_obsoletos=_bool_arg("incluir_obsoletos", default=False),
            actor_user_id=_actor_user_id(),
            request_id=getattr(g, "request_id", None) or "",
            correlation_id=getattr(g, "correlation_id", None) or "",
            source_endpoint=request.path,
        )
        return _pdf_attachment_response(
            content=report["content"],
            filename=report["filename"],
            mimetype=report["mimetype"],
            document_policy="finance_individual_report_pdf",
        )
    except DomainError as exc:
        return domain_error_payload(exc)


@financeiro_bp.route("/api/v1/financeiro/competencias/<string:competencia>", methods=["GET"])
@permission_required("finance:periods:read")
def api_finance_period_detail(competencia: str):
    try:
        validated_competencia = _validate_competencia_or_raise(competencia)
        result = detalhar_competencia_financeira(validated_competencia)
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_period_detail_ok",
        message="Competencia financeira encontrada.",
        period=result["period"],
        totals=result["totals"],
        snapshot=result["snapshot"],
        divergences=result["divergences"],
    )


@financeiro_bp.route("/api/v1/financeiro/competencias/<string:competencia>/preflight-calculo", methods=["GET"])
@permission_required("finance:periods:read")
def api_finance_period_preflight_calculo(competencia: str):
    try:
        validated_competencia = _validate_competencia_or_raise(competencia)
        result = preflight_calculo_competencia(validated_competencia)
    except DomainError as exc:
        return domain_error_payload(exc)
    if result["calculavel"] and result["fechavel"]:
        message = "Preflight de competencia concluido: recalculo e fechamento aptos."
    elif result["calculavel"]:
        message = "Preflight de competencia concluido: recalculo apto, fechamento bloqueado."
    else:
        message = "Preflight de competencia concluido: bloqueios operacionais encontrados."
    return _success_payload(
        status=200,
        code="finance_period_preflight_ok",
        message=message,
        data=result,
    )


@financeiro_bp.route("/api/v1/financeiro/competencias/<string:competencia>/relatorio.pdf", methods=["GET"])
@permission_required("finance:exports:create")
def api_finance_period_report_pdf(competencia: str):
    try:
        validated_competencia = _validate_competencia_or_raise(competencia)
        report = gerar_relatorio_financeiro_competencia_pdf(
            validated_competencia,
            actor_user_id=_actor_user_id(),
            request_id=getattr(g, "request_id", None) or "",
            correlation_id=getattr(g, "correlation_id", None) or "",
            source_endpoint=request.path,
        )
        return _pdf_attachment_response(
            content=report["content"],
            filename=report["filename"],
            mimetype=report["mimetype"],
            document_policy="finance_period_report_pdf",
        )
    except DomainError as exc:
        return domain_error_payload(exc)


@financeiro_bp.route("/api/v1/financeiro/competencias/<string:competencia>/recalcular", methods=["POST"])
@permission_required("finance:periods:recalculate")
def api_finance_period_recalculate(competencia: str):
    try:
        validated_competencia = _validate_competencia_or_raise(competencia)
        result = recalcular_competencia_financeira(
            validated_competencia,
            actor_user_id=_actor_user_id(),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_period_recalculated",
        message="Competencia recalculada com bonificacao por funcao/produtividade.",
        period=result["period"],
        items=result["items"],
        totals=result["totals"],
        divergences=result["divergences"],
        calculation_memory=result["calculation_memory"],
    )


@financeiro_bp.route("/api/v1/financeiro/competencias/<string:competencia>/fechar", methods=["POST"])
@permission_required("finance:periods:close")
def api_finance_period_close(competencia: str):
    try:
        validated_competencia = _validate_competencia_or_raise(competencia)
        result = fechar_competencia_financeira(
            validated_competencia,
            _json_payload(),
            actor_user_id=_actor_user_id(),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_period_closed",
        message="Competencia financeira fechada com sucesso.",
        period=result["period"],
        snapshot=result["snapshot"],
        totals=result["totals"],
    )


@financeiro_bp.route("/api/v1/financeiro/competencias/<string:competencia>/reabrir", methods=["POST"])
@permission_required("finance:periods:reopen")
def api_finance_period_reopen(competencia: str):
    try:
        validated_competencia = _validate_competencia_or_raise(competencia)
        result = reabrir_competencia_financeira(
            validated_competencia,
            _json_payload(),
            actor_user_id=_actor_user_id(),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_period_reopened",
        message="Competencia financeira reaberta com sucesso.",
        period=result["period"],
    )


@financeiro_bp.route("/api/v1/financeiro/parametros", methods=["GET"])
@permission_required("finance:parameters:read")
def api_finance_parameters_list():
    page = get_page_arg()
    page_size = _page_size_arg()
    try:
        result = listar_parametros_financeiros(
            tipo=request.args.get("tipo", "").strip() or None,
            status=request.args.get("status", "").strip() or None,
            funcao=request.args.get("funcao", None),
            categoria=request.args.get("categoria", None),
            unidade=request.args.get("unidade", "").strip() or None,
            vigencia_em=request.args.get("vigencia_em", "").strip() or None,
            page=page,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_parameters_list_ok",
        message="Parametros financeiros listados com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={
            "tipo": request.args.get("tipo", "").strip() or None,
            "status": request.args.get("status", "").strip() or None,
            "funcao": request.args.get("funcao", None),
            "categoria": request.args.get("categoria", None),
            "unidade": request.args.get("unidade", "").strip() or None,
            "vigencia_em": request.args.get("vigencia_em", "").strip() or None,
        },
    )


@financeiro_bp.route("/api/v1/financeiro/parametros", methods=["POST"])
@permission_required("finance:parameters:create")
def api_finance_parameters_create():
    try:
        parameter = criar_parametro_financeiro(_json_payload(), actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=201,
        code="finance_parameter_created",
        message="Parametro financeiro criado com sucesso.",
        parameter=parameter,
    )


@financeiro_bp.route("/api/v1/financeiro/parametros/<int:parameter_id>", methods=["PATCH"])
@permission_required("finance:parameters:update")
def api_finance_parameters_update(parameter_id: int):
    try:
        payload = _validate_patch_payload_or_raise(
            _json_payload(),
            allowed_fields=_PARAMETER_PATCH_FIELDS,
            code="finance_parameter_patch_empty_or_invalid",
            entity_label="parametro",
        )
        parameter = atualizar_parametro_financeiro(parameter_id, payload, actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_parameter_updated",
        message="Parametro financeiro atualizado com sucesso.",
        parameter=parameter,
    )


@financeiro_bp.route("/api/v1/financeiro/feriados", methods=["GET"])
@permission_required("finance:parameters:read")
def api_finance_holidays_list():
    page = get_page_arg()
    page_size = _page_size_arg()
    ano_raw = request.args.get("ano", "").strip()
    try:
        ano = int(ano_raw) if ano_raw else None
    except ValueError:
        return error_payload("Ano invalido.", status=400, code="finance_holidays_invalid_year")
    try:
        result = listar_feriados_nacionais(
            status=request.args.get("status", "").strip() or None,
            ano=ano,
            data_inicio=request.args.get("data_inicio", "").strip() or None,
            data_fim=request.args.get("data_fim", "").strip() or None,
            page=page,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_holidays_list_ok",
        message="Feriados nacionais listados com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={
            "tipo": "nacional",
            "status": request.args.get("status", "").strip() or None,
            "ano": ano,
            "data_inicio": request.args.get("data_inicio", "").strip() or None,
            "data_fim": request.args.get("data_fim", "").strip() or None,
        },
    )


@financeiro_bp.route("/api/v1/financeiro/feriados", methods=["POST"])
@permission_required("finance:parameters:create")
def api_finance_holidays_create():
    try:
        holiday = criar_feriado_nacional(_json_payload(), actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=201,
        code="finance_holiday_created",
        message="Feriado nacional criado com sucesso.",
        holiday=holiday,
    )


@financeiro_bp.route("/api/v1/financeiro/feriados/<int:holiday_id>", methods=["PATCH"])
@permission_required("finance:parameters:update")
def api_finance_holidays_update(holiday_id: int):
    try:
        payload = _validate_patch_payload_or_raise(
            _json_payload(),
            allowed_fields=_HOLIDAY_PATCH_FIELDS,
            code="finance_holiday_patch_empty_or_invalid",
            entity_label="feriado",
        )
        holiday = atualizar_feriado_nacional(holiday_id, payload, actor_user_id=_actor_user_id())
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_holiday_updated",
        message="Feriado nacional atualizado com sucesso.",
        holiday=holiday,
    )


@financeiro_bp.route("/api/v1/financeiro/auditoria", methods=["GET"])
@permission_required("finance:audit:read")
def api_finance_audit_list():
    try:
        result = listar_eventos_auditoria_financeira(
            competencia=request.args.get("competencia", "").strip() or None,
            entity_type=request.args.get("entity_type", "").strip() or None,
            entity_id=request.args.get("entity_id", "").strip() or None,
            event_name=request.args.get("event_name", "").strip() or None,
            limit=request.args.get("limit", "").strip() or None,
            offset=request.args.get("offset", "").strip() or None,
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_audit_list_ok",
        message="Eventos de auditoria financeira listados com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={
            "competencia": request.args.get("competencia", "").strip() or None,
            "entity_type": request.args.get("entity_type", "").strip() or None,
            "entity_id": _optional_int_arg("entity_id"),
            "event_name": request.args.get("event_name", "").strip() or None,
        },
    )


@financeiro_bp.route("/api/v1/financeiro/divergencias", methods=["GET"])
@permission_required("finance:divergences:read")
def api_finance_divergences_list():
    try:
        result = listar_divergencias_financeiras(
            competencia=request.args.get("competencia", "").strip() or None,
            status=request.args.get("status", "").strip() or None,
            severidade=request.args.get("severidade", "").strip() or None,
            codigo=request.args.get("codigo", "").strip() or None,
            limit=request.args.get("limit", "").strip() or None,
            offset=request.args.get("offset", "").strip() or None,
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return _success_payload(
        status=200,
        code="finance_divergences_list_ok",
        message="Divergencias financeiras listadas com sucesso.",
        items=result["items"],
        pagination=result["pagination"],
        filters={
            "competencia": request.args.get("competencia", "").strip() or None,
            "status": request.args.get("status", "").strip() or None,
            "severidade": request.args.get("severidade", "").strip() or None,
            "codigo": request.args.get("codigo", "").strip() or None,
        },
    )
