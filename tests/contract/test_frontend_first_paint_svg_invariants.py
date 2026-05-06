from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PAGE = ROOT / "frontend" / "src" / "features" / "dashboard" / "page.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_sparkline_has_inline_first_paint_safety_invariants():
    source = _read(DASHBOARD_PAGE)
    sparkline_block = source.split("function renderDashboardSparkline", 1)[1].split("function renderDashboardActions", 1)[0]

    assert '<svg viewBox="0 0 130 48" role="presentation" focusable="false" fill="none">' in sparkline_block
    assert 'fill="none"' in sparkline_block
    assert 'stroke="currentColor"' in sparkline_block
    assert 'stroke-width="2.8"' in sparkline_block
    assert 'stroke-linecap="round"' in sparkline_block
    assert 'stroke-linejoin="round"' in sparkline_block
    assert 'vector-effect="non-scaling-stroke"' in sparkline_block
    assert '<path d="${line}" />' not in sparkline_block
