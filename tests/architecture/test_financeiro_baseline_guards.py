from __future__ import annotations

import ast
import re
from pathlib import Path

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import ENDPOINT_PERMISSION_MAP
from backend.src.controle_treinamentos.contracts.financeiro import (
    FINANCE_API_ROUTE_PREFIX,
    FINANCE_DIVERGENCE_SEVERITIES,
    FINANCE_MISSION_STATUS,
)
from backend.src.controle_treinamentos.contracts.financeiro_http import FINANCE_HTTP_CONTRACTS, FINANCE_STUB_HTTP_CONTRACTS
from backend.src.controle_treinamentos.db.schema import SCHEMA

ROOT = Path(__file__).resolve().parents[2]
BACKEND_PACKAGE = ROOT / "backend" / "src" / "controle_treinamentos"
FINANCE_CONTRACT = BACKEND_PACKAGE / "contracts" / "financeiro.py"
FINANCE_ROUTES = BACKEND_PACKAGE / "api" / "http" / "financeiro" / "routes.py"
FRONTEND_SRC = ROOT / "frontend" / "src"
ROUTE_REGISTRY = FRONTEND_SRC / "app" / "route-registry.js"
SHELL_NAVIGATION = FRONTEND_SRC / "shell" / "navigation.js"

FORBIDDEN_FINANCE_CONTRACT_IMPORTS = (
    "flask",
    "psycopg2",
    "sqlalchemy",
    "db",
    "repositories",
    "application",
    "frontend",
)

FORBIDDEN_FINANCE_ROUTE_IMPORTS = (
    "psycopg2",
    "sqlalchemy",
    "db",
    "repositories",
    "financeiro_audit_events",
)

FORBIDDEN_FINANCE_STUB_CALLS = (
    "get_db",
    "record_audit_event",
    "audit_event",
)

LEGACY_ROUTE_PREFIXES = (
    "/missoes",
    "/produtividade",
    "/api/v1/missoes",
    "/api/v1/produtividade",
)


def _python_tree(file_path: Path) -> ast.Module:
    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def _module_matches(candidate: str, banned_module: str) -> bool:
    candidate_parts = candidate.split(".")
    banned_parts = banned_module.split(".")
    return any(
        candidate_parts[index : index + len(banned_parts)] == banned_parts
        for index in range(len(candidate_parts) - len(banned_parts) + 1)
    )


def _import_candidates(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        candidates = [module] if module else []
        candidates.extend(f"{module}.{alias.name}" if module else alias.name for alias in node.names)
        return candidates
    return []


def _registered_routes() -> set[str]:
    app = create_app()
    return {rule.rule for rule in app.url_map.iter_rules()}


def _registered_finance_route_contract_keys() -> set[tuple[str, str]]:
    app = create_app()
    keys = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(FINANCE_API_ROUTE_PREFIX):
            continue
        for method in sorted(set(rule.methods) & {"GET", "POST", "PATCH"}):
            keys.add((method, _normalize_registered_finance_path(rule.rule)))
    return keys


def _normalize_registered_finance_path(path: str) -> str:
    normalized = re.sub(r"<string:competencia>", "{competencia}", path)
    normalized = re.sub(r"<int:tripulante_id>", "{tripulante_id}", normalized)
    normalized = re.sub(r"<int:[^>]+>", "{id}", normalized)
    return normalized


def _expected_finance_route_contract_keys() -> set[tuple[str, str]]:
    return {(contract["method"], contract["path"]) for contract in FINANCE_HTTP_CONTRACTS}


def _schema_enum_values(*, table: str, column: str) -> tuple[str, ...]:
    table_pattern = re.compile(
        rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table)}\s*\((.*?)\)\s*;",
        flags=re.DOTALL | re.IGNORECASE,
    )
    table_match = table_pattern.search(SCHEMA)
    if not table_match:
        raise AssertionError(f"Tabela {table} nao encontrada no schema.")
    table_body = table_match.group(1)

    check_pattern = re.compile(
        rf"{re.escape(column)}\s+TEXT\s+NOT NULL(?:\s+DEFAULT\s+'[^']+')?\s+CHECK\s+\(\s*{re.escape(column)}\s+IN\s+\(([^)]+)\)\s*\)",
        flags=re.IGNORECASE,
    )
    check_match = check_pattern.search(table_body)
    if not check_match:
        raise AssertionError(f"Enum CHECK para {table}.{column} nao encontrado no schema.")
    return tuple(re.findall(r"'([^']+)'", check_match.group(1)))


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _call_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def _strip_js_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def _js_hrefs(source: str) -> set[str]:
    return set(re.findall(r'href:\s*"([^"]+)"', _strip_js_comments(source)))


