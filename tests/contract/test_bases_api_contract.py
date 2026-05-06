from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.bases import routes as bases_routes
from backend.src.controle_treinamentos.core.domain_errors import DomainValidationError


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _SingleCursor(self._row)


def _auth_user_row():
    return {
        "id": 61,
        "nome": "Gestora Bases",
        "login": "gestora_bases",
        "email": "gestora.bases@local.test",
        "perfil": "gestora",
        "ativo": 1,
        "permissao_modulos_json": "[]",
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch):
    row = _auth_user_row()
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "gestora_bases", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_bases_programmatic_payload_adds_minimum_success_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(bases_routes, "get_panel_cache", lambda _key: None)
    monkeypatch.setattr(bases_routes, "set_panel_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bases_routes,
        "_fetch_bases_payload",
        lambda status_filter=None: {
            "bases": [
                {
                    "id": "1",
                    "nome": "SSA",
                    "uf": "BA",
                    "latitude": "-12.9714",
                    "longitude": "-38.5014",
                    "ativa": 1,
                    "total_pilotos": "1",
                    "counts": {"ativo": "1", "desconhecido": None},
                    "pilotos": [
                        {
                            "id": "77",
                            "nome": "Lucas Silva",
                            "matricula": "AB123",
                            "tripulante_id": None,
                            "base_id": "1",
                            "base_nome": "SSA",
                            "base_uf": "BA",
                            "status": "ativo",
                            "status_label": "Ativo",
                            "status_class": "status-green",
                            "status_raw": "",
                            "possui_foto": False,
                            "foto_url": "",
                            "iniciais": "LS",
                            "expiry_indicator": {
                                "key": "sem_informacao",
                                "label": "Sem informacao",
                                "css_class": "status-gray",
                                "pulse": False,
                                "priority": "0",
                                "days_remaining": "12",
                                "due_date_iso": "2026-04-30",
                                "due_date_label": "",
                            },
                            "criado_em": "01/04/2026 10:00",
                            "criado_em_iso": "2026-04-01T10:00:00",
                            "drag_state": "screen-only",
                        }
                    ],
                    "map_marker_html": "<span>screen</span>",
                }
            ],
            "pilotos": [
                {
                    "id": "77",
                    "nome": "Lucas Silva",
                    "matricula": "AB123",
                    "tripulante_id": None,
                    "base_id": "1",
                    "base_nome": "SSA",
                    "base_uf": "BA",
                    "status": "ativo",
                    "status_label": "Ativo",
                    "status_class": "status-green",
                    "status_raw": "",
                    "possui_foto": False,
                    "foto_url": "",
                    "iniciais": "LS",
                    "expiry_indicator": {"days_remaining": "12", "due_date_iso": "2026-04-30"},
                    "criado_em": "01/04/2026 10:00",
                    "criado_em_iso": "2026-04-01T10:00:00",
                    "drag_state": "screen-only",
                }
            ],
            "status_options": [{"key": "ativo", "label": "Ativo", "class": "status-green", "marker_class": "dot", "html": "<b>screen</b>"}],
            "status_filter": status_filter or "",
            "screen_state": {"zoom": 7},
        },
    )

    response = client.get("/bases/api/dados?status=ativo")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["status"] == 200
    assert payload["code"] == "bases_payload_ok"
    assert payload["status_filter"] == "ativo"
    assert "screen_state" not in payload
    assert "map_marker_html" not in payload["bases"][0]
    assert "drag_state" not in payload["bases"][0]["pilotos"][0]
    assert payload["bases"][0]["id"] == 1
    assert isinstance(payload["bases"][0]["latitude"], float)
    assert payload["bases"][0]["counts"]["ativo"] == 1
    assert payload["bases"][0]["counts"]["desconhecido"] == 0
    assert payload["bases"][0]["pilotos"][0]["id"] == 77
    assert payload["bases"][0]["pilotos"][0]["tripulante_id"] is None
    assert payload["bases"][0]["pilotos"][0]["status_raw"] is None
    assert payload["bases"][0]["pilotos"][0]["expiry_indicator"]["days_remaining"] == 12
    assert payload["bases"][0]["pilotos"][0]["expiry_indicator"]["due_date_iso"] == "2026-04-30"
    assert payload["bases"][0]["pilotos"][0]["criado_em_iso"] == "2026-04-01T10:00:00"
    assert payload["status_options"][0] == {
        "key": "ativo",
        "label": "Ativo",
        "class": "status-green",
        "marker_class": "dot",
    }


