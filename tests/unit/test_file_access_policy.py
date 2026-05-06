import pytest
from flask import request

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.core.domain_errors import DomainForbiddenError, DomainUnexpectedError
from backend.src.controle_treinamentos.core.file_access_policy import (
    FileAccessPolicy,
    TRIPULANTE_FILE_ACCESS_POLICY,
    build_file_access_response,
    file_access_policy_contract,
    resolve_file_access_action,
)


class StubUser:
    is_authenticated = True
    id = 41

    def __init__(self, permissions):
        self._permissions = set(permissions)

    def has_permission(self, permission: str) -> bool:
        return permission in self._permissions


def test_file_access_policy_contract_declares_actions_and_link_expiration():
    payload = file_access_policy_contract(TRIPULANTE_FILE_ACCESS_POLICY)

    assert payload["preview_permission"] == "tripulantes_file:view"
    assert payload["download_permission"] == "tripulantes_file:view"
    assert payload["replace_permission"] == "tripulantes_file:replace"
    assert payload["delete_permission"] == "tripulantes_file:delete"
    assert payload["link_policy"] == "authenticated-session"
    assert payload["link_expires_after"] == "session"
    assert payload["cache_control"] == "private, no-store"


@pytest.mark.parametrize(
    ("query_string", "expected"),
    [
        ("", "preview"),
        ("download=0", "preview"),
        ("download=1", "download"),
        ("download=true", "download"),
    ],
)
def test_resolve_file_access_action(query_string, expected):
    app = create_app()
    with app.test_request_context("/arquivo?" + query_string):
        assert resolve_file_access_action(request.args) == expected


def test_build_file_access_response_sets_streaming_and_sensitive_headers():
    app = create_app()
    with app.test_request_context("/arquivo"):
        response = build_file_access_response(
            policy=TRIPULANTE_FILE_ACCESS_POLICY,
            action="preview",
            payload_bytes=b"%PDF-1.4\n%%EOF",
            mime_type="application/pdf",
            filename="doc.pdf",
            entity_id=9,
            subject_id=7,
            user=StubUser({"tripulantes_file:view"}),
        )

    assert response.get_data().startswith(b"%PDF")
    assert response.headers["Content-Disposition"] == "inline; filename=doc.pdf"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-File-Access-Action"] == "preview"
    assert response.headers["X-File-Link-Policy"] == "authenticated-session"
    assert response.headers["X-File-Link-Expires"] == "session"


def test_download_permission_is_checked_as_a_separate_action():
    policy = FileAccessPolicy(
        key="custom_file",
        subject="arquivo customizado",
        view_permission="custom:view",
        download_permission="custom:download",
        replace_permission=None,
        delete_permission=None,
    )
    app = create_app()

    with app.test_request_context("/arquivo"):
        preview = build_file_access_response(
            policy=policy,
            action="preview",
            payload_bytes=b"abc",
            mime_type="application/octet-stream",
            filename="a.bin",
            user=StubUser({"custom:view"}),
        )
        with pytest.raises(DomainForbiddenError):
            build_file_access_response(
                policy=policy,
                action="download",
                payload_bytes=b"abc",
                mime_type="application/octet-stream",
                filename="a.bin",
                user=StubUser({"custom:view"}),
            )

    assert preview.headers["Content-Disposition"] == "inline; filename=a.bin"


def test_invalid_binary_payload_is_not_silent():
    app = create_app()
    with app.test_request_context("/arquivo"):
        with pytest.raises(DomainUnexpectedError) as exc_info:
            build_file_access_response(
                policy=TRIPULANTE_FILE_ACCESS_POLICY,
                action="preview",
                payload_bytes=b"",
                mime_type="application/pdf",
                filename="doc.pdf",
                user=StubUser({"tripulantes_file:view"}),
            )

    assert exc_info.value.code == "tripulante_file_empty_binary_payload"