def _js_static_hash_routes(source: str) -> set[str]:
    return set(re.findall(r'"(#[^"]+)":\s*{', _strip_js_comments(source)))


def _js_permissions(source: str) -> set[str]:
    return set(re.findall(r'"([a-zA-Z0-9_]+:[a-zA-Z0-9_:*]+)"', _strip_js_comments(source)))


def test_finance_contract_stays_pure_python_without_framework_or_layer_imports():
    violations = []
    tree = _python_tree(FINANCE_CONTRACT)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        for candidate in _import_candidates(node):
            for banned_module in FORBIDDEN_FINANCE_CONTRACT_IMPORTS:
                if _module_matches(candidate, banned_module):
                    violations.append(
                        f"{FINANCE_CONTRACT}:{node.lineno}: import '{candidate}' violates finance contract "
                        f"baseline; contracts/financeiro.py must stay pure and must not import '{banned_module}'."
                    )

    assert violations == []


def test_registered_finance_api_routes_match_future_http_contract_matrix():
    assert _registered_finance_route_contract_keys() == _expected_finance_route_contract_keys()


def test_registered_finance_endpoints_have_explicit_rbac_mapping():
    app = create_app()
    expected_permissions = {
        (contract["method"], contract["path"]): contract["permission"]
        for contract in FINANCE_HTTP_CONTRACTS
    }
    violations = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(FINANCE_API_ROUTE_PREFIX):
            continue
        normalized_path = _normalize_registered_finance_path(rule.rule)
        for method in sorted(set(rule.methods) & {"GET", "POST", "PATCH"}):
            expected_permission = expected_permissions[(method, normalized_path)]
            mapped_permission = ENDPOINT_PERMISSION_MAP.get(rule.endpoint)
            if mapped_permission != expected_permission:
                violations.append(
                    f"{rule.endpoint} {method} {rule.rule}: expected {expected_permission}, got {mapped_permission}"
                )

    assert violations == []


def test_finance_blueprint_is_registered_only_for_api_surface():
    app = create_app()
    blueprint_names = set(app.blueprints)

    assert "financeiro" in blueprint_names
    assert "finance" not in blueprint_names


def test_finance_frontend_feature_declares_only_authorized_finance_surfaces():
    # Gate de transicao: Financeiro no frontend esta autorizado para as tres subabas do modulo.
    # Novas superficies devem atualizar este contrato em vez de aparecerem por expansao implicita.
    route_registry_source = ROUTE_REGISTRY.read_text(encoding="utf-8")
    navigation_source = SHELL_NAVIGATION.read_text(encoding="utf-8")

    finance_hash_routes = sorted(
        route for route in _js_static_hash_routes(route_registry_source) if route.startswith("#/financeiro")
    )
    finance_nav_hrefs = sorted(href for href in _js_hrefs(navigation_source) if "financeiro" in href.lower())
    finance_permissions = sorted(
        permission
        for permission in _js_permissions(f"{route_registry_source}\n{navigation_source}")
        if permission.startswith("finance:")
    )

    assert finance_hash_routes == [
        "#/financeiro/bonificacoes",
        "#/financeiro/bonificacoes/horaria",
        "#/financeiro/bonificacoes/produtividade",
        "#/financeiro/fechamento-parametros",
        "#/financeiro/lancamentos-jornada",
        "#/financeiro/missoes",
    ]
    assert finance_nav_hrefs == [
        "#/financeiro/fechamento-parametros",
        "#/financeiro/lancamentos-jornada",
    ]
    assert finance_permissions == [
        "finance:bonuses:read",
        "finance:missions:read",
        "finance:parameters:read",
        "finance:periods:read",
    ]
    for forbidden_route in (
        "#/financeiro/parametros",
        "#/financeiro/feriados",
        "#/missoes",
        "#/produtividade",
    ):
        assert forbidden_route not in _strip_js_comments(f"{route_registry_source}\n{navigation_source}").lower()


