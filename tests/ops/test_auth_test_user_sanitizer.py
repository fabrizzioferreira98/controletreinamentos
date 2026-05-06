from ops.scripts.admin.sanitize_test_users import (
    CANONICAL_TEST_USERS,
    build_keep_logins,
    build_sanitization_plan,
    classify_user_record,
    is_test_login,
)


def _row(login: str, *, user_id: int = 1, ativo: int = 1, perfil: str = "operador") -> dict:
    return {
        "id": user_id,
        "login": login,
        "nome": login,
        "email": f"{login}@example.test",
        "perfil": perfil,
        "ativo": ativo,
    }


def test_canonical_test_users_are_minimal_and_role_named():
    assert set(CANONICAL_TEST_USERS) == {"qa_admin", "qa_operador", "qa_inativo", "qa_restrito"}
    assert all(login.startswith("qa_") for login in CANONICAL_TEST_USERS)


def test_canonical_user_is_kept_even_with_references():
    classified = classify_user_record(
        _row("qa_admin", perfil="gestora"),
        reference_count=10,
        keep_logins=build_keep_logins([]),
        allow_delete=True,
    )

    assert classified is not None
    assert classified.classification == "manter"
    assert classified.planned_action == "none"


def test_noncanonical_orphan_test_user_can_be_removed_when_allowed():
    classified = classify_user_record(
        _row("qa_runtime_smoke_operador"),
        reference_count=0,
        keep_logins=build_keep_logins([]),
        allow_delete=True,
    )

    assert classified is not None
    assert classified.classification == "remover"
    assert classified.planned_action == "delete"


def test_referenced_duplicate_role_user_is_consolidated_by_deactivation():
    classified = classify_user_record(
        _row("qa_old_admin"),
        reference_count=3,
        keep_logins=build_keep_logins([]),
        allow_delete=True,
    )

    assert classified is not None
    assert classified.classification == "consolidar"
    assert classified.planned_action == "deactivate"


def test_real_user_login_is_ignored():
    assert is_test_login("maria.silva") is False
    assert (
        classify_user_record(
            _row("maria.silva"),
            reference_count=0,
            keep_logins=build_keep_logins([]),
            allow_delete=True,
        )
        is None
    )


def test_plan_keeps_external_e2e_login_and_filters_real_users():
    rows = [
        _row("qa_admin", user_id=1, perfil="gestora"),
        _row("e2e_release_bot", user_id=2),
        _row("qa_runtime_smoke_gestora", user_id=3),
        _row("maria.silva", user_id=4),
    ]

    plan = build_sanitization_plan(
        rows,
        reference_counts={1: 0, 2: 0, 3: 0, 4: 0},
        keep_logins=build_keep_logins(["e2e_release_bot"]),
        allow_delete=True,
    )

    assert [item.login for item in plan] == ["e2e_release_bot", "qa_admin", "qa_runtime_smoke_gestora"]
    assert {item.login: item.classification for item in plan} == {
        "e2e_release_bot": "manter",
        "qa_admin": "manter",
        "qa_runtime_smoke_gestora": "remover",
    }
