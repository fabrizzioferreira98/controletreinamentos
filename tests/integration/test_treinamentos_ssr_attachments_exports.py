from __future__ import annotations

import io
import json
from datetime import date
from typing import Any

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.cadastros import routes_treinamentos
from backend.src.controle_treinamentos.core.domain_errors import (
    DomainConflictError,
    DomainNotFoundError,
    DomainValidationError,
)


class _SingleCursor:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _SingleUserDB:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> _SingleCursor:
        return _SingleCursor(self._row)


def _auth_user_row() -> dict[str, Any]:
    return {
        "id": 1,
        "login": "treinamentos_ssr_files",
        "email": "admin@example.com",
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
        "nome": "Admin",
        "perfil": "admin",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(
            [
                "treinamentos:view",
                "treinamentos:create",
                "treinamentos:edit",
                "treinamentos:delete",
                "treinamentos_anexos:view",
                "treinamentos_anexos:create",
                "treinamentos_anexos:delete",
                "relatorio_habilitacoes:view",
            ]
        ),
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    user_db = _SingleUserDB(_auth_user_row())
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: user_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: user_db)

    with app.test_client() as flask_client:
        csrf_response = flask_client.get("/api/v1/session")
        csrf_token = csrf_response.get_json()["csrf_token"]
        login_response = flask_client.post(
            "/api/v1/session/login",
            json={"login": "treinamentos_ssr_files", "senha": "secret"},
            headers={"X-CSRFToken": csrf_token},
            follow_redirects=False,
        )
        assert login_response.status_code == 200
        yield flask_client


@pytest.fixture(autouse=True)
def disable_frontend_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_treinamentos, "frontend_compat_enabled", lambda: False)
    monkeypatch.setattr(routes_treinamentos, "business_today", lambda: date(2026, 4, 25))


@pytest.fixture
def captured_templates(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    captured: list[tuple[str, dict[str, Any]]] = []

    def _render_template(template_name: str, **context: Any) -> str:
        captured.append((template_name, context))
        return f"rendered:{template_name}"

    monkeypatch.setattr(routes_treinamentos, "render_template", _render_template)
    return captured


def _flashes(client) -> list[tuple[str, str]]:
    with client.session_transaction() as session:
        return list(session.get("_flashes", []))


def _assert_redirects_to(response, expected_path: str) -> None:
    assert response.status_code == 302
    assert response.headers["Location"].endswith(expected_path)


def _assert_flash_contains(client, category: str, expected_substring: str) -> None:
    assert any(cat == category and expected_substring in message for cat, message in _flashes(client))


def _report_payload(*, grouped: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "summary": {
            "total_tripulantes": 1,
            "total_habilitacoes": 1,
            "vencidas": 0,
            "a_vencer": 0,
            "regulares": 1,
            "sem_informacao": 0,
        },
        "tripulantes_grouped": grouped if grouped is not None else [{"tripulante_id": 7, "habilitacoes": []}],
        "filtros_aplicados": {
            "nome": "-",
            "base": "SSA",
            "status": "vencido",
            "tipo": "-",
            "ordenacao": "vencimento",
        },
        "emitted_at": "02/04/2026 12:00",
    }


def _upload_form_data() -> dict[str, tuple[io.BytesIO, str]]:
    return {"arquivo_pdf": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "anexo.pdf")}


