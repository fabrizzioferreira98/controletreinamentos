from __future__ import annotations


OPERACOES_API_ROUTE_PREFIX = "/api/v1/operacoes"


OPERACOES_SSR_CURRENT_ENDPOINTS = (
    {
        "domain": "pernoites",
        "route": "/pernoites",
        "methods": ("GET",),
        "endpoint": "operacoes.pernoites_list",
        "handler": "pernoites_list",
        "classification": "ssr_canonical_current_direct",
        "reason": "UI operacional atual de Pernoites; leitura API existe para cutover controlado, mas a tela viva permanece SSR neste ciclo.",
    },
    {
        "domain": "pernoites",
        "route": "/pernoites/novo",
        "methods": ("GET", "POST"),
        "endpoint": "operacoes.pernoites_new",
        "handler": "pernoites_new",
        "classification": "ssr_canonical_current_direct",
        "reason": "Formulario HTML atual de criacao; escrita API ainda nao registrada neste ciclo.",
    },
    {
        "domain": "pernoites",
        "route": "/pernoites/<int:pernoite_id>/editar",
        "methods": ("GET", "POST"),
        "endpoint": "operacoes.pernoites_edit",
        "handler": "pernoites_edit",
        "classification": "ssr_canonical_current_direct",
        "reason": "Formulario HTML atual de edicao; escrita API ainda nao registrada neste ciclo.",
    },
    {
        "domain": "pernoites",
        "route": "/pernoites/<int:pernoite_id>/excluir",
        "methods": ("POST",),
        "endpoint": "operacoes.pernoites_delete",
        "handler": "pernoites_delete",
        "classification": "ssr_canonical_current_direct",
        "reason": "Acao HTML atual de exclusao; escrita API ainda nao registrada neste ciclo.",
    },
)


OPERACOES_READ_API_ENDPOINTS = (
    {
        "domain": "pernoites",
        "route": "/api/v1/operacoes/pernoites",
        "methods": ("GET",),
        "endpoint": "operacoes.api_operacoes_pernoites_list",
        "handler": "api_operacoes_pernoites_list",
        "classification": "api_read_canonical_registered",
        "reason": "Primeiro contrato real de migracao: read model canonico para lista de Pernoites, sem migrar escrita/UI neste ciclo.",
    },
    {
        "domain": "pernoites",
        "route": "/api/v1/operacoes/pernoites/<int:pernoite_id>",
        "methods": ("GET",),
        "endpoint": "operacoes.api_operacoes_pernoite_detail",
        "handler": "api_operacoes_pernoite_detail",
        "classification": "api_read_canonical_registered",
        "reason": "Read model canonico de detalhe para preparar SPA futura sem pseudo-API.",
    },
)


OPERACOES_FUTURE_API_CONTRACT = {
    "status": "read_api_registered_write_ssr_canonical_current",
    "canonical_current": "ssr_ui_and_write_current_with_api_read_model",
    "registration_policy": "Read API is registered and canonical for machine reads; write API and SPA cutover require a dedicated follow-up block.",
    "base_path": OPERACOES_API_ROUTE_PREFIX,
    "read_policy": "GET list/detail are registered as real API contracts.",
    "write_policy": "Create/edit/delete remain SSR canonical current; POST/PUT/PATCH/DELETE API routes must stay unregistered until cutover.",
    "error": {
        "shape": {"success": False, "status": "int", "code": "string", "message": "string", "request_id": "string|null"},
        "source": "DomainError",
    },
    "resources": {
        "pernoites": {
            "canonical_paths": (
                "/api/v1/operacoes/pernoites",
                "/api/v1/operacoes/pernoites/<id>",
            ),
            "request": {
                "tripulante_id": "int",
                "data_pernoite": "date_iso",
                "tipo_pernoite": "enum:cobertura_base|operacional_comum",
                "quantidade": "int",
                "observacoes": "string|null",
            },
            "response_item": {
                "id": "int",
                "tripulante_id": "int",
                "tripulante_nome": "string",
                "data_pernoite": "date_iso",
                "tipo_pernoite": "enum:cobertura_base|operacional_comum",
                "quantidade": "int",
                "observacoes": "string|null",
            },
            "success_codes": {
                "list": "operacoes_pernoites_list_ok",
                "detail": "operacoes_pernoite_ok",
                "create": "not_registered_write_ssr_current",
                "update": "not_registered_write_ssr_current",
                "delete": "not_registered_write_ssr_current",
            },
        },
    },
}


def current_ssr_endpoints() -> tuple[dict, ...]:
    return OPERACOES_SSR_CURRENT_ENDPOINTS


def current_read_api_endpoints() -> tuple[dict, ...]:
    return OPERACOES_READ_API_ENDPOINTS


def future_api_paths() -> tuple[str, ...]:
    paths: list[str] = []
    for resource in OPERACOES_FUTURE_API_CONTRACT["resources"].values():
        paths.extend(resource["canonical_paths"])
    return tuple(paths)
