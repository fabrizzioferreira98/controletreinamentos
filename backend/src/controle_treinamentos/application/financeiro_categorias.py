from __future__ import annotations

CANONICAL_CATEGORY_A = "categoria a"
CANONICAL_CATEGORY_B = "categoria b"
CANONICAL_CATEGORY_TURBOHELICE_PALMAS = "turbohelice_palmas"


def normalizar_categoria_parametro(value) -> str:
    """Normaliza categoria persistida sem promover abreviacoes legadas a canonicas."""
    return str(value or "").strip().lower()


def normalizar_categoria_operacional(value) -> str:
    """Aceita entrada operacional legada e resolve para a categoria financeira canonica."""
    raw = str(value or "").strip().lower()
    normalized = raw.replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    if normalized in {"a", CANONICAL_CATEGORY_A}:
        return CANONICAL_CATEGORY_A
    if normalized in {"b", CANONICAL_CATEGORY_B}:
        return CANONICAL_CATEGORY_B
    if raw in {"turbohelice_palmas", "turbohelice-palmas"} or normalized in {
        "turbohelice palmas",
        "turbo helice palmas",
        "turbohélice palmas",
    }:
        return CANONICAL_CATEGORY_TURBOHELICE_PALMAS
    return normalized or ""
