from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_TREINAMENTOS = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "blueprints"
    / "cadastros"
    / "routes_treinamentos.py"
)

BANNED_DIRECT_CALLS = {
    "get_db",
    "execute",
    "commit",
    "rollback",
    "rollback_db",
    "build_training_filters",
    "count_treinamentos",
    "fetch_training_page",
    "get_treinamentos_summary",
    "list_treinamentos_ssr_page",
    "get_treinamento_for_edit",
}
SQL_LITERAL_PATTERN = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE)\b|"
    r"\bFROM\s+treinamentos\b",
    re.IGNORECASE,
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


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


def _iter_nodes(statements: list[ast.stmt]):
    for statement in statements:
        yield statement
        yield from ast.walk(statement)


def _is_request_method_guard(expr: ast.AST, method: str) -> bool:
    if isinstance(expr, ast.BoolOp):
        return any(_is_request_method_guard(value, method) for value in expr.values)
    if not isinstance(expr, ast.Compare):
        return False

    left_name = _call_name(expr.left)
    for op, comparator in zip(expr.ops, expr.comparators):
        if not isinstance(op, ast.Eq):
            continue
        if left_name != "request.method":
            continue
        if isinstance(comparator, ast.Constant) and comparator.value == method:
            return True
    return False


def _find_post_guard(handler: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.If | None:
    for statement in handler.body:
        if isinstance(statement, ast.If) and _is_request_method_guard(statement.test, "POST"):
            return statement
    return None


def _collect_violations(*, scope_name: str, statements: list[ast.stmt], required_call: str) -> list[str]:
    violations: list[str] = []
    called_names: set[str] = set()

    for node in _iter_nodes(statements):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if not call_name:
                continue
            called_names.add(call_name)
            terminal_name = call_name.rsplit(".", 1)[-1]
            if (
                call_name in BANNED_DIRECT_CALLS
                or terminal_name in BANNED_DIRECT_CALLS
                or call_name.endswith(".execute")
            ):
                violations.append(
                    f"{ROUTES_TREINAMENTOS}:{node.lineno}: trecho '{scope_name}' chama "
                    f"'{call_name}' diretamente; handlers SSR migrados de treinamentos não podem "
                    "acessar DB/repository diretamente."
                )

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_LITERAL_PATTERN.search(node.value):
                violations.append(
                    f"{ROUTES_TREINAMENTOS}:{node.lineno}: trecho '{scope_name}' contém SQL literal "
                    f"{node.value[:80]!r}; SQL deve ficar em repositories/treinamentos.py."
                )

    if not any(name == required_call or name.endswith(f".{required_call}") for name in called_names):
        violations.append(
            f"{ROUTES_TREINAMENTOS}: trecho '{scope_name}' deve delegar para "
            f"'{required_call}' em application/treinamentos_ssr.py."
        )

    return violations


def test_migrated_treinamentos_ssr_handlers_do_not_execute_sql_directly():
    violations: list[str] = []
    function_defs = _function_defs(_tree(ROUTES_TREINAMENTOS))

    treinamentos_list = function_defs.get("treinamentos_list")
    if treinamentos_list is None:
        violations.append(f"{ROUTES_TREINAMENTOS}: handler protegido 'treinamentos_list' não encontrado.")
    else:
        violations.extend(
            _collect_violations(
                scope_name="treinamentos_list",
                statements=list(treinamentos_list.body),
                required_call="get_treinamentos_list_context",
            )
        )

    treinamentos_edit = function_defs.get("treinamentos_edit")
    if treinamentos_edit is None:
        violations.append(f"{ROUTES_TREINAMENTOS}: handler protegido 'treinamentos_edit' não encontrado.")
    else:
        post_guard = _find_post_guard(treinamentos_edit)
        if post_guard is None:
            violations.append(
                f"{ROUTES_TREINAMENTOS}:{treinamentos_edit.lineno}: não foi possível identificar o ramo "
                "POST de 'treinamentos_edit' para analisar apenas o caminho GET."
            )
        else:
            get_path_statements = [statement for statement in treinamentos_edit.body if statement is not post_guard]
            violations.extend(
                _collect_violations(
                    scope_name="treinamentos_edit[GET]",
                    statements=get_path_statements,
                    required_call="get_treinamento_edit_context",
                )
            )

    assert violations == []
