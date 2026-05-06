from __future__ import annotations


def normalize_tipo_documento(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    if not value:
        return "geral"
    return value.lower()


def status_label(status_value: str | None) -> str:
    value = (status_value or "").strip().lower()
    labels = {
        "ativo": "Ativo",
        "substituido": "Substituído",
        "removido": "Removido",
    }
    return labels.get(value, "Desconhecido")

