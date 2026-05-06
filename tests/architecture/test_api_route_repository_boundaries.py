from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PACKAGE = REPO_ROOT / "backend" / "src" / "controle_treinamentos"
CADASTROS_ROUTES = BACKEND_PACKAGE / "api" / "http" / "cadastros" / "routes.py"
TRAINING_PROGRAM_ROUTES = BACKEND_PACKAGE / "api" / "http" / "cadastros" / "routes_training_program.py"
OPERACOES_ROUTES = BACKEND_PACKAGE / "api" / "http" / "operacoes" / "routes.py"


IMPORT_RULES = {
    CADASTROS_ROUTES: {
        "banned_modules": ("repositories",),
        "reason": "Lote 1 APIs must delegate reads through application read use cases.",
    },
    TRAINING_PROGRAM_ROUTES: {
        "banned_modules": ("repositories.training_program",),
        "reason": "Lote 2 training_program reads must not import repositories.training_program in the route.",
    },
    OPERACOES_ROUTES: {
        "banned_modules": ("repositories", "db"),
        "reason": "Operacoes/Pernoites API reads must delegate through application read use cases.",
    },
}


PROTECTED_GET_HANDLERS = {
    CADASTROS_ROUTES: {
        "api_tripulantes_list": {
            "required_calls": ("list_tripulantes_read_model",),
            "forbidden_calls": (
                "get_db",
                "count_tripulantes",
                "fetch_tripulante_list_page",
            ),
        },
        "api_tripulantes_options": {
            "required_calls": ("get_tripulantes_options_read_model",),
            "forbidden_calls": ("get_db", "fetch_base_options"),
        },
        "api_tripulante_get": {
            "required_calls": ("get_tripulante_detail_read_model",),
            "forbidden_calls": ("get_db", "fetch_tripulante_detail"),
        },
        "api_treinamentos_list": {
            "required_calls": ("list_treinamentos_read_model",),
            "forbidden_calls": (
                "get_db",
                "count_treinamentos",
                "build_training_filters",
                "fetch_training_page",
            ),
        },
        "api_equipamentos_options": {
            "required_calls": ("get_equipamentos_options_read_model",),
            "forbidden_calls": ("get_db", "fetch_equipamento_options"),
        },
        "api_treinamentos_options": {
            "required_calls": ("get_treinamentos_options_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_options"),
        },
        "api_treinamento_get": {
            "required_calls": ("get_treinamento_detail_read_model",),
            "forbidden_calls": ("get_db", "fetch_treinamento_detail"),
        },
    },
    TRAINING_PROGRAM_ROUTES: {
        "api_training_master_options": {
            "required_calls": ("get_training_master_options_read_model",),
            "forbidden_calls": (
                "get_db",
                "fetch_training_master_types",
                "fetch_training_program_aircraft_models",
            ),
        },
        "api_training_master_types_list": {
            "required_calls": ("list_training_master_entities_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_master_types"),
        },
        "api_training_master_type_get": {
            "required_calls": ("get_training_master_entity_detail_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_master_type_detail"),
        },
        "api_training_master_segments_list": {
            "required_calls": ("list_training_master_entities_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_master_segments"),
        },
        "api_training_master_segment_get": {
            "required_calls": ("get_training_master_entity_detail_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_master_segment_detail"),
        },
        "api_training_master_hours_list": {
            "required_calls": ("list_training_master_entities_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_master_hours"),
        },
        "api_training_master_hour_get": {
            "required_calls": ("get_training_master_entity_detail_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_master_hour_detail"),
        },
        "api_training_program_tripulantes_options": {
            "required_calls": ("get_tripulante_program_options_read_model",),
            "forbidden_calls": (
                "get_db",
                "fetch_training_program_tripulantes",
                "fetch_training_program_active_types",
                "fetch_training_program_aircraft_models",
            ),
        },
        "api_training_program_records_list": {
            "required_calls": ("list_tripulante_program_records_read_model",),
            "forbidden_calls": ("get_db", "fetch_training_program_record_list"),
        },
        "api_training_program_record_get": {
            "required_calls": ("get_tripulante_program_record_detail_read_model",),
            "forbidden_calls": (
                "get_db",
                "fetch_training_program_record_detail",
                "fetch_treinamento_attachments",
            ),
        },
    },
    OPERACOES_ROUTES: {
        "api_operacoes_pernoites_list": {
            "required_calls": ("list_pernoites_read_model",),
            "forbidden_calls": ("get_db", "count_pernoites", "fetch_pernoite_list_page"),
        },
        "api_operacoes_pernoite_detail": {
            "required_calls": ("get_pernoite_read_model",),
            "forbidden_calls": ("get_db", "fetch_pernoite_detail"),
        },
    },
}


def _tree(file_path: Path) -> ast.Module:
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


def test_corrected_api_routes_do_not_import_prohibited_repositories():
    violations = []
    for file_path, rule in IMPORT_RULES.items():
        tree = _tree(file_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            for candidate in _import_candidates(node):
                for banned_module in rule["banned_modules"]:
                    if _module_matches(candidate, banned_module):
                        violations.append(
                            f"{file_path}:{node.lineno}: import '{candidate}' violates "
                            f"'{banned_module}' boundary. {rule['reason']}"
                        )
    assert violations == []


def test_corrected_get_handlers_delegate_to_application_read_use_cases():
    violations = []
    for file_path, handlers in PROTECTED_GET_HANDLERS.items():
        function_defs = _function_defs(_tree(file_path))
        for handler_name, rule in handlers.items():
            handler = function_defs.get(handler_name)
            if handler is None:
                violations.append(f"{file_path}: missing protected handler '{handler_name}'")
                continue

            calls = []
            for node in ast.walk(handler):
                if isinstance(node, ast.Call):
                    call_name = _call_name(node.func)
                    if call_name:
                        calls.append((call_name, node.lineno))

            called_names = {name for name, _line in calls}
            for required_call in rule["required_calls"]:
                if not any(name == required_call or name.endswith(f".{required_call}") for name in called_names):
                    violations.append(
                        f"{file_path}:{handler.lineno}: handler '{handler_name}' must delegate to "
                        f"application read use case '{required_call}'."
                    )

            for forbidden_call in rule["forbidden_calls"]:
                for call_name, line in calls:
                    if call_name == forbidden_call or call_name.endswith(f".{forbidden_call}"):
                        violations.append(
                            f"{file_path}:{line}: handler '{handler_name}' calls '{call_name}' directly; "
                            "corrected GET routes must not orchestrate repositories or db access."
                        )
    assert violations == []
