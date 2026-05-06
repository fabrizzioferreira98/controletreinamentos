from __future__ import annotations

from importlib import import_module

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.cadastros import routes_catalogos


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params=None):
        return _SingleCursor(self._row)


class _Cursor:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _CatalogosDB:
    def __init__(
        self,
        *,
        missing_equipment_ids=None,
        missing_tipo_ids=None,
        linked_equipment_ids=None,
        linked_tipo_ids=None,
    ):
        self.queries = []
        self.params = []
        self.missing_equipment_ids = set(missing_equipment_ids or set())
        self.missing_tipo_ids = set(missing_tipo_ids or set())
        self.linked_equipment_ids = set(linked_equipment_ids or set())
        self.linked_tipo_ids = set(linked_tipo_ids or set())
        self.inserted_equipamentos = []
        self.updated_equipamentos = []
        self.deleted_equipamentos = []
        self.inserted_tipos = []
        self.updated_tipos = []
        self.deleted_tipos = []
        self.commits = 0

    def execute(self, query, params=None):
        normalized = " ".join(str(query).split()).lower()
        self.queries.append(normalized)
        self.params.append(params)

        if "count(*) as total from equipamentos" in normalized:
            return _Cursor(row={"total": 25})
        if "from equipamentos" in normalized and "order by nome limit" in normalized:
            return _Cursor(
                rows=[
                    {
                        "id": 2,
                        "nome": "AS350",
                        "tipo": "Helicoptero",
                        "categoria_financeira": "b",
                        "ativo": 1,
                    }
                ]
            )
        if "insert into equipamentos" in normalized:
            self.inserted_equipamentos.append(params)
            return _Cursor(row={"id": 101})
        if "select * from equipamentos where id" in normalized:
            equipamento_id = int(params[0])
            if equipamento_id in self.missing_equipment_ids:
                return _Cursor(row=None)
            return _Cursor(
                row={
                    "id": equipamento_id,
                    "nome": "AS350",
                    "tipo": "Helicoptero",
                    "categoria_financeira": "b",
                    "ativo": 1,
                }
            )
        if "select id from equipamentos where id" in normalized:
            equipamento_id = int(params[0])
            if equipamento_id in self.missing_equipment_ids:
                return _Cursor(row=None)
            return _Cursor(row={"id": equipamento_id})
        if "update equipamentos set" in normalized:
            self.updated_equipamentos.append(params)
            return _Cursor()
        if "from treinamentos where equipamento_id" in normalized:
            equipamento_id = int(params[0])
            return _Cursor(row={"id": 500} if equipamento_id in self.linked_equipment_ids else None)
        if "delete from equipamentos" in normalized:
            self.deleted_equipamentos.append(int(params[0]))
            return _Cursor()
        if "count(*) as total from tipos_treinamento" in normalized:
            return _Cursor(row={"total": 22})
        if "from tipos_treinamento" in normalized and "order by nome limit" in normalized:
            return _Cursor(
                rows=[
                    {
                        "id": 4,
                        "nome": "CQ IFR",
                        "periodicidade_meses": 6,
                        "exige_equipamento": 1,
                        "ativo": 1,
                    }
                ]
            )
        if "insert into tipos_treinamento" in normalized:
            self.inserted_tipos.append(params)
            return _Cursor(row={"id": 202})
        if "select * from tipos_treinamento where id" in normalized:
            tipo_id = int(params[0])
            if tipo_id in self.missing_tipo_ids:
                return _Cursor(row=None)
            return _Cursor(
                row={
                    "id": tipo_id,
                    "nome": "CQ IFR",
                    "periodicidade_meses": 6,
                    "exige_equipamento": 1,
                    "ativo": 1,
                }
            )
        if "select id from tipos_treinamento where id" in normalized:
            tipo_id = int(params[0])
            if tipo_id in self.missing_tipo_ids:
                return _Cursor(row=None)
            return _Cursor(row={"id": tipo_id})
        if "update tipos_treinamento" in normalized:
            self.updated_tipos.append(params)
            return _Cursor()
        if "from treinamentos where tipo_treinamento_id" in normalized:
            tipo_id = int(params[0])
            return _Cursor(row={"id": 600} if tipo_id in self.linked_tipo_ids else None)
        if "delete from tipos_treinamento" in normalized:
            self.deleted_tipos.append(int(params[0]))
            return _Cursor()
        raise AssertionError(f"Unexpected catalog query: {query}")

    def commit(self):
        self.commits += 1


