from __future__ import annotations

import inspect
from datetime import date, datetime

from flask import Flask

from backend.src.controle_treinamentos import db as db_module
from backend.src.controle_treinamentos.blueprints.bases import routes as bases_module
from backend.src.controle_treinamentos.blueprints.cadastros import routes as cadastros_module
from backend.src.controle_treinamentos.core.cache_service import cache_service
from backend.src.controle_treinamentos.repositories import dashboard_cache as routes_module
from backend.src.controle_treinamentos.repositories.queries import find_tripulante_by_cpf


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]


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

    def execute(self, query, params=()):
        self.calls.append((query, params))
        compact = " ".join(query.split())
        if compact.startswith("SELECT * FROM tripulantes WHERE id = %s"):
            return _FakeCursor([self.tripulante_row])
        if compact.startswith("INSERT INTO tripulantes"):
            return _FakeCursor([{"id": 123}])
        if compact.startswith("UPDATE tripulantes"):
            return _FakeCursor([])
        raise AssertionError(f"Unexpected query: {query}")

    def commit(self):
        self.committed = True


def _find_db_call(calls, fragment):
    return next((params for query, params in calls if fragment in query), None)


def _sample_pilots():
    return [
        {
            "id": 1,
            "nome": "Piloto Ativo",
            "matricula": "000001",
            "tripulante_id": 10,
            "base_id": 1,
            "base_nome": "São Paulo",
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
            "base_nome": "São Paulo",
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
                "nome": "São Paulo",
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
                "nome": "São Paulo",
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
            "nome": "Piloto Férias",
            "matricula": "000003",
            "tripulante_id": 12,
            "base_id": 1,
            "base_nome": "São Paulo",
            "base_uf": "SP",
            "status": "FÉRIAS",
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
                "nome": "São Paulo",
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
            "base_nome": "São Paulo",
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
                "nome": "São Paulo",
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
    assert bases_module._payload_cache_key("férias") == "bases:payload:ferias"
    assert bases_module._payload_cache_key(" FÉRIAS ") == "bases:payload:ferias"
    assert bases_module._payload_cache_key("ferias") == "bases:payload:ferias"
    assert bases_module._payload_cache_key("nao_mapeado") == "bases:payload:all"


def test_sync_tripulante_from_pilot_updates_ativo_for_afastado(monkeypatch):
    db = _CaptureDB()
    monkeypatch.setattr(bases_module, "_get_active_base", lambda _base_id: {"id": 1, "nome": "São Paulo", "uf": "SP"})

    bases_module._sync_tripulante_from_pilot(
        db,
        tripulante_id=7,
        nome="Teste",
        base_id=1,
        status="afastado",
    )

    assert db.calls
    _query, params = db.calls[0]
    assert params[0] == "Teste"
    assert params[1] == "São Paulo"
    assert params[2] == "Afastado"
    assert params[3] == 0
    assert params[4] == 7


def test_sync_tripulante_from_pilot_accepts_unknown_status_without_crash(monkeypatch):
    db = _CaptureDB()
    monkeypatch.setattr(bases_module, "_get_active_base", lambda _base_id: {"id": 1, "nome": "São Paulo", "uf": "SP"})

    bases_module._sync_tripulante_from_pilot(
        db,
        tripulante_id=9,
        nome="Teste 2",
        base_id=1,
        status="licenca_medica",
    )

    assert db.calls
    _query, params = db.calls[0]
    assert params[0] == "Teste 2"
    assert params[1] == "São Paulo"
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
    assert "INSERT INTO pilotos" in source


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


def test_decode_photo_data_uri_accepts_jpg_and_webp():
    jpg_payload = "data:image/jpg;base64,aGVsbG8="
    webp_payload = "data:image/webp;base64,aGVsbG8="

    decoded_jpg = cadastros_module._decode_photo_data_uri(jpg_payload)
    decoded_webp = cadastros_module._decode_photo_data_uri(webp_payload)

    assert decoded_jpg is not None
    assert decoded_jpg[1] == "image/jpeg"
    assert decoded_webp is not None
    assert decoded_webp[1] == "image/webp"


def test_tripulantes_new_persists_possui_foto_as_boolean(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    db = _TripulanteMutationDB()

    monkeypatch.setattr(cadastros_module, "get_db", lambda: db)
    monkeypatch.setattr(cadastros_module, "ensure_base_exists", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "find_tripulante_by_cpf", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "sync_linked_pilot_from_tripulante", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "clear_panel_cache", lambda: None)
    monkeypatch.setattr(cadastros_module, "url_for", lambda *_args, **_kwargs: "/tripulantes")
    monkeypatch.setattr(cadastros_module, "fetch_base_options", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cadastros_module, "sanitize_photo_base64", lambda *_args, **_kwargs: "data:image/png;base64,aGVsbG8=")

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
    photo_update_call = _find_db_call(db.calls, "SET foto_base64 = %s,")
    assert insert_call is not None
    assert photo_update_call is not None
    assert isinstance(photo_update_call[3], bool)
    assert photo_update_call[3] is False
    assert response.status_code == 302
    assert db.committed is True


def test_tripulantes_edit_persists_possui_foto_as_boolean(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    db = _TripulanteMutationDB()

    monkeypatch.setattr(cadastros_module, "get_db", lambda: db)
    monkeypatch.setattr(cadastros_module, "ensure_base_exists", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "find_tripulante_by_cpf", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "sync_linked_pilot_from_tripulante", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cadastros_module, "clear_panel_cache", lambda: None)
    monkeypatch.setattr(cadastros_module, "url_for", lambda *_args, **_kwargs: "/tripulantes")
    monkeypatch.setattr(cadastros_module, "fetch_base_options", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cadastros_module, "sanitize_photo_base64", lambda *_args, **_kwargs: "data:image/png;base64,aGVsbG8=")

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
    assert isinstance(update_call[11], bool)
    assert update_call[11] is False
    assert response.status_code == 302
    assert db.committed is True


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
