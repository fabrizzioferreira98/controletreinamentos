import pytest

from backend.src.controle_treinamentos.core.sistema_controle_policy import (
    assert_sistema_controle_key_allowed,
    classify_sistema_controle_key,
    sistema_controle_residual_policy,
)


def test_sistema_controle_policy_allows_only_residual_keys():
    assert classify_sistema_controle_key("notification_last_run") == "notification_compat"
    assert classify_sistema_controle_key("cache:dashboard:v1") == "legacy_cache"


def test_sistema_controle_policy_rejects_new_generic_keys():
    assert classify_sistema_controle_key("worker:last-run") == "forbidden"
    with pytest.raises(ValueError):
        assert_sistema_controle_key_allowed("worker:last-run")


def test_sistema_controle_policy_keeps_notification_and_cache_paths_as_explicit_residuals():
    assert assert_sistema_controle_key_allowed("notification_last_run") == "notification_compat"
    assert assert_sistema_controle_key_allowed("notification_last_sent_at") == "notification_compat"
    assert assert_sistema_controle_key_allowed("notification_last_error") == "notification_compat"
    assert assert_sistema_controle_key_allowed("cache:tripulantes:list:v1") == "legacy_cache"


def test_sistema_controle_policy_has_death_condition_for_generic_residual():
    policy = sistema_controle_residual_policy()

    assert policy["status"] == "generic_residual_frozen"
    assert policy["new_generic_state"] == "forbidden"
    assert policy["hot_path"] == "out_of_hot_path"
    assert "notification_last_run" in policy["allowed_exact_keys"]
    assert "cache:" in policy["allowed_prefixes"]
    assert "provar ausencia de novos usos genericos" in policy["death_condition"]
