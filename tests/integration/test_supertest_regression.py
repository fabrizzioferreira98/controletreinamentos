from __future__ import annotations

import inspect
import io
from datetime import date, datetime
from pathlib import Path

from flask import Flask
from flask_login import LoginManager, UserMixin, login_user
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos import db as db_module
from backend.src.controle_treinamentos.application import base_operations as base_operations_app
from backend.src.controle_treinamentos.application import tripulante_media as tripulante_media_app
from backend.src.controle_treinamentos.application import tripulantes as tripulantes_app
from backend.src.controle_treinamentos.blueprints.bases import routes as bases_module
from backend.src.controle_treinamentos.blueprints.cadastros import routes as cadastros_module
from backend.src.controle_treinamentos.blueprints.cadastros import routes_treinamentos as treinamentos_views_module
from backend.src.controle_treinamentos.blueprints.cadastros import routes_tripulante_views as tripulante_views_module
from backend.src.controle_treinamentos.core.cache_service import cache_service
from backend.src.controle_treinamentos.core.domain_errors import DomainConflictError
from backend.src.controle_treinamentos.repositories import dashboard_cache as routes_module
from backend.src.controle_treinamentos.repositories.queries import find_tripulante_by_cpf

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]


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


class _PayloadDB:
    def __init__(self, pilots):
        self._pilots = pilots

    def execute(self, query, params=()):
        compact = " ".join(query.split())
        if "FROM pilotos p" in compact:
            if "LOWER(TRIM(COALESCE(p.status, ''))) IN (%s, %s)" in compact:
                status_set = {str(params[0]).lower(), str(params[1]).lower()}
                rows = [item for item in self._pilots if str(item["status"]).strip().lower() in status_set]
                return _FakeCursor(rows)
            if "LOWER(TRIM(COALESCE(p.status, ''))) = %s" in compact:
                status = str(params[0]).lower()
                rows = [item for item in self._pilots if str(item["status"]).strip().lower() == status]
                return _FakeCursor(rows)
            if "LOWER(TRIM(COALESCE(p.status, ''))) <> %s" in compact:
                status = str(params[0]).lower()
                rows = [item for item in self._pilots if str(item["status"]).strip().lower() != status]
                return _FakeCursor(rows)
            return _FakeCursor(self._pilots)
        raise AssertionError(f"Unexpected query: {query}")


class _CaptureDB:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _FakeCursor([])


class _CpfDB:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _FakeCursor([{"id": 99}])


class _TripulanteMutationDB:
    def __init__(self, *, tripulante_row=None):
        self.calls = []
        self.tripulante_row = tripulante_row or {
            "id": 7,
            "foto_base64": None,
        }
        self.committed = False
        self.conn = self

    def execute(self, query, params=()):
        self.calls.append((query, params))
        compact = " ".join(query.split())
        if compact.startswith("SELECT * FROM tripulantes WHERE id = %s"):
            return _FakeCursor([self.tripulante_row])
        if "FROM tripulantes" in compact and ("WHERE id = %s" in compact or "WHERE t.id = %s" in compact):
            return _FakeCursor([self.tripulante_row])
        if compact.startswith("INSERT INTO tripulantes"):
            return _FakeCursor([{"id": 123}])
        if compact.startswith("UPDATE tripulantes"):
            return _FakeCursor([])
        raise AssertionError(f"Unexpected query: {query}")

    def commit(self):
        self.committed = True

    def rollback(self):
        return None


def _find_db_call(calls, fragment):
    return next((params for query, params in calls if fragment in query), None)


