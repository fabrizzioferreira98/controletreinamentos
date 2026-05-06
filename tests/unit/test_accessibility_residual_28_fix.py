from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = PROJECT_ROOT / "backend" / "src" / "controle_treinamentos" / "templates"
STATIC = PROJECT_ROOT / "backend" / "src" / "controle_treinamentos" / "static"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    raw = value.strip().lstrip("#")
    return tuple(int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(item) for item in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: str, background: str) -> float:
    lum_a = _relative_luminance(_hex_to_rgb(foreground))
    lum_b = _relative_luminance(_hex_to_rgb(background))
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def test_shell_has_persistent_live_regions_focus_after_render_and_no_label_generation():
    source = _read(TEMPLATES / "base.html")

    assert 'id="appStatusRegion" class="sr-only" role="status" aria-live="polite" aria-atomic="true"' in source
    assert 'id="appAlertRegion" class="sr-only" role="alert" aria-live="assertive" aria-atomic="true"' in source
    assert '<main class="content" id="mainContent" tabindex="-1">' in source
    assert "document.body.addEventListener('htmx:afterSwap'" in source
    assert "focusMainHeading();" in source
    assert "function auditUnlabeledControls" in source
    assert "derivedControlLabel" not in source
    assert "getAttribute('placeholder')" not in source
    assert "a11yLabelGenerated" not in source


def test_placeholder_fields_are_inside_persistent_labels():
    offenders: list[str] = []
    for template in TEMPLATES.rglob("*.html"):
        source = _read(template)
        for match in re.finditer(r"<input\b[^>]*placeholder=", source):
            window = source[max(0, match.start() - 260) : match.end() + 260]
            if "<label" not in window or "</label>" not in window:
                offenders.append(str(template.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_collapsible_filters_restore_focus_and_expose_labels():
    expected_labels = {
        "treinamentos_list.html": ["Tripulante", "Equipamento", "Tipo de treinamento", "Periodo de vencimento"],
        "treinamentos_consolidado.html": ["Tripulante", "Tipo de habilitacao", "Ordenacao"],
    }

    for filename, labels in expected_labels.items():
        source = _read(TEMPLATES / filename)
        for label in labels:
            assert f"<span>{label}</span>" in source
        assert 'panel.setAttribute("aria-hidden", String(!expanded));' in source
        assert "window.appA11y?.focusFirstInteractive(panel)" in source
        assert "toggle.focus();" in source


def test_bases_map_has_keyboard_alternative_live_status_and_modal_semantics():
    source = _read(TEMPLATES / "bases" / "index.html")

    assert 'id="basesMapAlternativeHint"' in source
    assert 'role="region" tabindex="0" aria-label="Mapa visual das bases do Brasil"' in source
    assert 'id="basesAlternativeList" class="bases-alternative-list"' in source
    assert 'id="basesAlternativeStatus" class="secondary-cell" role="status" aria-live="polite" aria-atomic="true"' in source
    assert "base-alt-open" in source
    assert "markerEntityForKey" in source
    assert 'id="basesModalShell" role="presentation" aria-hidden="true"' in source
    assert 'class="modal-backdrop" data-close-modal aria-hidden="true" tabindex="-1"' in source
    assert 'aria-labelledby="modalHistoryTitle"' in source
    assert "data-initial-focus" in source
    assert "function setModalBackgroundInert" in source
    assert 'root.setAttribute("inert", "");' in source
    assert 'window.appA11y?.announce(message, isAlert ? "assertive" : "polite");' in source


def test_success_state_contrast_is_not_soft_green_on_soft_green():
    css = _read(STATIC / "styles.css")
    variables = dict(re.findall(r"--(color-success-[a-z-]+):\s*(#[0-9a-fA-F]{6});", css))

    ratio = _contrast_ratio(variables["color-success-strong"], variables["color-success-soft"])

    assert ratio >= 4.5
    assert ".status-green" in css
    assert "color: var(--color-success-strong);" in css
    assert "background: var(--color-success-soft);" in css


def test_accessibility_fix_document_records_scope_validation_and_debt():
    doc = _read(PROJECT_ROOT / "docs" / "migration" / "28.fix-acessibilidade-residual.md")

    for section in [
        "## 1. HOTSPOTS RESIDUAIS",
        "## 2. CORRECOES APLICADAS",
        "## 3. FOCO / LABEL / LIVE REGION",
        "## 4. MAPA / MODAL / CONTRASTE",
        "## 5. VALIDACAO",
        "## 6. DIVIDA ADIADA",
    ]:
        assert section in doc
    assert "lista alternativa" in doc
    assert "placeholder" in doc
    assert "inert" in doc
    assert "leitor de tela real" in doc
