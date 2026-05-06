from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_CATALOGOS = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "blueprints"
    / "cadastros"
    / "routes_catalogos.py"
)

PROTECTED_HANDLERS = {
    "equipamentos_list": ("get_equipamentos_list_context",),
    "equipamentos_new": ("create_equipamento_from_form", "get_equipamento_form_context"),
    "equipamentos_edit": ("update_equipamento_from_form", "get_equipamento_form_context"),
    "equipamentos_delete": ("delete_equipamento_with_guards",),
    "tipos_list": ("get_tipos_treinamento_list_context",),
    "tipos_new": ("create_tipo_treinamento_from_form", "get_tipo_treinamento_form_context"),
    "tipos_edit": ("update_tipo_treinamento_from_form", "get_tipo_treinamento_form_context"),
    "tipos_delete": ("delete_tipo_treinamento_with_guards",),
}

BANNED_IMPORT_SEGMENTS = ("db", "repositories")
BANNED_CALL_NAMES = ("get_db", "execute")
SQL_LITERAL_PATTERN = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)


def _tree(file_path: Path) -> ast.Module:
    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def _import_candidates(node: ast.AST) -> list[tuple[str, int]]:
    if isinstance(node, ast.Import):
        return [(alias.name, node.lineno) for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        candidates = [(module, node.lineno)] if module else []
        candidates.extend((f"{module}.{alias.name}" if module else alias.name, node.lineno) for alias in node.names)
        return candidates
    return []


def _module_has_segment(candidate: str, segment: str) -> bool:
    return segment in candidate.split(".")


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _call_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def _function_defs(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def _walk_function_body(handler: ast.FunctionDef | ast.AsyncFunctionDef):
    for statement in handler.body:
        yield statement
        yield from ast.walk(statement)


def test_routes_catalogos_does_not_import_db_or_repositories_directly():
    violations = []
    tree = _tree(ROUTES_CATALOGOS)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        for candidate, line in _import_candidates(node):
            for segment in BANNED_IMPORT_SEGMENTS:
                if _module_has_segment(candidate, segment):
                    violations.append(
                        f"{ROUTES_CATALOGOS}:{line}: import '{candidate}' violates the migrated "
                        "catalogos SSR boundary; routes_catalogos.py must delegate database and "
                        "repository access through application.catalogos_ssr."
                    )

    assert violations == []


def test_migrated_catalogos_ssr_handlers_do_not_execute_sql_directly():
    violations = []
    function_defs = _function_defs(_tree(ROUTES_CATALOGOS))

    for handler_name, required_calls in PROTECTED_HANDLERS.items():
        handler = function_defs.get(handler_name)
        if handler is None:
            violations.append(f"{ROUTES_CATALOGOS}: missing protected handler '{handler_name}'")
            continue

        called_names = set()
        for node in _walk_function_body(handler):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if not call_name:
                    continue
                called_names.add(call_name)
                if call_name in BANNED_CALL_NAMES or call_name.endswith(".execute"):
                    violations.append(
                        f"{ROUTES_CATALOGOS}:{node.lineno}: handler '{handler_name}' calls "
                        f"'{call_name}' directly; migrated catalogos SSR handlers must not access "
                        "the database or execute SQL."
                    )

            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if SQL_LITERAL_PATTERN.search(node.value):
                    violations.append(
                        f"{ROUTES_CATALOGOS}:{node.lineno}: handler '{handler_name}' contains "
                        f"SQL literal {node.value[:60]!r}; SQL belongs in repositories/catalogos.py."
                    )

        for required_call in required_calls:
            if not any(call == required_call or call.endswith(f".{required_call}") for call in called_names):
                violations.append(
                    f"{ROUTES_CATALOGOS}:{handler.lineno}: handler '{handler_name}' must keep "
                    f"delegating to application use case '{required_call}'."
                )

    assert violations == []