def _authenticate_bases_user(client, monkeypatch):
    row = {
        "id": 73,
        "nome": "Gestora Bases",
        "login": "gestora_bases",
        "email": "gestora.bases@local.test",
        "perfil": "gestora",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view","bases:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
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


def _authenticate_tripulantes_user(client, monkeypatch):
    row = {
        "id": 74,
        "nome": "Gestora Tripulantes",
        "login": "gestora_tripulantes",
        "email": "gestora.tripulantes@local.test",
        "perfil": "gestora",
        "ativo": 1,
        "permissao_modulos_json": '["tripulantes:view","tripulantes:edit","tripulantes_file:view","relatorio_individual:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "gestora_tripulantes", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_bases_bootstrap_uses_local_vendor_assets():
    base_template = (
        PROJECT_ROOT / "backend/src/controle_treinamentos/templates/base.html"
    ).read_text(encoding="utf-8")
    bases_template = (
        PROJECT_ROOT / "backend/src/controle_treinamentos/templates/bases/index.html"
    ).read_text(encoding="utf-8")
    security_module = (
        PROJECT_ROOT / "backend/src/controle_treinamentos/core/security.py"
    ).read_text(encoding="utf-8")

    assert "https://unpkg.com" not in base_template
    assert "https://unpkg.com" not in bases_template
    assert "https://unpkg.com" not in security_module
    assert "vendor/htmx/htmx-1.9.11.min.js" in base_template
    assert "vendor/leaflet/leaflet-1.9.4.css" in bases_template
    assert "vendor/leaflet/leaflet-1.9.4.js" in bases_template
    assert "renderMapBootstrapError" in bases_template


def test_bases_html_route_renders_local_asset_bootstrap(monkeypatch):
    payload = {
        "bases": [
            {
                "id": 1,
                "nome": "Sao Paulo",
                "uf": "SP",
                "latitude": -23.55,
                "longitude": -46.63,
                "ativa": True,
                "total_pilotos": 0,
                "counts": {"ativo": 0, "folga": 0, "ferias": 0, "atestado": 0, "afastado": 0, "treinamento": 0},
                "pilotos": [],
            }
        ],
        "pilotos": [],
        "status_options": list(bases_module.STATUS_META.values()),
        "status_filter": "",
    }
    monkeypatch.setattr(bases_module, "get_panel_cache", lambda _key: None)
    monkeypatch.setattr(bases_module, "set_panel_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bases_module, "_fetch_bases_payload", lambda *_args, **_kwargs: payload)

    app = create_app()
    client = app.test_client()
    _authenticate_bases_user(client, monkeypatch)

    response = client.get("/bases", follow_redirects=False)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Gest" in html
    assert "vendor/htmx/htmx-1.9.11.min.js" in html
    assert "vendor/leaflet/leaflet-1.9.4.css" in html
    assert "vendor/leaflet/leaflet-1.9.4.js" in html
    assert "https://unpkg.com" not in html


def test_bases_vendor_assets_are_versioned_locally_without_sourcemap_fetch():
    vendor_files = [
        "backend/src/controle_treinamentos/static/vendor/htmx/htmx-1.9.11.min.js",
        "backend/src/controle_treinamentos/static/vendor/leaflet/leaflet-1.9.4.css",
        "backend/src/controle_treinamentos/static/vendor/leaflet/leaflet-1.9.4.js",
        "backend/src/controle_treinamentos/static/vendor/leaflet/images/layers.png",
        "backend/src/controle_treinamentos/static/vendor/leaflet/images/layers-2x.png",
        "backend/src/controle_treinamentos/static/vendor/leaflet/images/marker-icon.png",
        "backend/src/controle_treinamentos/static/vendor/leaflet/images/marker-icon-2x.png",
        "backend/src/controle_treinamentos/static/vendor/leaflet/images/marker-shadow.png",
    ]

    for relative_path in vendor_files:
        asset_path = PROJECT_ROOT / relative_path
        assert asset_path.exists()
        assert asset_path.stat().st_size > 0

    leaflet_js = (
        PROJECT_ROOT / "backend/src/controle_treinamentos/static/vendor/leaflet/leaflet-1.9.4.js"
    ).read_text(encoding="utf-8")
    assert "sourceMappingURL" not in leaflet_js


def _sample_pilots():
    return [
        {
            "id": 1,
            "nome": "Piloto Ativo",
            "matricula": "000001",
            "tripulante_id": 10,
            "base_id": 1,
            "base_nome": "SÃ£o Paulo",
            "base_uf": "SP",
            "status": "ativo",
            "foto_base64": "",
            "criado_em": "2026-03-01 10:00:00",
        },
        {
            "id": 2,
            "nome": "Piloto Afastado",
            "matricula": "000002",
            "tripulante_id": 11,
            "base_id": 1,
            "base_nome": "SÃ£o Paulo",
            "base_uf": "SP",
            "status": "afastado",
            "foto_base64": "",
            "criado_em": "2026-03-01 10:00:00",
        },
    ]


def test_bases_payload_default_excludes_afastado(monkeypatch):
    db = _PayloadDB(_sample_pilots())
    monkeypatch.setattr(bases_module, "get_db", lambda: db)
    monkeypatch.setattr(
        bases_module,
        "fetch_unique_bases",
        lambda _db: [
            {
                "id": 1,
                "nome": "SÃ£o Paulo",
                "uf": "SP",
                "latitude": -23.55,
                "longitude": -46.63,
                "ativa": True,
            }
        ],
    )
    monkeypatch.setattr(bases_module, "_fetch_earliest_due_by_tripulante", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bases_module, "business_today", lambda: date(2026, 3, 25))

    payload = bases_module._fetch_bases_payload()

    assert [row["status"] for row in payload["pilotos"]] == ["ativo"]
    assert payload["bases"][0]["total_pilotos"] == 1
    assert "foto_base64" not in payload["pilotos"][0]
    assert payload["pilotos"][0]["foto_url"] == ""


def test_bases_payload_status_filter_includes_afastado(monkeypatch):
    db = _PayloadDB(_sample_pilots())
    monkeypatch.setattr(bases_module, "get_db", lambda: db)
    monkeypatch.setattr(
        bases_module,
        "fetch_unique_bases",
        lambda _db: [
            {
                "id": 1,
                "nome": "SÃ£o Paulo",
                "uf": "SP",
                "latitude": -23.55,
                "longitude": -46.63,
                "ativa": True,
            }
        ],
    )
    monkeypatch.setattr(bases_module, "_fetch_earliest_due_by_tripulante", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bases_module, "business_today", lambda: date(2026, 3, 25))

    payload = bases_module._fetch_bases_payload(status_filter="afastado")

    assert [row["status"] for row in payload["pilotos"]] == ["afastado"]
    assert payload["bases"][0]["counts"]["afastado"] == 1


def test_bases_payload_normalizes_accented_and_uppercase_status(monkeypatch):
    pilots = [
        {
            "id": 1,
            "nome": "Piloto F\u00e9rias",
            "matricula": "000003",
            "tripulante_id": 12,
            "base_id": 1,
            "base_nome": "S\u00e3o Paulo",
            "base_uf": "SP",
            "status": "F\u00c9RIAS",
            "foto_base64": "",
            "criado_em": "2026-03-01 10:00:00",
        }
    ]
    db = _PayloadDB(pilots)
    monkeypatch.setattr(bases_module, "get_db", lambda: db)
    monkeypatch.setattr(
        bases_module,
        "fetch_unique_bases",
        lambda _db: [
            {
                "id": 1,
                "nome": "S\u00e3o Paulo",
                "uf": "SP",
                "latitude": -23.55,
                "longitude": -46.63,
                "ativa": True,
            }
        ],
    )
    monkeypatch.setattr(bases_module, "_fetch_earliest_due_by_tripulante", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bases_module, "business_today", lambda: date(2026, 3, 25))

    payload = bases_module._fetch_bases_payload(status_filter="ferias")

    assert payload["status_filter"] == "ferias"
    assert payload["bases"][0]["counts"]["ferias"] == 1
    assert payload["pilotos"][0]["status"] == "ferias"


def test_bases_payload_unknown_status_does_not_raise(monkeypatch):
    pilots = [
        {
            "id": 1,
            "nome": "Piloto Legado",
            "matricula": "000004",
            "tripulante_id": 13,
            "base_id": 1,
            "base_nome": "SÃ£o Paulo",
            "base_uf": "SP",
            "status": "licenca_medica",
            "foto_base64": "",
            "criado_em": "2026-03-01 10:00:00",
        }
    ]
    db = _PayloadDB(pilots)
    monkeypatch.setattr(bases_module, "get_db", lambda: db)
    monkeypatch.setattr(
        bases_module,
        "fetch_unique_bases",
        lambda _db: [
            {
                "id": 1,
                "nome": "SÃ£o Paulo",
                "uf": "SP",
                "latitude": -23.55,
                "longitude": -46.63,
                "ativa": True,
            }
        ],
    )
    monkeypatch.setattr(bases_module, "_fetch_earliest_due_by_tripulante", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bases_module, "business_today", lambda: date(2026, 3, 25))

    payload = bases_module._fetch_bases_payload()

    assert payload["bases"][0]["total_pilotos"] == 1
    assert payload["bases"][0]["counts"]["desconhecido"] == 1
    assert payload["pilotos"][0]["status"] == "desconhecido"
    assert payload["pilotos"][0]["status_raw"] == "licenca_medica"


def test_bases_payload_cache_key_normalizes_accented_status():
    assert bases_module._payload_cache_key("f\u00e9rias") == "bases:payload:ferias"
    assert bases_module._payload_cache_key(" F\u00c9RIAS ") == "bases:payload:ferias"
    assert bases_module._payload_cache_key("ferias") == "bases:payload:ferias"
    assert bases_module._payload_cache_key("nao_mapeado") == "bases:payload:all"


def test_sync_tripulante_from_pilot_updates_ativo_for_afastado(monkeypatch):
    db = _CaptureDB()
    monkeypatch.setattr(
        base_operations_app,
        "fetch_active_base",
        lambda _db, _base_id: {"id": 1, "nome": "SÃ£o Paulo", "uf": "SP"},
    )

    base_operations_app._sync_tripulante_from_pilot(
        db,
        tripulante_id=7,
        nome="Teste",
        base_id=1,
        status="afastado",
    )

    assert db.calls
    _query, params = db.calls[0]
    assert params[0] == "Teste"
    assert params[1] == "SÃ£o Paulo"
    assert params[2] == "Afastado"
    assert params[3] == 0
    assert params[4] == 7


def test_sync_tripulante_from_pilot_accepts_unknown_status_without_crash(monkeypatch):
    db = _CaptureDB()
    monkeypatch.setattr(
        base_operations_app,
        "fetch_active_base",
        lambda _db, _base_id: {"id": 1, "nome": "SÃ£o Paulo", "uf": "SP"},
    )

    base_operations_app._sync_tripulante_from_pilot(
        db,
        tripulante_id=9,
        nome="Teste 2",
        base_id=1,
        status="licenca_medica",
    )

    assert db.calls
    _query, params = db.calls[0]
    assert params[0] == "Teste 2"
    assert params[1] == "SÃ£o Paulo"
    assert params[2] == "licenca_medica"
    assert params[3] == 1
    assert params[4] == 9


def test_alterar_status_route_requires_gestora_role():
    freevars = bases_module.alterar_status.__code__.co_freevars
    assert "roles" in freevars
    closure_values = [cell.cell_contents for cell in (bases_module.alterar_status.__closure__ or ())]
    roles_tuple = next((value for value in closure_values if isinstance(value, tuple)), ())
    assert "gestora" in roles_tuple


def test_adicionar_piloto_route_is_implemented():
    source = inspect.getsource(bases_module.adicionar_piloto.__wrapped__)
    assert "abort(404)" not in source
    assert "add_pilot_to_base" in source
    assert "parse_base_pilot_add_request" in source
    assert "serialize_base_pilot_added" in source
    assert "actor_user_id=int(current_user.id)" in source


def test_find_tripulante_by_cpf_normalizes_digits_and_excludes_id():
    db = _CpfDB()

    row = find_tripulante_by_cpf(db, "123.456.789-01", exclude_id=42)

    assert row == {"id": 99}
    assert db.calls
    _query, params = db.calls[0]
    assert params == ("12345678901", 42, 42)


def test_init_app_does_not_call_execute_script_when_not_testing(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = False

    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid")
    monkeypatch.setattr(db_module, "execute_script", lambda _db=None: (_ for _ in ()).throw(RuntimeError("boom")))

    db_module.init_app(app)


def test_init_app_does_not_call_execute_script_when_testing(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True

    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid")
    monkeypatch.setattr(db_module, "execute_script", lambda _db=None: (_ for _ in ()).throw(RuntimeError("boom")))

    db_module.init_app(app)


def test_clear_panel_cache_invalidates_navigation_and_dashboard_cache():
    cache_service._panel_cache.clear()
    cache_service._panel_cache["sample:key"] = (datetime.now(), {"ok": True})
    cache_service._nav_cache = (datetime.now(), {"tripulantes": 10})
    cache_service._dashboard_cache = (datetime.now(), {"totals": {"tripulantes": 10}})

    routes_module.clear_panel_cache()

    assert cache_service._panel_cache == {}
    assert cache_service._nav_cache is None
    assert cache_service._dashboard_cache is None


def test_tripulante_photo_payload_accepts_jpg_and_webp_data_uri():
    jpg_payload = "data:image/jpg;base64,aGVsbG8="
    webp_payload = "data:image/webp;base64,aGVsbG8="

    decoded_jpg = tripulante_media_app.load_tripulante_photo_payload({"foto_storage_ref": "", "foto_base64": jpg_payload})
    decoded_webp = tripulante_media_app.load_tripulante_photo_payload({"foto_storage_ref": "", "foto_base64": webp_payload})

    assert decoded_jpg is not None
    assert decoded_jpg["mime_type"] == "image/jpeg"
    assert decoded_webp is not None
    assert decoded_webp["mime_type"] == "image/webp"


def test_tripulantes_new_persists_possui_foto_as_boolean(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    db = _TripulanteMutationDB()

    monkeypatch.setattr(cadastros_module, "get_db", lambda: db)
    monkeypatch.setattr(tripulantes_app, "get_db", lambda: db)
    monkeypatch.setattr(tripulantes_app, "ensure_base_exists", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "find_tripulante_by_cpf", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "sync_linked_pilot_from_tripulante", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "clear_panel_cache", lambda: None)
    monkeypatch.setattr(cadastros_module, "url_for", lambda *_args, **_kwargs: "/tripulantes")
    monkeypatch.setattr(cadastros_module, "fetch_base_options", lambda *_args, **_kwargs: [])

    with app.test_request_context(
        "/tripulantes/novo",
        method="POST",
        data={
            "nome": "Tripulante Teste",
            "cpf": "12345678901",
            "licenca_anac": "123456",
            "email": "trip@example.com",
            "telefone": "11999999999",
            "base": "Sao Paulo",
            "status": "Ativo",
            "funcao_operacional": "comandante",
            "categoria_operacional": "N/A",
            "ativo": "1",
        },
    ):
        response = cadastros_module.tripulantes_new.__wrapped__()

    insert_call = _find_db_call(db.calls, "INSERT INTO tripulantes")
    photo_update_call = _find_db_call(db.calls, "SET foto_storage_ref = %s,")
    assert insert_call is not None
    assert photo_update_call is not None
    assert isinstance(photo_update_call[2], bool)
    assert photo_update_call[2] is False
    assert response.status_code == 302
    assert db.committed is True


def test_tripulantes_edit_persists_possui_foto_as_boolean(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    db = _TripulanteMutationDB()

    monkeypatch.setattr(cadastros_module, "get_db", lambda: db)
    monkeypatch.setattr(tripulantes_app, "get_db", lambda: db)
    monkeypatch.setattr(tripulantes_app, "ensure_base_exists", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "find_tripulante_by_cpf", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "sync_linked_pilot_from_tripulante", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tripulantes_app, "clear_panel_cache", lambda: None)
    monkeypatch.setattr(cadastros_module, "url_for", lambda *_args, **_kwargs: "/tripulantes")
    monkeypatch.setattr(cadastros_module, "fetch_base_options", lambda *_args, **_kwargs: [])

    with app.test_request_context(
        "/tripulantes/7/editar",
        method="POST",
        data={
            "nome": "Tripulante Editado",
            "cpf": "12345678901",
            "licenca_anac": "123456",
            "email": "trip@example.com",
            "telefone": "11999999999",
            "base": "Sao Paulo",
            "status": "Ativo",
            "funcao_operacional": "comandante",
            "categoria_operacional": "N/A",
            "ativo": "1",
        },
    ):
        response = cadastros_module.tripulantes_edit.__wrapped__(7)

    update_call = _find_db_call(db.calls, "SET nome = %s, cpf = %s")
    assert update_call is not None
    assert isinstance(update_call[8], bool)
    assert update_call[8] is False
    assert response.status_code == 302
    assert db.committed is True


def test_tripulantes_edit_form_keeps_legacy_photo_behind_route_not_inline_base64(monkeypatch):
    tripulante = {
        "id": 7,
        "nome": "Tripulante Legado",
        "cpf": "12345678901",
        "licenca_anac": "123456",
        "email": "trip@example.com",
        "telefone": "11999999999",
        "base": "Sao Paulo",
        "status": "Ativo",
        "funcao_operacional": "comandante",
        "categoria_operacional": "N/A",
        "observacoes": "",
        "ativo": 1,
        "sdea_ativo": 0,
        "instrutor_ativo": 0,
        "checador_ativo": 0,
        "elegivel_adicional_excepcional": 0,
        "foto_base64": "data:image/png;base64,aW1n",
        "foto_storage_ref": "",
        "foto_mime_type": "",
        "possui_foto": True,
    }

    monkeypatch.setattr(cadastros_module, "frontend_compat_enabled", lambda: False)
    monkeypatch.setattr(cadastros_module, "get_db", lambda: object())
    monkeypatch.setattr(cadastros_module, "fetch_tripulante_for_write", lambda *_args, **_kwargs: tripulante)
    monkeypatch.setattr(
        cadastros_module,
        "fetch_base_options",
        lambda *_args, **_kwargs: [{"nome": "Sao Paulo", "uf": "SP"}],
    )

    app = create_app()
    client = app.test_client()
    _authenticate_tripulantes_user(client, monkeypatch)

    response = client.get("/tripulantes/7/editar", follow_redirects=False)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="foto_base64" id="foto_base64" value=""' in html
    assert "data:image/png;base64,aW1n" not in html
    assert 'data-current-url="/tripulantes/7/foto"' in html


def test_tripulantes_delete_html_delegates_to_application_use_case(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    calls = []

    def _delete_tripulante(*, tripulante_id):
        calls.append(tripulante_id)
        return {"operation": "inactivated", "message": "Tripulante inativado porque existem vinculos historicos."}

    monkeypatch.setattr(tripulante_views_module, "delete_tripulante", _delete_tripulante)
    monkeypatch.setattr(tripulante_views_module, "url_for", lambda *_args, **_kwargs: "/tripulantes")

    with app.test_request_context("/tripulantes/7/excluir", method="POST"):
        response = tripulante_views_module.tripulantes_delete.__wrapped__(7)

    assert calls == [7]
    assert response.status_code == 302
    assert response.location == "/tripulantes"


def test_tripulantes_delete_html_translates_domain_error(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"

    def _delete_tripulante(*, tripulante_id):
        raise DomainConflictError(f"Tripulante {tripulante_id} bloqueado por vinculos historicos.")

    monkeypatch.setattr(tripulante_views_module, "delete_tripulante", _delete_tripulante)
    monkeypatch.setattr(tripulante_views_module, "url_for", lambda *_args, **_kwargs: "/tripulantes")

    with app.test_request_context("/tripulantes/7/excluir", method="POST"):
        response = tripulante_views_module.tripulantes_delete.__wrapped__(7)

    assert response.status_code == 302
    assert response.location == "/tripulantes"


def _treinamentos_url_for(endpoint, **kwargs):
    if endpoint == "cadastros.treinamentos_edit":
        return f"/treinamentos/{kwargs['treinamento_id']}/editar"
    return "/treinamentos"


def test_treinamentos_new_html_delegates_to_application_use_case(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    calls = []

    def _save_treinamento(payload, treinamento_id=None):
        calls.append((payload["tripulante_id"], treinamento_id))
        return {"operation": "created"}

    monkeypatch.setattr(treinamentos_views_module, "save_treinamento", _save_treinamento)
    monkeypatch.setattr(treinamentos_views_module, "url_for", _treinamentos_url_for)

    with app.test_request_context(
        "/treinamentos/novo",
        method="POST",
        data={
            "tripulante_id": "7",
            "equipamento_id": "3",
            "tipo_treinamento_id": "2",
            "data_realizacao": "2026-04-01",
            "due_date_mode": "auto",
        },
    ):
        response = treinamentos_views_module.treinamentos_new.__wrapped__()

    assert calls == [("7", None)]
    assert response.status_code == 302
    assert response.location == "/treinamentos"


def test_treinamentos_edit_html_delegates_to_application_use_case(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    calls = []

    def _save_treinamento(payload, treinamento_id=None):
        calls.append((payload["tipo_treinamento_id"], treinamento_id))
        return {"operation": "updated"}

    monkeypatch.setattr(treinamentos_views_module, "save_treinamento", _save_treinamento)
    monkeypatch.setattr(treinamentos_views_module, "url_for", _treinamentos_url_for)

    with app.test_request_context(
        "/treinamentos/55/editar",
        method="POST",
        data={
            "tripulante_id": "7",
            "equipamento_id": "3",
            "tipo_treinamento_id": "2",
            "data_realizacao": "2026-04-01",
            "due_date_mode": "auto",
        },
    ):
        response = treinamentos_views_module.treinamentos_edit.__wrapped__(55)

    assert calls == [("2", 55)]
    assert response.status_code == 302
    assert response.location == "/treinamentos"


def test_treinamentos_delete_html_delegates_to_application_use_case(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    calls = []

    def _delete_treinamento(*, treinamento_id):
        calls.append(treinamento_id)
        return {"operation": "deleted", "treinamento_id": treinamento_id}

    monkeypatch.setattr(treinamentos_views_module, "delete_treinamento", _delete_treinamento)
    monkeypatch.setattr(treinamentos_views_module, "url_for", _treinamentos_url_for)

    with app.test_request_context("/treinamentos/55/excluir", method="POST"):
        response = treinamentos_views_module.treinamentos_delete.__wrapped__(55)

    assert calls == [55]
    assert response.status_code == 302
    assert response.location == "/treinamentos"


def test_treinamentos_html_translates_domain_error_near_form(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"

    def _save_treinamento(_payload, treinamento_id=None):
        raise DomainConflictError("Treinamento bloqueado por regra de dominio.")

    monkeypatch.setattr(treinamentos_views_module, "save_treinamento", _save_treinamento)
    monkeypatch.setattr(treinamentos_views_module, "get_db", lambda: object())
    monkeypatch.setattr(treinamentos_views_module, "get_training_form_options", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(treinamentos_views_module, "render_template", lambda *_args, **_kwargs: "form")

    with app.test_request_context(
        "/treinamentos/novo",
        method="POST",
        data={
            "tripulante_id": "7",
            "tipo_treinamento_id": "2",
            "data_realizacao": "2026-04-01",
        },
    ):
        response = treinamentos_views_module.treinamentos_new.__wrapped__()

    assert response == ("form", 400)


def test_treinamentos_attachment_upload_html_delegates_to_application(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    calls = []

    class _CurrentUser:
        id = 41

    def _upload_treinamento_attachment(payload, *, treinamento_id, enviado_por):
        calls.append((payload["filename"], payload["arquivo_bytes"], treinamento_id, enviado_por))
        return {"id": 88}

    monkeypatch.setattr(treinamentos_views_module, "current_user", _CurrentUser())
    monkeypatch.setattr(treinamentos_views_module, "upload_treinamento_attachment", _upload_treinamento_attachment)
    monkeypatch.setattr(treinamentos_views_module, "url_for", _treinamentos_url_for)

    with app.test_request_context(
        "/treinamentos/55/anexos/upload",
        method="POST",
        data={"arquivo_pdf": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "anexo.pdf")},
        content_type="multipart/form-data",
    ):
        response = treinamentos_views_module.treinamentos_anexo_upload.__wrapped__(55)

    assert calls == [("anexo.pdf", b"%PDF-1.4\n%%EOF", 55, 41)]
    assert response.status_code == 302
    assert response.location == "/treinamentos/55/editar"


def test_treinamentos_attachment_get_html_delegates_to_application(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    login_manager = LoginManager(app)
    calls = []

    class _AllowedUser(UserMixin):
        id = "41"

        def has_permission(self, permission):
            return permission == "treinamentos_anexos:view"

    @login_manager.user_loader
    def _load_user(_user_id):
        return _AllowedUser()

    def _get_treinamento_attachment(*, treinamento_id, anexo_id):
        calls.append((treinamento_id, anexo_id))
        return {"nome_original": "anexo.pdf", "mime_type": "application/pdf", "payload_bytes": b"%PDF-1.4\n%%EOF"}

    monkeypatch.setattr(treinamentos_views_module, "get_treinamento_attachment", _get_treinamento_attachment)

    with app.test_request_context("/treinamentos/55/anexos/77"):
        login_user(_AllowedUser())
        response = treinamentos_views_module.treinamentos_anexo_get.__wrapped__(55, 77)

    assert calls == [(55, 77)]
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_treinamentos_attachment_delete_html_delegates_to_application(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    calls = []

    def _delete_treinamento_attachment(*, treinamento_id, anexo_id):
        calls.append((treinamento_id, anexo_id))
        return {"id": anexo_id}

    monkeypatch.setattr(treinamentos_views_module, "delete_treinamento_attachment", _delete_treinamento_attachment)
    monkeypatch.setattr(treinamentos_views_module, "url_for", _treinamentos_url_for)

    with app.test_request_context("/treinamentos/55/anexos/77/excluir", method="POST"):
        response = treinamentos_views_module.treinamentos_anexo_delete.__wrapped__(55, 77)

    assert calls == [(55, 77)]
    assert response.status_code == 302
    assert response.location == "/treinamentos/55/editar"


def test_bases_decode_photo_data_uri_accepts_jpg_and_webp():
    jpg_payload = "data:image/jpg;base64,aGVsbG8="
    webp_payload = "data:image/webp;base64,aGVsbG8="

    decoded_jpg = bases_module._decode_photo_data_uri(jpg_payload)
    decoded_webp = bases_module._decode_photo_data_uri(webp_payload)

    assert decoded_jpg is not None
    assert decoded_jpg[1] == "image/jpeg"
    assert decoded_webp is not None
    assert decoded_webp[1] == "image/webp"


def test_clear_panel_cache_prefix_keeps_other_keys_and_still_invalidates_global_cache():
    cache_service._panel_cache.clear()
    cache_service._panel_cache["options:one"] = (datetime.now(), {"ok": 1})
    cache_service._panel_cache["other:two"] = (datetime.now(), {"ok": 2})
    cache_service._nav_cache = (datetime.now(), {"tripulantes": 2})
    cache_service._dashboard_cache = (datetime.now(), {"totals": {"tripulantes": 2}})

    routes_module.clear_panel_cache("options:")

    assert "options:one" not in cache_service._panel_cache
    assert "other:two" in cache_service._panel_cache
    assert cache_service._nav_cache is None
    assert cache_service._dashboard_cache is None


def test_clear_catalog_options_cache_does_not_invalidate_global_snapshots():
    cache_service._panel_cache.clear()
    cache_service._panel_cache["options:equipamentos:all"] = (datetime.now(), {"ok": 1})
    cache_service._panel_cache["options:tipos_treinamento:all"] = (datetime.now(), {"ok": 2})
    cache_service._panel_cache["other:two"] = (datetime.now(), {"ok": 3})
    nav_payload = {"tripulantes": 2}
    dashboard_payload = {"totals": {"tripulantes": 2}}
    cache_service._nav_cache = (datetime.now(), nav_payload)
    cache_service._dashboard_cache = (datetime.now(), dashboard_payload)

    routes_module.clear_catalog_options_cache()

    assert "options:equipamentos:all" not in cache_service._panel_cache
    assert "options:tipos_treinamento:all" not in cache_service._panel_cache
    assert "other:two" in cache_service._panel_cache
    assert cache_service._nav_cache is not None
    assert cache_service._dashboard_cache is not None
    assert cache_service._nav_cache[1] == nav_payload
    assert cache_service._dashboard_cache[1] == dashboard_payload