def test_bases_ssr_initial_payload_uses_formal_programmatic_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}
    monkeypatch.setattr(bases_routes, "get_panel_cache", lambda _key: None)
    monkeypatch.setattr(bases_routes, "set_panel_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bases_routes,
        "_fetch_bases_payload",
        lambda status_filter=None: {
            "bases": [
                {
                    "id": "1",
                    "nome": "SSA",
                    "uf": "BA",
                    "latitude": "-12.9714",
                    "longitude": "-38.5014",
                    "ativa": 1,
                    "total_pilotos": "1",
                    "counts": {"ativo": "1"},
                    "pilotos": [
                        {
                            "id": "77",
                            "nome": "Lucas Silva",
                            "matricula": "AB123",
                            "tripulante_id": None,
                            "base_id": "1",
                            "base_nome": "SSA",
                            "base_uf": "BA",
                            "status": "ativo",
                            "status_label": "Ativo",
                            "status_class": "status-green",
                            "status_raw": "",
                            "possui_foto": False,
                            "foto_url": "",
                            "iniciais": "LS",
                            "expiry_indicator": {"days_remaining": None, "due_date_iso": None},
                            "criado_em": "01/04/2026 10:00",
                            "criado_em_iso": "2026-04-01T10:00:00",
                            "drag_state": "screen-only",
                        }
                    ],
                    "map_marker_html": "<span>screen</span>",
                }
            ],
            "pilotos": [],
            "status_options": [{"key": "ativo", "label": "Ativo", "class": "status-green", "marker_class": "dot"}],
            "status_filter": status_filter or "",
            "screen_state": {"zoom": 7},
        },
    )

    def _render_template(template, **context):
        captured["template"] = template
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(bases_routes, "render_template", _render_template)

    response = client.get("/bases")

    assert response.status_code == 200
    assert captured["template"] == "bases/index.html"
    initial_payload = captured["context"]["initial_payload"]
    assert initial_payload["success"] is True
    assert initial_payload["status"] == 200
    assert initial_payload["code"] == "bases_payload_ok"
    assert "screen_state" not in initial_payload
    assert "map_marker_html" not in initial_payload["bases"][0]
    assert "drag_state" not in initial_payload["bases"][0]["pilotos"][0]
    assert initial_payload["bases"][0]["id"] == 1
    assert isinstance(initial_payload["bases"][0]["latitude"], float)


