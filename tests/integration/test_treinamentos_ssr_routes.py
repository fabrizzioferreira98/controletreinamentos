from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.application import treinamentos_ssr
from backend.src.controle_treinamentos.blueprints.cadastros import routes_treinamentos
from backend.src.controle_treinamentos.core.domain_errors import (
    DomainConflictError,
    DomainNotFoundError,
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


class _TreinamentosDB:
    def __init__(self, *, missing_ids: set[int] | None = None) -> None:
        self.missing_ids = missing_ids or set()
        self.queries: list[str] = []
        self.params: list[tuple[Any, ...] | list[Any] | None] = []

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> _SingleCursor:
        normalized = " ".join(str(query).split())
        self.queries.append(normalized)
        self.params.append(params)

        lowered = normalized.lower()
        if "count(*) as total" in lowered and "from treinamentos" in lowered:
            return _SingleCursor(
                {
                    "total": 42,
                    "sem_informacao": 3,
                    "vencido": 5,
                    "a_vencer": 7,
                    "regular": 27,
                }
            )

        if "select * from treinamentos where id" in lowered:
            treinamento_id = int((params or [0])[0])
            if treinamento_id in self.missing_ids:
                return _SingleCursor(None)
            return _SingleCursor(
                {
                    "id": treinamento_id,
                    "tripulante_id": 7,
                    "equipamento_id": 3,
                    "tipo_treinamento_id": 2,
                    "data_realizacao": "2026-04-01",
                    "data_vencimento": "2027-04-01",
                    "observacoes": "Treinamento regular",
                }
            )

        raise AssertionError(f"Unexpected SQL in treinamentos SSR test: {normalized}")


def _auth_user_row() -> dict[str, Any]:
    return {
        "id": 1,
        "login": "treinamentos_ssr",
        "email": "admin@example.com",
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
        "nome": "Admin",
        "perfil": "admin",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(
            ["treinamentos:view", "treinamentos:create", "treinamentos:edit", "treinamentos:delete"]
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
            json={"login": "treinamentos_ssr", "senha": "secret"},
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
def fake_db(monkeypatch: pytest.MonkeyPatch) -> _TreinamentosDB:
    db = _TreinamentosDB()
    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: db)
    monkeypatch.setattr(treinamentos_ssr, "get_db", lambda: db)
    return db


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


def _training_options() -> dict[str, Any]:
    return {
        "attachments": [{"id": 9, "filename": "certificado.pdf"}],
        "max_bytes": 8 * 1024 * 1024,
        "tripulantes": [{"id": 7, "nome": "Ana Silva"}],
        "equipamentos": [{"id": 3, "nome": "A320"}],
        "tipos": [{"id": 2, "nome": "Inicial"}],
    }


def _valid_form() -> dict[str, str]:
    return {
        "tripulante_id": "7",
        "equipamento_id": "3",
        "tipo_treinamento_id": "2",
        "data_realizacao": "2026-04-01",
        "data_vencimento": "2027-04-01",
        "observacoes": "Treinamento regular",
    }


def _patch_filter_options(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fetch_cached_rows(db: Any, cache_key: str, query: str):
        if cache_key == "options:tripulantes:id_nome":
            return [{"id": 7, "nome": "Ana Silva"}]
        if cache_key == "options:equipamentos:id_nome":
            return [{"id": 3, "nome": "A320"}]
        if cache_key == "options:tipos_treinamento:id_nome":
            return [{"id": 2, "nome": "Inicial"}]
        raise AssertionError(f"Unexpected cached option key: {cache_key}")

    monkeypatch.setattr(treinamentos_ssr, "fetch_cached_rows", _fetch_cached_rows)


def _patch_form_options(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _get_training_form_options(db: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _training_options()

    monkeypatch.setattr(routes_treinamentos, "get_training_form_options", _get_training_form_options)
    monkeypatch.setattr(treinamentos_ssr, "get_training_form_options", _get_training_form_options)
    return calls


def test_treinamentos_list_preserves_template_filters_summary_and_pagination(
    client,
    fake_db: _TreinamentosDB,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_filter_options(monkeypatch)
    page_calls: list[dict[str, Any]] = []

    def _fetch_training_page(
        db: Any,
        where_clause: str,
        params: tuple[Any, ...],
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        page_calls.append(
            {
                "where_clause": where_clause,
                "params": params,
                "limit": limit,
                "offset": offset,
            }
        )
        return [{"id": 91, "tripulante_nome": "Ana Silva", "equipamento_nome": "A320"}]

    monkeypatch.setattr(treinamentos_ssr, "list_treinamentos_ssr_page", _fetch_training_page)

    response = client.get(
        "/treinamentos?tripulante=7&equipamento=3&tipo=2&status=regular&periodo=30&page=2"
    )

    assert response.status_code == 200
    assert captured_templates[-1][0] == "treinamentos_list.html"
    context = captured_templates[-1][1]
    assert context["treinamentos"] == [
        {"id": 91, "tripulante_nome": "Ana Silva", "equipamento_nome": "A320"}
    ]
    assert context["resumo"] == {
        "total": 42,
        "vencido": 5,
        "a vencer": 7,
        "regular": 27,
        "sem informação": 3,
    }
    assert context["filtros"] == {
        "tripulante": "7",
        "equipamento": "3",
        "tipo": "2",
        "status": "regular",
        "periodo": "30",
    }
    assert context["tripulantes"] == [{"id": 7, "nome": "Ana Silva"}]
    assert context["equipamentos"] == [{"id": 3, "nome": "A320"}]
    assert context["tipos"] == [{"id": 2, "nome": "Inicial"}]
    assert context["pagination"]["page"] == 2

    assert page_calls
    page_call = page_calls[-1]
    assert page_call["limit"] == context["pagination"]["per_page"]
    assert page_call["offset"] == (context["pagination"]["page"] - 1) * context["pagination"]["per_page"]
    assert "c.id = %s" in page_call["where_clause"]
    assert "e.id = %s" in page_call["where_clause"]
    assert "tt.id = %s" in page_call["where_clause"]
    assert "t.data_vencimento > %s" in page_call["where_clause"]
    assert "t.data_vencimento BETWEEN %s AND %s" in page_call["where_clause"]
    assert 7 in page_call["params"]
    assert 3 in page_call["params"]
    assert 2 in page_call["params"]

    assert any("COUNT(*) AS total" in query for query in fake_db.queries)


def test_treinamentos_list_invalid_numeric_filters_preserve_flash_and_fallback(
    client,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_filter_options(monkeypatch)

    db = _TreinamentosDB()
    monkeypatch.setattr(treinamentos_ssr, "get_db", lambda: db)
    monkeypatch.setattr(treinamentos_ssr, "list_treinamentos_ssr_page", lambda *args, **kwargs: [])

    response = client.get("/treinamentos?tripulante=abc&equipamento=x&tipo=y")

    assert response.status_code == 200
    context = captured_templates[-1][1]
    assert context["filtros"]["tripulante"] == ""
    assert context["filtros"]["equipamento"] == ""
    assert context["filtros"]["tipo"] == ""
    assert ("error", "Filtro de tripulante inválido.") in _flashes(client)
    assert ("error", "Filtro de equipamento inválido.") in _flashes(client)
    assert ("error", "Filtro de tipo inválido.") in _flashes(client)


def test_treinamentos_new_get_preserves_form_template_and_options(
    client,
    fake_db: _TreinamentosDB,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_form_options(monkeypatch)

    response = client.get("/treinamentos/novo")

    assert response.status_code == 200
    assert captured_templates[-1][0] == "treinamentos_form.html"
    context = captured_templates[-1][1]
    assert context["treinamento"] is None
    assert context["attachments"] == [{"id": 9, "filename": "certificado.pdf"}]
    assert context["attachment_max_mb"] == routes_treinamentos.TRAINING_ATTACHMENT_MAX_MB
    assert context["tripulantes"] == [{"id": 7, "nome": "Ana Silva"}]
    assert context["equipamentos"] == [{"id": 3, "nome": "A320"}]
    assert context["tipos"] == [{"id": 2, "nome": "Inicial"}]


def test_treinamentos_new_post_valid_preserves_redirect_flash_and_application_call(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def _save_treinamento(form_data: Any, *, treinamento_id: int | None = None) -> dict[str, Any]:
        calls.append({"form_data": form_data, "treinamento_id": treinamento_id})
        return {"operation": "created"}

    monkeypatch.setattr(routes_treinamentos, "save_treinamento", _save_treinamento)

    response = client.post("/treinamentos/novo", data=_valid_form())

    _assert_redirects_to(response, "/treinamentos")
    assert calls and calls[-1]["treinamento_id"] is None
    assert calls[-1]["form_data"]["tripulante_id"] == "7"
    assert ("success", "Treinamento cadastrado com sucesso.") in _flashes(client)


def test_treinamentos_new_post_invalid_preserves_form_status_flash_and_state(
    client,
    fake_db: _TreinamentosDB,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_form_options(monkeypatch)

    def _save_treinamento(form_data: Any, *, treinamento_id: int | None = None) -> dict[str, Any]:
        raise DomainConflictError("Treinamento duplicado.")

    monkeypatch.setattr(routes_treinamentos, "save_treinamento", _save_treinamento)

    response = client.post("/treinamentos/novo", data=_valid_form())

    assert response.status_code == 400
    assert captured_templates[-1][0] == "treinamentos_form.html"
    context = captured_templates[-1][1]
    assert context["treinamento"]["tripulante_id"] == "7"
    assert context["treinamento"]["equipamento_id"] == "3"
    assert context["treinamento"]["tipo_treinamento_id"] == "2"
    assert ("error", "Treinamento duplicado.") in _flashes(client)


def test_treinamentos_edit_get_existing_preserves_form_context_and_options(
    client,
    fake_db: _TreinamentosDB,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    option_calls = _patch_form_options(monkeypatch)

    response = client.get("/treinamentos/55/editar")

    assert response.status_code == 200
    assert captured_templates[-1][0] == "treinamentos_form.html"
    context = captured_templates[-1][1]
    assert context["treinamento"]["id"] == 55
    assert context["treinamento"]["tripulante_id"] == 7
    assert option_calls[-1] == {
        "treinamento_id": 55,
        "selected_equipment_id": 3,
        "selected_tipo_id": 2,
    }
    assert any("SELECT * FROM treinamentos WHERE id = %s" in query for query in fake_db.queries)


def test_treinamentos_edit_get_missing_preserves_not_found_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(treinamentos_ssr, "get_db", lambda: _TreinamentosDB(missing_ids={404}))
    _patch_form_options(monkeypatch)

    response = client.get("/treinamentos/404/editar")

    _assert_redirects_to(response, "/dashboard")
    assert ("error", "Recurso não encontrado.") in _flashes(client)


def test_treinamentos_edit_post_valid_preserves_redirect_flash_and_application_call(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def _save_treinamento(form_data: Any, *, treinamento_id: int | None = None) -> dict[str, Any]:
        calls.append({"form_data": form_data, "treinamento_id": treinamento_id})
        return {"operation": "updated"}

    monkeypatch.setattr(routes_treinamentos, "save_treinamento", _save_treinamento)

    response = client.post("/treinamentos/55/editar", data=_valid_form())

    _assert_redirects_to(response, "/treinamentos")
    assert calls and calls[-1]["treinamento_id"] == 55
    assert calls[-1]["form_data"]["tripulante_id"] == "7"
    assert ("success", "Treinamento atualizado com sucesso.") in _flashes(client)


def test_treinamentos_edit_post_invalid_preserves_form_status_flash_and_state(
    client,
    fake_db: _TreinamentosDB,
    captured_templates: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    option_calls = _patch_form_options(monkeypatch)

    def _save_treinamento(form_data: Any, *, treinamento_id: int | None = None) -> dict[str, Any]:
        raise DomainConflictError("Treinamento duplicado.")

    monkeypatch.setattr(routes_treinamentos, "save_treinamento", _save_treinamento)

    response = client.post("/treinamentos/55/editar", data=_valid_form())

    assert response.status_code == 400
    assert captured_templates[-1][0] == "treinamentos_form.html"
    context = captured_templates[-1][1]
    assert context["treinamento"]["tripulante_id"] == "7"
    assert option_calls[-1]["treinamento_id"] == 55
    assert ("error", "Treinamento duplicado.") in _flashes(client)


def test_treinamentos_delete_success_preserves_redirect_flash_and_application_call(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def _delete_treinamento(*, treinamento_id: int) -> None:
        calls.append(treinamento_id)

    monkeypatch.setattr(routes_treinamentos, "delete_treinamento", _delete_treinamento)

    response = client.post("/treinamentos/55/excluir")

    _assert_redirects_to(response, "/treinamentos")
    assert calls == [55]
    assert ("success", "Treinamento excluido com sucesso.") in _flashes(client)


def test_treinamentos_delete_domain_error_preserves_flash_and_redirect(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _delete_treinamento(*, treinamento_id: int) -> None:
        raise DomainConflictError("Treinamento possui vínculos.")

    monkeypatch.setattr(routes_treinamentos, "delete_treinamento", _delete_treinamento)

    response = client.post("/treinamentos/55/excluir")

    _assert_redirects_to(response, "/treinamentos")
    assert ("error", "Treinamento possui vínculos.") in _flashes(client)


def test_treinamentos_delete_missing_preserves_not_found_behavior(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _delete_treinamento(*, treinamento_id: int) -> None:
        raise DomainNotFoundError("Treinamento não encontrado.")

    monkeypatch.setattr(routes_treinamentos, "delete_treinamento", _delete_treinamento)

    response = client.post("/treinamentos/404/excluir")

    _assert_redirects_to(response, "/dashboard")
    assert ("error", "Recurso não encontrado.") in _flashes(client)
