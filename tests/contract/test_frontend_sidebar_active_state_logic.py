from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sidebar_active_state_is_derived_from_navigation_match_logic():
    source = _read(FRONTEND_SRC / "shell" / "navigation.js")

    assert "const itemActive = isItemActive(item, activeRoute);" in source
    assert "const groupActive = groupItems.some((item) => isItemActive(item, activeRoute));" in source
    assert 'data-nav-active="${itemActive ? "true" : "false"}"' in source
    assert 'data-nav-active-child="${groupActive ? "true" : "false"}"' in source
    assert 'data-nav-level="${escapeAttr(navLevel)}"' in source
    assert "data-nav-boundary" in source
    assert "capabilitySet()" in source


def test_sidebar_active_visual_contract_exists_for_all_sidebar_modes():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".nav-active-indicator",
        '.nav-group[data-nav-active-child="true"] > .nav-group-toggle',
        ".nav-group-links a.active",
        '.app-shell[data-sidebar-state="iconic"] .nav-active-indicator',
        '.app-shell[data-sidebar-state] .nav-group[data-nav-active-child="true"] > .nav-group-toggle',
    ):
        assert expected in css


def test_sidebar_group_behavior_keeps_accordion_and_flyout_modes_separate():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    assert 'navGroupEl.dataset.navMode = railMode ? "flyout" : "accordion";' in source
    assert 'navGroupEl.classList.toggle("flyout-open", willOpen);' in source
    assert 'navGroupEl.classList.toggle("open");' in source
    assert 'if (links) links.hidden = railMode ? !flyoutOpen : !expanded;' in source