def test_bases_ssr_sidebar_keeps_financeiro_menu(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(bases_routes, "get_panel_cache", lambda _key: None)
    monkeypatch.setattr(bases_routes, "set_panel_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bases_routes,
        "_fetch_bases_payload",
        lambda status_filter=None: {
            "bases": [],
            "pilotos": [],
            "status_options": [],
            "status_filter": status_filter or "",
        },
    )

    response = client.get("/bases")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Financeiro" in body
    assert 'href="/#/financeiro/missoes"' not in body
    assert 'href="/#/financeiro/bonificacoes"' not in body
    assert 'href="/#/financeiro/lancamentos-jornada"' in body
    assert 'href="/#/financeiro/fechamento-parametros"' in body


def test_bases_programmatic_mutation_success_uses_minimum_envelope(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def _add_pilot(payload, *, actor_user_id):
        captured["payload"] = dict(payload)
        captured["actor_user_id"] = actor_user_id
        return {"message": "Piloto adicionado.", "pilot_id": "77"}

    monkeypatch.setattr(
        bases_routes,
        "add_pilot_to_base",
        _add_pilot,
    )

    response = client.post(
        "/bases/pilotos/adicionar",
        data={
            "nome": "Lucas Silva",
            "matricula": "ab123",
            "status": "ativo",
            "base_id": "1",
            "tripulante_id": "7",
            "observacao": "",
            "csrf_token": "ignored-by-contract-adapter",
            "screen_state": "screen-only",
        },
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["status"] == 201
    assert payload["code"] == "base_pilot_added"
    assert payload["pilot_id"] == 77
    assert isinstance(payload["pilot_id"], int)
    assert captured["actor_user_id"] == 61
    assert captured["payload"] == {
        "nome": "Lucas Silva",
        "matricula": "ab123",
        "status": "ativo",
        "base_id": "1",
        "tripulante_id": "7",
        "observacao": "",
    }


def test_bases_programmatic_status_and_move_use_formal_response_contract(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def _change_status(pilot_id, payload, *, actor_user_id):
        captured["status"] = {"pilot_id": pilot_id, "payload": dict(payload), "actor_user_id": actor_user_id}
        return {"message": "Status atualizado."}

    def _move_pilot(pilot_id, payload, *, actor_user_id):
        captured["move"] = {"pilot_id": pilot_id, "payload": dict(payload), "actor_user_id": actor_user_id}
        return {"message": "Piloto movido."}

    monkeypatch.setattr(bases_routes, "change_pilot_status", _change_status)
    monkeypatch.setattr(bases_routes, "move_pilot_to_base", _move_pilot)

    status_response = client.post(
        "/bases/pilotos/77/status",
        json={"status_novo": "folga", "observacao": "Escala", "screen_state": "screen-only"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    move_response = client.post(
        "/bases/pilotos/77/mover",
        json={"base_nova_id": 2, "observacao": "Realocacao", "screen_state": "screen-only"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )

    status_payload = status_response.get_json()
    move_payload = move_response.get_json()
    assert status_response.status_code == 200
    assert status_payload["success"] is True
    assert status_payload["code"] == "base_pilot_status_updated"
    assert status_payload["pilot_id"] == 77
    assert move_response.status_code == 200
    assert move_payload["success"] is True
    assert move_payload["code"] == "base_pilot_moved"
    assert move_payload["pilot_id"] == 77
    assert captured["status"] == {
        "pilot_id": 77,
        "payload": {"status_novo": "folga", "observacao": "Escala"},
        "actor_user_id": 61,
    }
    assert captured["move"] == {
        "pilot_id": 77,
        "payload": {"base_nova_id": "2", "observacao": "Realocacao"},
        "actor_user_id": 61,
    }


def test_bases_programmatic_history_uses_formal_response_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        bases_routes,
        "get_pilot_history",
        lambda pilot_id: {
            "piloto": {"id": str(pilot_id), "nome": "Lucas Silva", "matricula": None, "screen_badge": "x"},
            "historico": [
                {
                    "id": "5",
                    "event_type": "Cadastro inicial",
                    "status_anterior": "",
                    "status_novo": "ativo",
                    "base_anterior_nome": "",
                    "base_nova_nome": "SSA",
                    "alterado_por": "Gestora Bases",
                    "alterado_em": "01/04/2026 10:00",
                    "alterado_em_iso": "2026-04-01T10:00:00",
                    "observacao": None,
                    "html": "<span>screen</span>",
                }
            ],
        },
    )

    response = client.get("/bases/pilotos/77/historico")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["status"] == 200
    assert payload["code"] == "base_pilot_history_ok"
    assert payload["piloto"] == {"id": 77, "nome": "Lucas Silva", "matricula": ""}
    assert payload["historico"][0]["id"] == 5
    assert payload["historico"][0]["status_anterior"] is None
    assert payload["historico"][0]["base_anterior_nome"] is None
    assert payload["historico"][0]["alterado_em_iso"] == "2026-04-01T10:00:00"
    assert payload["historico"][0]["observacao"] == ""
    assert "html" not in payload["historico"][0]


def test_bases_programmatic_domain_error_uses_standard_error_contract(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def _raise_validation_error(_payload, *, actor_user_id):
        raise DomainValidationError(
            "Base invalida.",
            code="base_invalid",
            details={"field": "base_id", "reason": "invalid"},
        )

    monkeypatch.setattr(bases_routes, "add_pilot_to_base", _raise_validation_error)

    response = client.post(
        "/bases/pilotos/adicionar",
        data={"base_id": "abc"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 400
    assert payload["code"] == "base_invalid"
    assert payload["details"] == {"field": "base_id", "reason": "invalid"}
    assert "request_id" in payload