def _auth_user_row():
    return {
        "id": 71,
        "nome": "Operador Catalogos",
        "login": "catalogos_ssr",
        "email": "catalogos.ssr@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": (
            '["equipamentos:view","equipamentos:create","equipamentos:edit","equipamentos:delete",'
            '"tipos_treinamento:view","tipos_treinamento:create","tipos_treinamento:edit",'
            '"tipos_treinamento:delete"]'
        ),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch):
    fake_db = _SingleUserDB(_auth_user_row())
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "catalogos_ssr", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def _patch_catalogos_db(monkeypatch, fake_db):
    monkeypatch.setattr(routes_catalogos, "get_db", lambda: fake_db, raising=False)
    try:
        catalogos_ssr = import_module("backend.src.controle_treinamentos.application.catalogos_ssr")
    except ModuleNotFoundError:
        return
    monkeypatch.setattr(catalogos_ssr, "get_db", lambda: fake_db)


def _capture_render_template(monkeypatch):
    captured = {}

    def _render_template(template, **context):
        captured["template"] = template
        captured["context"] = context
        return "rendered"

    monkeypatch.setattr(routes_catalogos, "render_template", _render_template)
    return captured


def _client_with_catalog_permissions(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    return app, client


def _patch_catalog_side_effects(monkeypatch):
    captured = {"audits": [], "cache_clears": 0}

    def _audit_event(*args, **kwargs):
        captured["audits"].append({"args": args, "kwargs": kwargs})

    def _clear_catalog_options_cache():
        captured["cache_clears"] += 1

    monkeypatch.setattr(routes_catalogos, "audit_event", _audit_event, raising=False)
    monkeypatch.setattr(routes_catalogos, "clear_catalog_options_cache", _clear_catalog_options_cache, raising=False)
    catalogos_ssr = import_module("backend.src.controle_treinamentos.application.catalogos_ssr")
    monkeypatch.setattr(catalogos_ssr, "audit_event", _audit_event, raising=False)
    monkeypatch.setattr(catalogos_ssr, "clear_catalog_options_cache", _clear_catalog_options_cache, raising=False)
    return captured


def _flashes(client):
    with client.session_transaction() as session:
        return list(session.get("_flashes", []))


def _assert_redirects_to(response, path: str):
    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith(path)


def test_equipamentos_list_preserves_template_context_and_pagination(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.get("/equipamentos?page=2")

    assert response.status_code == 200
    assert captured["template"] == "equipamentos_list.html"
    assert captured["context"]["equipamentos"] == [
        {"id": 2, "nome": "AS350", "tipo": "Helicoptero", "categoria_financeira": "b", "ativo": 1}
    ]
    assert captured["context"]["pagination"]["page"] == 2
    assert captured["context"]["pagination"]["per_page"] == 20
    assert captured["context"]["pagination"]["total"] == 25
    assert captured["context"]["pagination"]["has_prev"] is True
    assert captured["context"]["pagination"]["has_next"] is False
    assert fake_db.params[-1] == (20, 20)
    assert any("select * from equipamentos order by nome limit" in query for query in fake_db.queries)


def test_equipamentos_list_consumes_prior_document_404_flash_from_session(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    _patch_catalogos_db(monkeypatch, _CatalogosDB())

    not_found = client.get(
        "/_test/nao-existe-catalogos",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
        },
        follow_redirects=False,
    )

    assert not_found.status_code in {302, 303}
    assert ("error", "Recurso não encontrado.") in _flashes(client)

    response = client.get("/equipamentos")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Recurso não encontrado." in html
    assert _flashes(client) == []


def test_non_document_404_probe_does_not_pollute_equipamentos_flash(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    _patch_catalogos_db(monkeypatch, _CatalogosDB())

    probe = client.get(
        "/sw.js",
        headers={"Sec-Fetch-Dest": "serviceworker", "Accept": "*/*"},
        follow_redirects=False,
    )

    assert probe.status_code == 404
    assert _flashes(client) == []

    response = client.get("/equipamentos")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Recurso não encontrado." not in html


def test_tipos_treinamento_list_preserves_template_context_and_pagination(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.get("/tipos-treinamento?page=2")

    assert response.status_code == 200
    assert captured["template"] == "tipos_list.html"
    assert captured["context"]["tipos"] == [
        {
            "id": 4,
            "nome": "CQ IFR",
            "periodicidade_meses": 6,
            "exige_equipamento": 1,
            "ativo": 1,
        }
    ]
    assert captured["context"]["pagination"]["page"] == 2
    assert captured["context"]["pagination"]["per_page"] == 20
    assert captured["context"]["pagination"]["total"] == 22
    assert captured["context"]["pagination"]["has_prev"] is True
    assert captured["context"]["pagination"]["has_next"] is False
    assert fake_db.params[-1] == (20, 20)
    assert any("select * from tipos_treinamento order by nome limit" in query for query in fake_db.queries)


@pytest.mark.parametrize(
    ("path", "template", "context_key"),
    [
        ("/equipamentos/novo", "equipamentos_form.html", "equipamento"),
        ("/tipos-treinamento/novo", "tipos_form.html", "tipo"),
    ],
)
def test_catalog_create_get_preserves_form_template(monkeypatch, path, template, context_key):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    _patch_catalogos_db(monkeypatch, _CatalogosDB())
    captured = _capture_render_template(monkeypatch)

    response = client.get(path)

    assert response.status_code == 200
    assert captured["template"] == template
    assert captured["context"][context_key] is None


def test_equipamentos_create_post_valid_preserves_redirect_flash_audit_and_cache(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post(
        "/equipamentos/novo",
        data={"nome": "Bell 407", "tipo": "Helicoptero", "categoria_financeira": "a", "ativo": "on"},
    )

    _assert_redirects_to(response, "/equipamentos")
    assert fake_db.inserted_equipamentos == [("Bell 407", "Helicoptero", "a", 1)]
    assert fake_db.commits == 1
    assert side_effects["cache_clears"] == 1
    assert side_effects["audits"][0]["args"][1:4] == ("equipamento", 101, "create")
    assert _flashes(client) == [("success", "Equipamento cadastrado com sucesso.")]


def test_equipamentos_create_post_invalid_preserves_form_state_status_and_flash(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.post("/equipamentos/novo", data={"tipo": "Helicoptero", "ativo": "on"})

    assert response.status_code == 400
    assert captured["template"] == "equipamentos_form.html"
    assert captured["context"]["equipamento"]["tipo"] == "Helicoptero"
    assert captured["context"]["equipamento"]["ativo"] is True
    assert fake_db.inserted_equipamentos == []
    assert fake_db.commits == 0
    assert _flashes(client) == [("error", "O campo 'Nome' é obrigatório.")]


def test_equipamentos_edit_get_existing_preserves_form_context(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.get("/equipamentos/2/editar")

    assert response.status_code == 200
    assert captured["template"] == "equipamentos_form.html"
    assert captured["context"]["equipamento"] == {
        "id": 2,
        "nome": "AS350",
        "tipo": "Helicoptero",
        "categoria_financeira": "b",
        "ativo": 1,
    }


def test_equipamentos_edit_get_missing_preserves_404(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    _patch_catalogos_db(monkeypatch, _CatalogosDB(missing_equipment_ids={999}))

    response = client.get("/equipamentos/999/editar")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_equipamentos_edit_post_valid_preserves_redirect_flash_audit_and_cache(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post(
        "/equipamentos/2/editar",
        data={"nome": "AS350 B2", "tipo": "Helicoptero", "categoria_financeira": "turbohelice_palmas"},
    )

    _assert_redirects_to(response, "/equipamentos")
    assert fake_db.updated_equipamentos == [("AS350 B2", "Helicoptero", "turbohelice_palmas", 0, 2)]
    assert fake_db.commits == 1
    assert side_effects["cache_clears"] == 1
    assert side_effects["audits"][0]["args"][1:4] == ("equipamento", 2, "update")
    assert _flashes(client) == [("success", "Equipamento atualizado com sucesso.")]


def test_equipamentos_edit_post_invalid_preserves_form_state_status_and_flash(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.post("/equipamentos/2/editar", data={"tipo": "Helicoptero"})

    assert response.status_code == 400
    assert captured["template"] == "equipamentos_form.html"
    assert captured["context"]["equipamento"]["tipo"] == "Helicoptero"
    assert fake_db.updated_equipamentos == []
    assert fake_db.commits == 0
    assert _flashes(client) == [("error", "O campo 'Nome' é obrigatório.")]


def test_equipamentos_delete_with_linked_training_preserves_block_flash_and_redirect(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB(linked_equipment_ids={2})
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post("/equipamentos/2/excluir")

    _assert_redirects_to(response, "/equipamentos")
    assert fake_db.deleted_equipamentos == []
    assert fake_db.commits == 0
    assert side_effects["cache_clears"] == 0
    assert side_effects["audits"] == []
    assert _flashes(client) == [
        ("error", "Não é possível excluir o equipamento porque existem treinamentos vinculados.")
    ]


def test_equipamentos_delete_without_linked_training_preserves_delete_flash_audit_and_cache(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post("/equipamentos/2/excluir")

    _assert_redirects_to(response, "/equipamentos")
    assert fake_db.deleted_equipamentos == [2]
    assert fake_db.commits == 1
    assert side_effects["cache_clears"] == 1
    assert side_effects["audits"][0]["args"][1:4] == ("equipamento", 2, "delete")
    assert _flashes(client) == [("success", "Equipamento excluído com sucesso.")]


def test_tipos_create_post_valid_preserves_redirect_flash_audit_and_cache(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post(
        "/tipos-treinamento/novo",
        data={"nome": "CQ IFR", "periodicidade_meses": "6", "exige_equipamento": "on", "ativo": "on"},
    )

    _assert_redirects_to(response, "/tipos-treinamento")
    assert fake_db.inserted_tipos == [("CQ IFR", 6, 1, 1)]
    assert fake_db.commits == 1
    assert side_effects["cache_clears"] == 1
    assert side_effects["audits"][0]["args"][1:4] == ("tipo_treinamento", 202, "create")
    assert _flashes(client) == [("success", "Tipo de treinamento cadastrado com sucesso.")]


def test_tipos_create_post_invalid_preserves_form_state_status_and_flash(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.post("/tipos-treinamento/novo", data={"nome": "CQ IFR", "periodicidade_meses": "0"})

    assert response.status_code == 400
    assert captured["template"] == "tipos_form.html"
    assert captured["context"]["tipo"]["nome"] == "CQ IFR"
    assert fake_db.inserted_tipos == []
    assert fake_db.commits == 0
    assert _flashes(client) == [("error", "O campo 'Periodicidade em meses' deve ser maior que zero.")]


def test_tipos_edit_get_existing_preserves_form_context(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.get("/tipos-treinamento/4/editar")

    assert response.status_code == 200
    assert captured["template"] == "tipos_form.html"
    assert captured["context"]["tipo"] == {
        "id": 4,
        "nome": "CQ IFR",
        "periodicidade_meses": 6,
        "exige_equipamento": 1,
        "ativo": 1,
    }


def test_tipos_edit_get_missing_preserves_404(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    _patch_catalogos_db(monkeypatch, _CatalogosDB(missing_tipo_ids={999}))

    response = client.get("/tipos-treinamento/999/editar")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_tipos_edit_post_valid_preserves_redirect_flash_audit_and_cache(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post(
        "/tipos-treinamento/4/editar",
        data={"nome": "CQ IFR Atualizado", "periodicidade_meses": "12", "ativo": "on"},
    )

    _assert_redirects_to(response, "/tipos-treinamento")
    assert fake_db.updated_tipos == [("CQ IFR Atualizado", 12, 0, 1, 4)]
    assert fake_db.commits == 1
    assert side_effects["cache_clears"] == 1
    assert side_effects["audits"][0]["args"][1:4] == ("tipo_treinamento", 4, "update")
    assert _flashes(client) == [("success", "Tipo de treinamento atualizado com sucesso.")]


def test_tipos_edit_post_invalid_preserves_form_state_status_and_flash(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    captured = _capture_render_template(monkeypatch)

    response = client.post("/tipos-treinamento/4/editar", data={"nome": "CQ IFR", "periodicidade_meses": "0"})

    assert response.status_code == 400
    assert captured["template"] == "tipos_form.html"
    assert captured["context"]["tipo"]["nome"] == "CQ IFR"
    assert fake_db.updated_tipos == []
    assert fake_db.commits == 0
    assert _flashes(client) == [("error", "O campo 'Periodicidade em meses' deve ser maior que zero.")]


def test_tipos_delete_with_linked_training_preserves_block_flash_and_redirect(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB(linked_tipo_ids={4})
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post("/tipos-treinamento/4/excluir")

    _assert_redirects_to(response, "/tipos-treinamento")
    assert fake_db.deleted_tipos == []
    assert fake_db.commits == 0
    assert side_effects["cache_clears"] == 0
    assert side_effects["audits"] == []
    assert _flashes(client) == [
        ("error", "Não é possível excluir o tipo de treinamento porque existem treinamentos vinculados.")
    ]


def test_tipos_delete_without_linked_training_preserves_delete_flash_audit_and_cache(monkeypatch):
    _app, client = _client_with_catalog_permissions(monkeypatch)
    fake_db = _CatalogosDB()
    _patch_catalogos_db(monkeypatch, fake_db)
    side_effects = _patch_catalog_side_effects(monkeypatch)

    response = client.post("/tipos-treinamento/4/excluir")

    _assert_redirects_to(response, "/tipos-treinamento")
    assert fake_db.deleted_tipos == [4]
    assert fake_db.commits == 1
    assert side_effects["cache_clears"] == 1
    assert side_effects["audits"][0]["args"][1:4] == ("tipo_treinamento", 4, "delete")
    assert _flashes(client) == [("success", "Tipo de treinamento excluído com sucesso.")]