def test_treinamentos_consolidado_get_preserves_template_context_and_filters(
    client,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: dict[str, Any] = {}

    def _get_report(_db, **kwargs: Any) -> dict[str, Any]:
        captured_request.update(kwargs)
        return {"report_id": "html"}

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", _get_report)
    monkeypatch.setattr(
        routes_treinamentos,
        "habilitacoes_report_to_html_context",
        lambda report: {"source": report["report_id"], "summary": {"total_tripulantes": 9}},
    )

    response = client.get("/treinamentos/consolidado?nome=Ana&base=SSA&status=vencido&tipo=IFR&ordenacao=vencimento")

    assert response.status_code == 200
    assert captured_templates[-1][0] == "treinamentos_consolidado.html"
    assert captured_templates[-1][1]["source"] == "html"
    assert captured_templates[-1][1]["summary"]["total_tripulantes"] == 9
    assert captured_request == {
        "nome": "Ana",
        "base": "SSA",
        "status": "vencido",
        "tipo": "IFR",
        "ordenacao": "vencimento",
    }


def test_treinamentos_consolidado_invalid_filters_preserve_passthrough_behavior(
    client,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: dict[str, Any] = {}

    def _get_report(_db, **kwargs: Any) -> dict[str, Any]:
        captured_request.update(kwargs)
        return {"report_id": "invalid"}

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", _get_report)
    monkeypatch.setattr(
        routes_treinamentos,
        "habilitacoes_report_to_html_context",
        lambda _report: {"summary": {"total_tripulantes": 0}},
    )

    response = client.get("/treinamentos/consolidado?nome=*&base=???&status=INVALIDO&tipo=&ordenacao=DROP")

    assert response.status_code == 200
    assert captured_templates[-1][0] == "treinamentos_consolidado.html"
    assert captured_request["base"] == "???"
    assert captured_request["status"] == "INVALIDO"
    assert captured_request["ordenacao"] == "DROP"


def test_treinamentos_consolidado_relatorio_preserves_template_and_context(
    client,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", lambda _db, **kwargs: {"filters": kwargs})
    monkeypatch.setattr(
        routes_treinamentos,
        "habilitacoes_report_to_print_context",
        lambda report: {"filtros_aplicados": report["filters"], "emitted_at": "02/04/2026 12:00"},
    )

    response = client.get("/treinamentos/consolidado/relatorio?base=SSA&status=vencido&ordenacao=vencimento")

    assert response.status_code == 200
    assert captured_templates[-1][0] == "treinamentos_consolidado_relatorio.html"
    assert captured_templates[-1][1]["filtros_aplicados"]["base"] == "SSA"
    assert captured_templates[-1][1]["filtros_aplicados"]["status"] == "vencido"


def test_treinamentos_consolidado_export_pdf_preserves_status_content_type_and_filename(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", lambda _db, **kwargs: {"filters": kwargs})
    monkeypatch.setattr(routes_treinamentos, "habilitacoes_report_to_export_payload", lambda _report: _report_payload())
    monkeypatch.setattr(routes_treinamentos, "build_habilitacoes_consolidado_pdf", lambda **kwargs: b"%PDF-habilitacoes\n%%EOF")
    monkeypatch.setattr(routes_treinamentos, "audit_document_generation", lambda **kwargs: audit_calls.append(kwargs))

    response = client.get("/treinamentos/consolidado/export.pdf?base=SSA&status=vencido&ordenacao=vencimento")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-habilitacoes\n%%EOF"
    content_disposition = response.headers.get("Content-Disposition", "")
    assert content_disposition.startswith("attachment; filename=consolidado_habilitacoes_")
    assert content_disposition.endswith(".pdf")
    assert response.headers["X-Document-Policy"] == "habilitacoes_export_pdf"
    assert response.headers["X-Document-Kind"] == "pdf_export"
    assert audit_calls and audit_calls[-1]["commit"] is True


def test_treinamentos_consolidado_export_pdf_without_rows_preserves_current_success_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", lambda _db, **kwargs: {"filters": kwargs})
    monkeypatch.setattr(
        routes_treinamentos,
        "habilitacoes_report_to_export_payload",
        lambda _report: _report_payload(grouped=[]),
    )
    monkeypatch.setattr(routes_treinamentos, "build_habilitacoes_consolidado_pdf", lambda **kwargs: b"%PDF-empty\n%%EOF")
    monkeypatch.setattr(routes_treinamentos, "audit_document_generation", lambda **kwargs: None)

    response = client.get("/treinamentos/consolidado/export.pdf?base=SSA")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-empty\n%%EOF"


def test_treinamentos_consolidado_export_csv_preserves_status_content_type_and_filename(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_calls: list[dict[str, Any]] = []
    captured_request: dict[str, Any] = {}

    def _get_report(_db, **kwargs: Any) -> dict[str, Any]:
        captured_request.update(kwargs)
        return {"report_id": "csv"}

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", _get_report)
    monkeypatch.setattr(
        routes_treinamentos,
        "habilitacoes_report_to_csv_export",
        lambda _report: {
            "content": "\ufeffTripulante;Status\nAna;Regular\n",
            "content_type": "text/csv; charset=utf-8",
        },
    )
    monkeypatch.setattr(routes_treinamentos, "habilitacoes_report_to_export_payload", lambda _report: _report_payload())
    monkeypatch.setattr(routes_treinamentos, "audit_document_generation", lambda **kwargs: audit_calls.append(kwargs))

    response = client.get("/treinamentos/consolidado/export.csv?base=SSA&status=vencido&ordenacao=vencimento")

    assert response.status_code == 200
    assert response.content_type == "text/csv; charset=utf-8"
    assert "Tripulante;Status" in response.get_data(as_text=True)
    content_disposition = response.headers.get("Content-Disposition", "")
    assert content_disposition.startswith("attachment; filename=consolidado_habilitacoes_")
    assert content_disposition.endswith(".csv")
    assert captured_request["base"] == "SSA"
    assert captured_request["status"] == "vencido"
    assert captured_request["ordenacao"] == "vencimento"
    assert audit_calls and audit_calls[-1]["commit"] is True


def test_treinamentos_consolidado_export_csv_without_rows_preserves_current_success_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", lambda _db, **kwargs: {"report_id": "csv-empty"})
    monkeypatch.setattr(
        routes_treinamentos,
        "habilitacoes_report_to_csv_export",
        lambda _report: {
            "content": "\ufeffTripulante;Status\n",
            "content_type": "text/csv; charset=utf-8",
        },
    )
    monkeypatch.setattr(routes_treinamentos, "habilitacoes_report_to_export_payload", lambda _report: _report_payload(grouped=[]))
    monkeypatch.setattr(routes_treinamentos, "audit_document_generation", lambda **kwargs: None)

    response = client.get("/treinamentos/consolidado/export.csv")

    assert response.status_code == 200
    assert response.content_type == "text/csv; charset=utf-8"
    assert "Tripulante;Status" in response.get_data(as_text=True)


def test_treinamentos_attachment_upload_valid_preserves_redirect_flash_and_application_call(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def _upload(payload: dict[str, Any], *, treinamento_id: int, enviado_por: int) -> dict[str, Any]:
        calls.append({"payload": payload, "treinamento_id": treinamento_id, "enviado_por": enviado_por})
        return {"id": 88}

    monkeypatch.setattr(routes_treinamentos, "upload_treinamento_attachment", _upload)

    response = client.post(
        "/treinamentos/55/anexos/upload",
        data=_upload_form_data(),
        content_type="multipart/form-data",
    )

    _assert_redirects_to(response, "/treinamentos/55/editar")
    assert calls and calls[-1]["treinamento_id"] == 55
    assert calls[-1]["enviado_por"] == 1
    assert calls[-1]["payload"]["filename"] == "anexo.pdf"
    assert calls[-1]["payload"]["arquivo_bytes"].startswith(b"%PDF")
    _assert_flash_contains(client, "success", "PDF anexado com sucesso.")


def test_treinamentos_attachment_upload_invalid_preserves_error_flash_and_redirect(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _upload(payload: dict[str, Any], *, treinamento_id: int, enviado_por: int) -> dict[str, Any]:
        raise DomainValidationError("Arquivo PDF invalido.")

    monkeypatch.setattr(routes_treinamentos, "upload_treinamento_attachment", _upload)

    response = client.post(
        "/treinamentos/55/anexos/upload",
        data=_upload_form_data(),
        content_type="multipart/form-data",
    )

    _assert_redirects_to(response, "/treinamentos/55/editar")
    _assert_flash_contains(client, "error", "Arquivo PDF invalido.")


def test_treinamentos_attachment_upload_missing_file_preserves_error_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _upload(payload: dict[str, Any], *, treinamento_id: int, enviado_por: int) -> dict[str, Any]:
        assert payload["filename"] == ""
        assert payload["arquivo_bytes"] == b""
        raise DomainValidationError("Selecione um arquivo PDF para enviar.")

    monkeypatch.setattr(routes_treinamentos, "upload_treinamento_attachment", _upload)

    response = client.post(
        "/treinamentos/55/anexos/upload",
        data={},
        content_type="multipart/form-data",
    )

    _assert_redirects_to(response, "/treinamentos/55/editar")
    _assert_flash_contains(client, "error", "Selecione um arquivo PDF")


def test_treinamentos_attachment_upload_missing_training_preserves_not_found_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _upload(payload: dict[str, Any], *, treinamento_id: int, enviado_por: int) -> dict[str, Any]:
        raise DomainNotFoundError("Treinamento nao encontrado.")

    monkeypatch.setattr(routes_treinamentos, "upload_treinamento_attachment", _upload)

    response = client.post(
        "/treinamentos/404/anexos/upload",
        data=_upload_form_data(),
        content_type="multipart/form-data",
    )

    _assert_redirects_to(response, "/dashboard")
    _assert_flash_contains(client, "error", "Recurso")


def test_treinamentos_attachment_get_preview_preserves_headers_and_content(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        routes_treinamentos,
        "get_treinamento_attachment",
        lambda **kwargs: {
            "nome_original": "anexo.pdf",
            "mime_type": "application/pdf",
            "payload_bytes": b"%PDF-1.4\n%%EOF",
        },
    )
    monkeypatch.setattr(routes_treinamentos, "audit_relevant_download", lambda **kwargs: download_calls.append(kwargs))

    response = client.get("/treinamentos/55/anexos/77")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data().startswith(b"%PDF")
    assert response.headers["Content-Disposition"] == "inline; filename=anexo.pdf"
    assert response.headers["X-File-Access-Action"] == "preview"
    assert download_calls and download_calls[-1]["action"] == "preview"
    assert download_calls[-1]["commit"] is True


def test_treinamentos_attachment_get_download_mode_preserves_attachment_disposition(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_treinamentos,
        "get_treinamento_attachment",
        lambda **kwargs: {
            "nome_original": "anexo.pdf",
            "mime_type": "application/pdf",
            "payload_bytes": b"%PDF-1.4\n%%EOF",
        },
    )
    monkeypatch.setattr(routes_treinamentos, "audit_relevant_download", lambda **kwargs: None)

    response = client.get("/treinamentos/55/anexos/77?download=1")

    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == "attachment; filename=anexo.pdf"
    assert response.headers["X-File-Access-Action"] == "download"


def test_treinamentos_attachment_get_missing_preserves_not_found_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing_attachment(**kwargs: Any):
        raise DomainNotFoundError("Anexo nao encontrado.")

    monkeypatch.setattr(routes_treinamentos, "get_treinamento_attachment", _missing_attachment)

    response = client.get("/treinamentos/55/anexos/999")

    _assert_redirects_to(response, "/dashboard")
    _assert_flash_contains(client, "error", "Recurso")


def test_treinamentos_attachment_delete_existing_preserves_redirect_flash_and_application_call(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def _delete_attachment(*, treinamento_id: int, anexo_id: int) -> dict[str, Any]:
        calls.append((treinamento_id, anexo_id))
        return {"id": anexo_id}

    monkeypatch.setattr(routes_treinamentos, "delete_treinamento_attachment", _delete_attachment)

    response = client.post("/treinamentos/55/anexos/77/excluir")

    _assert_redirects_to(response, "/treinamentos/55/editar")
    assert calls == [(55, 77)]
    _assert_flash_contains(client, "success", "Anexo removido com sucesso.")


def test_treinamentos_attachment_delete_missing_preserves_not_found_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _delete_attachment(*, treinamento_id: int, anexo_id: int) -> dict[str, Any]:
        raise DomainNotFoundError("Anexo nao encontrado.")

    monkeypatch.setattr(routes_treinamentos, "delete_treinamento_attachment", _delete_attachment)

    response = client.post("/treinamentos/55/anexos/999/excluir")

    _assert_redirects_to(response, "/dashboard")
    _assert_flash_contains(client, "error", "Recurso")


def test_treinamentos_attachment_delete_conflict_preserves_error_flash_and_redirect(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _delete_attachment(*, treinamento_id: int, anexo_id: int) -> dict[str, Any]:
        raise DomainConflictError("Anexo vinculado a registro protegido.")

    monkeypatch.setattr(routes_treinamentos, "delete_treinamento_attachment", _delete_attachment)

    response = client.post("/treinamentos/55/anexos/77/excluir")

    _assert_redirects_to(response, "/treinamentos/55/editar")
    _assert_flash_contains(client, "error", "Anexo vinculado")
