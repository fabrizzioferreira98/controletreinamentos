from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend" / "src" / "controle_treinamentos"


REMOVED_SURFACE_PATTERNS = (
    "painel-tv",
    "painel_tv",
    "Painel TV",
    "tv_vencimentos",
    "tv_produtividade",
    "/api/v1/tv",
    "relatorio_produtividade",
    "produtividade_adicionais",
    "produtividade_consolidado",
    "produtividade_tripulante",
    "produtividade_jornadas",
    "produtividade_regras",
    "produtividade_parametros",
    "produtividade_conferencias",
    "conta_missao_produtividade",
    "idx_missoes_conta_prod",
    "idx_excepcionais",
    "build_produtividade",
    "get_tv_",
)

REMOVED_FILES = (
    "application/produtividade_adicionais_ssr.py",
    "application/produtividade_conferencias_api.py",
    "application/produtividade_jornadas_api.py",
    "application/produtividade_reads_api.py",
    "application/produtividade_tv_api.py",
    "produtividade.py",
    "compat/python_reexports/produtividade.py",
    "service_layers/produtividade.py",
    "service_layers/produtividade_extrato_periodo.py",
    "service_layers/produtividade_jornada.py",
    "service_layers/produtividade_jornada_integracao.py",
    "service_layers/produtividade_jornadas.py",
    "repositories/produtividade_adicionais.py",
    "repositories/produtividade_engine.py",
    "repositories/produtividade_extrato_periodo.py",
    "repositories/produtividade_jornadas.py",
    "repositories/produtividade_parametros_regras.py",
    "templates/painel_tv.html",
    "templates/produtividade_adicionais_list.html",
    "templates/produtividade_adicional_form.html",
    "templates/produtividade_consolidado.html",
    "templates/produtividade_painel_tv.html",
    "templates/produtividade_tripulante.html",
    "static/tv-panel.js",
    "static/tv-panel.css",
    "static/produtividade-tv.js",
    "static/produtividade-tv.css",
)


def _active_backend_sources() -> list[Path]:
    suffixes = {".py", ".html", ".js", ".css"}
    return [
        path
        for path in BACKEND.rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and "__pycache__" not in path.parts
    ]


def test_removed_backend_files_do_not_exist():
    leftovers = [relative for relative in REMOVED_FILES if (BACKEND / relative).exists()]
    assert leftovers == []


def test_removed_backend_surfaces_have_no_executable_references_outside_schema():
    matches: list[str] = []
    for path in _active_backend_sources():
        source = path.read_text(encoding="utf-8")
        for pattern in REMOVED_SURFACE_PATTERNS:
            if pattern in source:
                matches.append(f"{path.relative_to(BACKEND)}::{pattern}")

    assert matches == []