def test_finance_routes_do_not_import_persistence_or_call_audit_layers_directly():
    violations = []
    tree = _python_tree(FINANCE_ROUTES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for candidate in _import_candidates(node):
                for banned_module in FORBIDDEN_FINANCE_ROUTE_IMPORTS:
                    if _module_matches(candidate, banned_module):
                        violations.append(f"{FINANCE_ROUTES}:{node.lineno}: import '{candidate}' violates Financeiro route boundary.")
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name and any(call_name == name or call_name.endswith(f".{name}") for name in FORBIDDEN_FINANCE_STUB_CALLS):
                violations.append(
                    f"{FINANCE_ROUTES}:{node.lineno}: call '{call_name}' violates Financeiro stub boundary."
                )

    assert violations == []


def test_finance_mission_status_contract_matches_schema_runtime_enum():
    schema_values = _schema_enum_values(table="financeiro_missoes_operacionais", column="status")
    assert FINANCE_MISSION_STATUS == schema_values


def test_finance_divergence_severity_contract_matches_schema_runtime_enum():
    schema_values = _schema_enum_values(table="financeiro_divergencias", column="severidade")
    assert FINANCE_DIVERGENCE_SEVERITIES == schema_values


def test_finance_stub_contract_matrix_is_explicit_and_disjoint_from_registered_routes():
    registered = _registered_finance_route_contract_keys()
    stub_keys = {(contract["method"], contract["path"]) for contract in FINANCE_STUB_HTTP_CONTRACTS}
    runtime_keys = {(contract["method"], contract["path"]) for contract in FINANCE_HTTP_CONTRACTS}

    assert stub_keys == set()
    assert stub_keys.isdisjoint(registered)
    assert runtime_keys == registered


def test_removed_missoes_produtividade_routes_are_not_restored_by_finance_baseline():
    registered_routes = _registered_routes()
    restored_routes = sorted(
        route for route in registered_routes if any(route.startswith(prefix) for prefix in LEGACY_ROUTE_PREFIXES)
    )
    navigation_source = SHELL_NAVIGATION.read_text(encoding="utf-8")
    route_registry_source = ROUTE_REGISTRY.read_text(encoding="utf-8")
    frontend_markers = []
    legacy_frontend_patterns = {
        "#/missoes": re.compile(r'["\']#\/missoes(?:["\'/?#]|$)'),
        "/api/v1/missoes": re.compile(r'["\']/api/v1/missoes(?:["\'/?#]|$)'),
        "#/produtividade": re.compile(r'["\']#\/produtividade(?:["\'/?#]|$)'),
    }
    for source_path, source in ((SHELL_NAVIGATION, navigation_source), (ROUTE_REGISTRY, route_registry_source)):
        commentless = _strip_js_comments(source).lower()
        for marker, pattern in legacy_frontend_patterns.items():
            if pattern.search(commentless):
                frontend_markers.append(f"{source_path.relative_to(ROOT)}::{marker}")

    assert restored_routes == []
    assert frontend_markers == []


def test_finance_api_routes_are_stub_only_and_do_not_restore_legacy_paths():
    finance_routes = sorted(route for route in _registered_routes() if route.startswith(FINANCE_API_ROUTE_PREFIX))

    assert finance_routes
    assert not any(route.startswith(LEGACY_ROUTE_PREFIXES) for route in finance_routes)
