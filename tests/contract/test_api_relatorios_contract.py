from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.relatorios import routes as relatorios_api
from backend.src.controle_treinamentos.blueprints.cadastros import routes_treinamentos
from backend.src.controle_treinamentos.contracts.relatorios import habilitacoes_report_to_csv_export


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


DEFAULT_AUTH_PERMISSIONS = ["relatorio_habilitacoes:view"]


def _auth_user_row(permissions=None):
    permission_keys = DEFAULT_AUTH_PERMISSIONS if permissions is None else permissions
    return {
        "id": 51,
        "nome": "Operador Relatorios",
        "login": "rel_api",
        "email": "rel.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(permission_keys),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions=None):
    row = _auth_user_row(permissions)
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "rel_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def _canonical_habilitacoes_report():
    return {
        "emitted_at": "02/04/2026 12:00",
        "summary": {
            "total_tripulantes": 1,
            "total_habilitacoes": 1,
            "total_em_dia": 0,
            "total_vencer_90": 0,
            "total_vencer_60": 0,
            "total_vencer_30": 0,
            "total_critico_15": 0,
            "total_vencido": 1,
        },
        "filters": {"nome": "", "base": "SSA", "status": "vencido", "tipo": "", "ordenacao": "vencimento"},
        "options": {
            "status": [{"key": "vencido", "label": "Vencido", "badge_class": "status-critical"}],
            "tipos": [{"id": 2, "nome": "CQ IFR"}],
            "bases": [{"nome": "SSA", "uf": "BA"}],
        },
        "items": [
            {
                "tripulante_id": 7,
                "tripulante_nome": "Lucas Silva",
                "base": "SSA",
                "funcao_cargo": "Comandante",
                "habilitacoes": [
                    {
                        "treinamento_id": 55,
                        "tipo_treinamento_id": 2,
                        "habilitacao_nome": "CQ IFR",
                        "data_vencimento": "02/04/2026",
                        "days_remaining": -1,
                        "days_remaining_label": "Vencida ha 1 dia(s)",
                        "status_key": "vencido",
                        "status_label": "Vencido",
                        "pulse": True,
                        "is_placeholder": False,
                    },
                    {
                        "treinamento_id": None,
                        "tipo_treinamento_id": None,
                        "habilitacao_nome": "Sem habilitacoes cadastradas",
                        "data_vencimento": "Sem vencimento informado",
                        "days_remaining": None,
                        "days_remaining_label": "Sem vencimento informado",
                        "status_key": "sem_habilitacao",
                        "status_label": "Sem habilitacao",
                        "pulse": False,
                        "is_placeholder": True,
                    },
                ],
            }
        ],
    }


def test_api_relatorios_habilitacoes_returns_filterable_report_without_visual_fields(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(relatorios_api, "get_habilitacoes_report_data", lambda _db, **_kwargs: _canonical_habilitacoes_report())
    monkeypatch.setattr(relatorios_api, "get_db", lambda: object())

    response = client.get("/api/v1/relatorios/habilitacoes?base=SSA&status=vencido")

    assert response.status_code == 200
    payload = response.get_json()
    item = payload["report"]["items"][0]["habilitacoes"][0]
    assert payload["code"] == "relatorio_habilitacoes_ok"
    assert payload["report"]["emitted_at"] == "02/04/2026 12:00"
    assert item["status_key"] == "vencido"
    assert "status_class" not in item


def test_legacy_habilitacoes_html_and_print_use_canonical_report_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    report = _canonical_habilitacoes_report()
    captured = {"calls": []}

    def _get_report(_db, **kwargs):
        captured["request"] = kwargs
        return report

    def _render_template(template, **context):
        captured["calls"].append({"template": template, "context": context})
        return "ok"

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", _get_report)
    monkeypatch.setattr(routes_treinamentos, "render_template", _render_template)

    response = client.get("/treinamentos/consolidado?base=SSA&status=vencido&ordenacao=vencimento")

    assert response.status_code == 200
    assert captured["request"]["base"] == "SSA"
    assert captured["request"]["status"] == "vencido"
    assert captured["request"]["ordenacao"] == "vencimento"
    html_context = captured["calls"][-1]["context"]
    assert captured["calls"][-1]["template"] == "treinamentos_consolidado.html"
    assert html_context["emitted_at"] == "02/04/2026 12:00"
    assert html_context["filtros"] == report["filters"]
    assert html_context["summary"] == report["summary"]
    assert html_context["base_options"][0]["uf"] == "BA"
    assert html_context["tripulantes_grouped"][0]["habilitacoes"][0]["status_class"] == "status-critical"

    response = client.get("/treinamentos/consolidado/relatorio?base=SSA&status=vencido&ordenacao=vencimento")

    assert response.status_code == 200
    print_context = captured["calls"][-1]["context"]
    assert captured["calls"][-1]["template"] == "treinamentos_consolidado_relatorio.html"
    assert print_context["filtros_aplicados"] == {
        "nome": "-",
        "base": "SSA",
        "status": "vencido",
        "tipo": "-",
        "ordenacao": "vencimento",
    }
    assert print_context["emitted_at"] == "02/04/2026 12:00"


def test_habilitacoes_csv_export_uses_canonical_report_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def _get_report(_db, **kwargs):
        captured["request"] = kwargs
        return _canonical_habilitacoes_report()

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "get_habilitacoes_report_data", _get_report)
    monkeypatch.setattr(routes_treinamentos, "audit_document_generation", lambda **_kwargs: None)

    response = client.get(
        "/treinamentos/consolidado/export.csv?base=SSA&status=vencido&ordenacao=vencimento",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content_type == "text/csv; charset=utf-8"
    assert captured["request"]["status"] == "vencido"
    csv_payload = response.get_data(as_text=True)
    assert "Tripulante;Base;Funcao/Cargo;Habilitacao;Data de vencimento;Dias restantes;Status" in csv_payload
    assert "Lucas Silva;SSA;Comandante;CQ IFR;02/04/2026;Vencida ha 1 dia(s);Vencido" in csv_payload
    assert "Sem habilitacoes cadastradas" not in csv_payload


def test_habilitacoes_csv_adapter_defines_columns_and_formatting():
    export = habilitacoes_report_to_csv_export(_canonical_habilitacoes_report())

    assert export["content_type"] == "text/csv; charset=utf-8"
    assert export["delimiter"] == ";"
    assert export["columns"] == [
        "Tripulante",
        "Base",
        "Funcao/Cargo",
        "Habilitacao",
        "Data de vencimento",
        "Dias restantes",
        "Status",
    ]
    assert export["content"].startswith("\ufeff")
    assert "Tripulante;Base;Funcao/Cargo;Habilitacao;Data de vencimento;Dias restantes;Status" in export["content"]
    assert "Lucas Silva;SSA;Comandante;CQ IFR;02/04/2026;Vencida ha 1 dia(s);Vencido" in export["content"]
    assert "Sem habilitacoes cadastradas" not in export["content"]
