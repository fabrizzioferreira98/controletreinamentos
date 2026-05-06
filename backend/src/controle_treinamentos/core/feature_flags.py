"""Feature flags scaffolding.

Simple env-var-based feature flags. Upgrade to LaunchDarkly/Unleash
when the team grows.
"""
from __future__ import annotations

import os

_DEFAULTS: dict[str, bool] = {
    "FEATURE_MULTI_TENANCY": False,
    "FEATURE_PUBLIC_API": False,
    "FEATURE_BILLING": False,
    "FEATURE_CANARY_DEPLOY": False,
}


def is_enabled(flag_name: str) -> bool:
    """Check if a feature flag is enabled via environment variable."""
    env_key = flag_name if flag_name.startswith("FEATURE_") else f"FEATURE_{flag_name}"
    raw = (os.getenv(env_key, "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return _DEFAULTS.get(env_key, False)
    return _DEFAULTS.get(env_key, False)
