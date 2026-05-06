from __future__ import annotations

from typing import Callable

# Catálogo central de endpoints consumidos programaticamente (JSON),
# mesmo fora de /api/.
PROGRAMMATIC_JSON_ENDPOINTS: set[str] = {
    "admin.jobs_status",
    "admin.jobs_requeue",
    "dashboard.painel_tv_dados",
    "relatorios.produtividade_painel_tv_dados",
    "bases.api_dados",
    "bases.adicionar_piloto",
    "bases.alterar_status",
    "bases.mover_piloto",
    "bases.historico_piloto",
}

# Prefixos com contrato JSON obrigatório por convenção de URL.
PROGRAMMATIC_JSON_PATH_PREFIXES: tuple[str, ...] = ("/api/", "/bases/api/")


def programmatic_json(view_func: Callable) -> Callable:
    """
    Marca explicitamente uma view como endpoint programático JSON.
    """
    setattr(view_func, "_programmatic_json_contract", True)
    return view_func


def is_programmatic_json_endpoint(endpoint: str | None, view_func: Callable | None = None) -> bool:
    if endpoint and endpoint in PROGRAMMATIC_JSON_ENDPOINTS:
        return True
    if view_func is not None and bool(getattr(view_func, "_programmatic_json_contract", False)):
        return True
    return False

