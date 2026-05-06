from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import ENDPOINT_PERMISSION_MAP, PUBLIC_ENDPOINTS


def test_all_non_public_endpoints_have_permission_mapping():
    app = create_app()
    public_endpoints = set(PUBLIC_ENDPOINTS)

    missing = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint in public_endpoints:
            continue
        if rule.rule.startswith("/api/"):
            continue
        if rule.endpoint not in ENDPOINT_PERMISSION_MAP:
            missing.append((rule.endpoint, rule.rule))

    assert missing == []
