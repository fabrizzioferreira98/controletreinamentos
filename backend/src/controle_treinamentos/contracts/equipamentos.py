from __future__ import annotations

FINANCE_CATEGORIA_OPTIONS = ("a", "b", "turbohelice_palmas", "nao_aplicavel")

FINANCE_CATEGORIA_LABELS = {
    "a": "Categoria A",
    "b": "Categoria B",
    "turbohelice_palmas": "Turbo-helice Palmas",
    "nao_aplicavel": "Nao aplicavel",
}


def _as_bool(value) -> bool:
    return str(value).strip().lower() not in {"", "0", "false", "none", "null"}


def normalize_finance_categoria(value) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def validate_finance_categoria(value) -> str | None:
    normalized = normalize_finance_categoria(value)
    if normalized is not None and normalized not in FINANCE_CATEGORIA_OPTIONS:
        allowed = ", ".join(FINANCE_CATEGORIA_OPTIONS)
        raise ValueError(f"Categoria financeira invalida. Use um destes valores: {allowed}.")
    return normalized


def serialize_equipamento_option(row: dict) -> dict:
    equipamento_id = int(row["id"])
    nome = row.get("nome") or ""
    tipo = row.get("tipo") or ""
    ativo = _as_bool(row.get("ativo"))
    categoria_financeira = normalize_finance_categoria(row.get("categoria_financeira"))
    label = " / ".join(item for item in (nome, tipo) if item).strip() or f"Equipamento {equipamento_id}"
    return {
        "id": equipamento_id,
        "value": equipamento_id,
        "label": label,
        "nome": nome,
        "tipo": tipo,
        "status": "ativo" if ativo else "inativo",
        "ativo": ativo,
        "categoria_financeira": categoria_financeira,
        "raw": {
            "id": equipamento_id,
            "nome": nome,
            "tipo": tipo,
            "ativo": ativo,
            "categoria_financeira": categoria_financeira,
        },
    }


def serialize_equipamento_options(rows: list[dict]) -> list[dict]:
    return [serialize_equipamento_option(row) for row in rows]
