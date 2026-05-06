from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PACKAGE = REPO_ROOT / "backend" / "src" / "controle_treinamentos"


def _py_files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*.py") if path.is_file())


def test_service_layers_are_http_agnostic():
    service_layers_dir = BACKEND_PACKAGE / "service_layers"
    assert service_layers_dir.exists()
    http_patterns = (
        re.compile(r"^\s*from\s+flask\s+import\s+", re.MULTILINE),
        re.compile(r"^\s*import\s+flask\b", re.MULTILINE),
        re.compile(r"\brender_template\s*\("),
        re.compile(r"\brequest\s*\."),
    )
    offenders = []
    for file_path in _py_files(service_layers_dir):
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in http_patterns):
            offenders.append(str(file_path))
    assert offenders == []


def test_critical_blueprints_are_split_to_smaller_modules():
    limits = {
        BACKEND_PACKAGE / "blueprints" / "admin" / "routes.py": 725,
        BACKEND_PACKAGE / "blueprints" / "cadastros" / "routes.py": 650,
    }
    oversized = []
    for file_path, max_lines in limits.items():
        assert file_path.exists()
        line_count = sum(1 for _ in file_path.open("r", encoding="utf-8", errors="ignore"))
        if line_count > max_lines:
            oversized.append(f"{file_path}:{line_count}>{max_lines}")
    assert oversized == []
