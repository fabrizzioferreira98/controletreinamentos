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

PROTECTED_HANDLERS = {
    "treinamentos_consolidado": {
        "required_calls": ("get_treinamentos_consolidado_context",),
        "forbidden_terminal_calls": (
            "get_habilitacoes_report_data",
            "habilitacoes_report_to_html_context",
        ),
    },
    "treinamentos_consolidado_relatorio": {
        "required_calls": ("get_treinamentos_consolidado_relatorio_context",),
        "forbidden_terminal_calls": (
            "get_habilitacoes_report_data",
            "habilitacoes_report_to_print_context",
        ),
    },
    "treinamentos_consolidado_export_pdf": {
        "required_calls": ("build_treinamentos_consolidado_pdf_export",),
        "forbidden_terminal_calls": (
            "get_habilitacoes_report_data",
            "habilitacoes_report_to_export_payload",
            "build_habilitacoes_consolidado_pdf",
            "safe_pdf_filename",
            "audit_document_generation",
        ),
    },
    "treinamentos_consolidado_export_csv": {
        "required_calls": ("build_treinamentos_consolidado_csv_export",),
        "forbidden_terminal_calls": (
            "get_habilitacoes_report_data",
            "habilitacoes_report_to_csv_export",
            "habilitacoes_report_to_export_payload",
            "audit_document_generation",
        ),
    },
    "treinamentos_anexo_upload": {
        "required_calls": ("upload_treinamento_attachment_from_form",),
        "forbidden_terminal_calls": (
            "upload_treinamento_attachment",
            "safe_pdf_filename",
            "resolve_file_access_action",
        ),
    },
    "treinamentos_anexo_get": {
        "required_calls": ("get_treinamento_attachment_response_model",),
        "forbidden_terminal_calls": (
            "get_treinamento_attachment",
            "safe_pdf_filename",
            "resolve_file_access_action",
        ),
    },
    "treinamentos_anexo_delete": {
        "required_calls": ("delete_treinamento_attachment_from_form",),
        "forbidden_terminal_calls": ("delete_treinamento_attachment",),
    },
}

GLOBAL_FORBIDDEN_TERMINAL_CALLS = {
    "get_db",
    "execute",
    "commit",
    "rollback",
    "rollback_db",
    # direct repository/storage/blob style calls that should remain outside these route handlers
    "write_training_attachment",
    "read_document_blob",
    "delete_media_ref",
}

ALLOWED_RESPONSE_HELPERS = {
    "build_pdf_document_response",
    "build_file_access_response",
    "audit_relevant_download",
}

SQL_LITERAL_PATTERN = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE)\b|"
    r"\bFROM\b|"
    r"\bJOIN\b",
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


def _iter_function_nodes(handler: ast.FunctionDef | ast.AsyncFunctionDef):
    for statement in handler.body:
        yield statement
        yield from ast.walk(statement)


def _terminal_name(call_name: str) -> str:
    return call_name.rsplit(".", 1)[-1]


def test_migrated_treinamentos_ssr_reports_and_attachments_handlers_keep_boundaries():
    violations: list[str] = []
    function_defs = _function_defs(_tree(ROUTES_TREINAMENTOS))

    for handler_name, rule in PROTECTED_HANDLERS.items():
        handler = function_defs.get(handler_name)
        if handler is None:
            violations.append(f"{ROUTES_TREINAMENTOS}: missing protected handler '{handler_name}'")
            continue

        called_names: set[str] = set()
        forbidden_terminals = set(GLOBAL_FORBIDDEN_TERMINAL_CALLS)
        forbidden_terminals.update(rule["forbidden_terminal_calls"])

        for node in _iter_function_nodes(handler):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if not call_name:
                    continue
                called_names.add(call_name)
                terminal = _terminal_name(call_name)

                if terminal in ALLOWED_RESPONSE_HELPERS:
                    continue

                if call_name.endswith(".execute") or terminal in forbidden_terminals:
                    violations.append(
                        f"{ROUTES_TREINAMENTOS}:{node.lineno}: handler '{handler_name}' calls '{call_name}' "
                        "directly; migrated R.1/R.2/R.3 handlers must delegate orchestration to application "
                        "and avoid DB/SQL/repository/storage direct access."
                    )

            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if SQL_LITERAL_PATTERN.search(node.value):
                    violations.append(
                        f"{ROUTES_TREINAMENTOS}:{node.lineno}: handler '{handler_name}' contains SQL literal "
                        f"{node.value[:80]!r}; SQL should not be present in migrated consolidated/export/"
                        "attachments route handlers."
                    )

        for required_call in rule["required_calls"]:
            if not any(name == required_call or name.endswith(f".{required_call}") for name in called_names):
                violations.append(
                    f"{ROUTES_TREINAMENTOS}:{handler.lineno}: handler '{handler_name}' must delegate to "
                    f"application call '{required_call}'."
                )

    assert violations == []
