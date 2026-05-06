from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "templates"
DASHBOARD_ROUTES = (
    REPO_ROOT
    / "backend"
    / "src"
    / "controle_treinamentos"
    / "blueprints"
    / "dashboard"
    / "routes.py"
)
MIGRATION_DOC = REPO_ROOT / "docs" / "migration" / "94.ssr-template-canonical-link-guards.md"
README = REPO_ROOT / "README.md"

URL_FOR_PATTERN = re.compile(r"url_for\(['\"]([^'\"]+)['\"]")

USER_DISCOVERABLE_TEMPLATES = {
    "base.html",
    "dashboard.html",
}

MIGRATED_SURFACE_ENDPOINTS = {
    "cadastros.tripulantes_list": "/#/tripulantes",
    "cadastros.tripulantes_new": "/#/tripulantes/new",
    "cadastros.tripulantes_edit": "/#/tripulantes/<id>",
    "cadastros.treinamentos_list": "/#/treinamentos",
    "cadastros.treinamentos_new": "/#/treinamentos/new",
    "cadastros.treinamentos_edit": "/#/treinamentos/<id>",
    "cadastros.treinamentos_consolidado": "/#/relatorios/habilitacoes",
    "cadastros.tipos_list": "/#/treinamentos/raiz",
    "cadastros.tipos_new": "/#/treinamentos/raiz",
    "cadastros.tipos_edit": "/#/treinamentos/raiz",
}

# Excecoes formais: paginas SSR legadas autocontidas ainda vivas para compatibilidade
# direta. Elas nao podem voltar a ser descobertas por shell, dashboard, cards ou atalhos.
FORMAL_TEMPLATE_EXCEPTIONS = {
    "tipos_form.html": {"cadastros.tipos_list"},
    "tipos_list.html": {"cadastros.tipos_new", "cadastros.tipos_edit"},
    "treinamentos_consolidado.html": {
        "cadastros.treinamentos_consolidado",
        "cadastros.treinamentos_edit",
        "cadastros.treinamentos_list",
    },
    "treinamentos_consolidado_relatorio.html": {"cadastros.treinamentos_consolidado"},
    "treinamentos_form.html": {"cadastros.treinamentos_list"},
    "treinamentos_list.html": {
        "cadastros.treinamentos_edit",
        "cadastros.treinamentos_list",
        "cadastros.treinamentos_new",
    },
    "tripulantes_file.html": {
        "cadastros.treinamentos_edit",
        "cadastros.tripulantes_edit",
        "cadastros.tripulantes_list",
    },
    "tripulantes_form.html": {"cadastros.tripulantes_list"},
    "tripulantes_list.html": {
        "cadastros.tripulantes_edit",
        "cadastros.tripulantes_list",
        "cadastros.tripulantes_new",
    },
}

PUBLIC_TEMPLATE_CANONICAL_HASHES = {
    "base.html": {
        "/#/relatorios/habilitacoes",
        "/#/relatorios/individual",
        "/#/tripulantes",
        "/#/treinamentos",
        "/#/treinamentos/raiz",
    },
    "dashboard.html": {
        "/#/tripulantes",
        "/#/treinamentos",
        "/#/treinamentos/raiz",
        "/#/treinamentos?status=vencido",
        "/#/treinamentos?periodo=7",
        "/#/treinamentos?periodo=30",
    },
}


def _template_files() -> list[Path]:
    return sorted(TEMPLATES_DIR.rglob("*.html"))


def _relative_template(path: Path) -> str:
    return path.relative_to(TEMPLATES_DIR).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _url_for_endpoints(source: str) -> set[str]:
    return set(URL_FOR_PATTERN.findall(source))


def test_user_discoverable_ssr_templates_do_not_link_to_migrated_legacy_endpoints():
    violations = []

    for template in USER_DISCOVERABLE_TEMPLATES:
        source = _read(TEMPLATES_DIR / template)
        endpoints = _url_for_endpoints(source) & set(MIGRATED_SURFACE_ENDPOINTS)
        for endpoint in sorted(endpoints):
            violations.append(
                f"{template}: url_for('{endpoint}') reintroduces legacy navigation for "
                f"migrated surface {MIGRATED_SURFACE_ENDPOINTS[endpoint]}; public SSR "
                "templates must use the canonical SPA hash instead."
            )

    assert violations == []


def test_all_migrated_legacy_template_links_are_formally_exceptioned():
    violations = []

    for template_path in _template_files():
        template = _relative_template(template_path)
        source = _read(template_path)
        endpoints = _url_for_endpoints(source) & set(MIGRATED_SURFACE_ENDPOINTS)
        allowed = FORMAL_TEMPLATE_EXCEPTIONS.get(template, set())

        for endpoint in sorted(endpoints - allowed):
            violations.append(
                f"{template}: url_for('{endpoint}') points to migrated legacy surface "
                f"{MIGRATED_SURFACE_ENDPOINTS[endpoint]} without a formal exception."
            )

        unexpected_allowances = allowed - endpoints
        for endpoint in sorted(unexpected_allowances):
            violations.append(
                f"{template}: exception for url_for('{endpoint}') is stale; remove or "
                "update FORMAL_TEMPLATE_EXCEPTIONS and docs/migration/94."
            )

    assert violations == []


def test_public_ssr_templates_expose_canonical_hashes_for_migrated_surfaces():
    violations = []

    for template, hashes in PUBLIC_TEMPLATE_CANONICAL_HASHES.items():
        source = _read(TEMPLATES_DIR / template)
        for expected_hash in sorted(hashes):
            if expected_hash not in source:
                violations.append(f"{template}: missing canonical SPA href {expected_hash!r}.")

    assert violations == []


def test_dashboard_runtime_shortcuts_do_not_rebuild_legacy_training_urls():
    source = _read(DASHBOARD_ROUTES)

    assert "url_for(\"cadastros.treinamentos_edit\"" not in source
    assert "f\"/#/treinamentos/{item['training_id']}\"" in source


def test_formal_exceptions_are_documented_and_indexed():
    migration = _read(MIGRATION_DOC)
    readme = _read(README)

    assert "94.ssr-template-canonical-link-guards.md" in readme

    for template, endpoints in FORMAL_TEMPLATE_EXCEPTIONS.items():
        assert f"`{template}`" in migration
        for endpoint in endpoints:
            assert f"`{endpoint}`" in migration
