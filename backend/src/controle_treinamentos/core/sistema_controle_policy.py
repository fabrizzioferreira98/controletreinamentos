from __future__ import annotations

"""Residual policy for sistema_controle.

This table survives only for controlled residual uses:
- notification execution timestamps/errors
- legacy cache rows under the cache: prefix

It is not an open surface for new generic state, control flags, or
operational ownership.
"""

SISTEMA_CONTROLE_CACHE_PREFIX = "cache:"
SISTEMA_CONTROLE_NOTIFICATION_KEYS = (
    "notification_last_run",
    "notification_last_sent_at",
    "notification_last_error",
)
SISTEMA_CONTROLE_ALLOWED_EXACT_KEYS = frozenset(SISTEMA_CONTROLE_NOTIFICATION_KEYS)
SISTEMA_CONTROLE_RESIDUAL_POLICY = {
    "surface": "sistema_controle",
    "status": "generic_residual_frozen",
    "allowed_roles": ("notification_compat", "legacy_cache"),
    "new_generic_state": "forbidden",
    "hot_path": "out_of_hot_path",
    "death_condition": (
        "mover notification_last_* para owner especifico de notificacoes, aposentar cache:* persistido "
        "e provar ausencia de novos usos genericos em hygiene/testes"
    ),
}


def classify_sistema_controle_key(key: str | None) -> str:
    raw = str(key or "").strip()
    if not raw:
        return "missing"
    if raw.startswith(SISTEMA_CONTROLE_CACHE_PREFIX):
        return "legacy_cache"
    if raw in SISTEMA_CONTROLE_ALLOWED_EXACT_KEYS:
        return "notification_compat"
    return "forbidden"


def is_sistema_controle_key_allowed(key: str | None) -> bool:
    return classify_sistema_controle_key(key) in {"legacy_cache", "notification_compat"}


def assert_sistema_controle_key_allowed(key: str | None) -> str:
    kind = classify_sistema_controle_key(key)
    if kind not in {"legacy_cache", "notification_compat"}:
        raise ValueError(
            "sistema_controle e trilha residual fechada; novo uso generico nao e permitido."
        )
    return kind


def sistema_controle_residual_policy() -> dict:
    return {
        **SISTEMA_CONTROLE_RESIDUAL_POLICY,
        "allowed_exact_keys": tuple(sorted(SISTEMA_CONTROLE_ALLOWED_EXACT_KEYS)),
        "allowed_prefixes": (SISTEMA_CONTROLE_CACHE_PREFIX,),
    }
