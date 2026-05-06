from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.core.http_contract import PROGRAMMATIC_JSON_ENDPOINTS

KNOWN_PROGRAMMATIC_RULES = {
    "/jobs/<int:job_id>/status",
    "/jobs/<int:job_id>/reativar",
    "/painel-tv/dados",
    "/produtividade/painel-tv/dados",
    "/bases/api/dados",
    "/bases/pilotos/adicionar",
    "/bases/pilotos/<int:pilot_id>/status",
    "/bases/pilotos/<int:pilot_id>/mover",
    "/bases/pilotos/<int:pilot_id>/historico",
}


def _rule_to_endpoint_map(app):
    mapping = {}
    for rule in app.url_map.iter_rules():
        mapping[rule.rule] = rule.endpoint
    return mapping


def test_programmatic_catalog_endpoints_exist_in_url_map():
    app = create_app()
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    missing = sorted(endpoint for endpoint in PROGRAMMATIC_JSON_ENDPOINTS if endpoint not in endpoints)
    assert not missing, f"Endpoints programáticos catalogados não encontrados no app.url_map: {missing}"


def test_known_programmatic_rules_are_cataloged():
    app = create_app()
    rules = _rule_to_endpoint_map(app)
    missing_rules = sorted(rule for rule in KNOWN_PROGRAMMATIC_RULES if rule not in rules)
    assert not missing_rules, f"Rotas programáticas conhecidas ausentes no app.url_map: {missing_rules}"

    uncataloged = sorted(rule for rule in KNOWN_PROGRAMMATIC_RULES if rules[rule] not in PROGRAMMATIC_JSON_ENDPOINTS)
    assert not uncataloged, (
        "Rotas programáticas conhecidas sem catálogo JSON explícito: "
        f"{[(rule, rules[rule]) for rule in uncataloged]}"
    )


def test_declarative_programmatic_routes_match_manual_catalog():
    app = create_app()
    declarative = {
        endpoint
        for endpoint, view_func in app.view_functions.items()
        if bool(getattr(view_func, "_programmatic_json_contract", False))
    }
    assert declarative == PROGRAMMATIC_JSON_ENDPOINTS, (
        "Catálogo manual e marcação declarativa divergiram. "
        f"declarative_only={sorted(declarative - PROGRAMMATIC_JSON_ENDPOINTS)} "
        f"catalog_only={sorted(PROGRAMMATIC_JSON_ENDPOINTS - declarative)}"
    )

