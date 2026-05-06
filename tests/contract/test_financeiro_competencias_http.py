from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.application.financeiro_competencias import (
    CompetenciaFinanceiraJaFechadaErro,
    CompetenciaFinanceiraNaoEncontradaErro,
    CompetenciaFinanceiraNaoFechadaErro,
    MotivoReaberturaObrigatorioErro,
    ParametrosNaoElegiveisFechamentoRealErro,
)
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


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


def _auth_user_row(*, permissions, login: str = "finance_period_http_user"):
    return {
        "id": 951,
        "nome": "Finance Period HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_period_http_user") -> str:
    fake_db = _SingleUserDB(_auth_user_row(permissions=permissions, login=login))
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": login, "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200
    return client.get("/api/v1/session").get_json()["csrf_token"]


def _headers(*, request_id: str = "finance-period-http", csrf_token: str | None = None) -> dict:
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": request_id,
        "X-Correlation-ID": f"{request_id}-correlation",
    }
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    return headers


def _assert_envelope(response, *, status: int, success: bool):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is success
    assert payload["status"] == status
    assert payload["code"]
    assert payload["message"]
    assert payload["request_id"]
    assert payload["correlation_id"]
    return payload


def _period_response(status="em_conferencia"):
    return {
        "period": {
            "id": 7,
            "org_id": FINANCE_ORG_SCOPE_DEFAULT,
            "competencia": "2026-04",
            "status": status,
            "totals": {"total_geral": "300.00"},
            "snapshot": {"missoes_operacionais": [], "totals": {"total_geral": "300.00"}},
        },
        "snapshot": {"missoes_operacionais": [], "totals": {"total_geral": "300.00"}},
        "totals": {"total_geral": "300.00"},
        "divergences": [],
    }


def test_period_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get("/api/v1/financeiro/competencias/2026-04", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_period_no_scope",
    )
    response = no_scope_client.post(
        "/api/v1/financeiro/competencias/2026-04/fechar",
        headers=_headers(request_id="finance-period-forbidden", csrf_token=csrf_token),
        json={"confirm": True},
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_period_detail_recalculate_close_and_reopen_delegate_to_use_cases(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_period_authorized",
    )
    calls = []

    def _detail(competencia, **kwargs):
        calls.append(("detail", competencia, kwargs))
        return _period_response()

    def _recalculate(competencia, **kwargs):
        calls.append(("recalculate", competencia, kwargs))
        return {
            **_period_response(),
            "items": [{"tripulante_id": 101, "total_devido": "200.00"}],
            "calculation_memory": {"snapshot_version": "finance-period-snapshot-v1"},
        }

    def _close(competencia, payload, **kwargs):
        calls.append(("close", competencia, payload, kwargs))
        return _period_response(status="fechada")

    def _reopen(competencia, payload, **kwargs):
        calls.append(("reopen", competencia, payload, kwargs))
        return {"period": _period_response(status="reaberta")["period"]}

    monkeypatch.setattr(financeiro_routes, "detalhar_competencia_financeira", _detail)
    monkeypatch.setattr(financeiro_routes, "recalcular_competencia_financeira", _recalculate)
    monkeypatch.setattr(financeiro_routes, "fechar_competencia_financeira", _close)
    monkeypatch.setattr(financeiro_routes, "reabrir_competencia_financeira", _reopen)

    detail = client.get("/api/v1/financeiro/competencias/2026-04", headers=_headers(request_id="period-detail"))
    detail_payload = _assert_envelope(detail, status=200, success=True)
    assert detail_payload["period"]["status"] == "em_conferencia"
    assert detail_payload["snapshot"]["missoes_operacionais"] == []

    recalculated = client.post(
        "/api/v1/financeiro/competencias/2026-04/recalcular",
        headers=_headers(request_id="period-recalc", csrf_token=csrf_token),
        json={},
    )
    recalculated_payload = _assert_envelope(recalculated, status=200, success=True)
    assert recalculated_payload["period"]["status"] == "em_conferencia"
    assert recalculated_payload["calculation_memory"]["snapshot_version"] == "finance-period-snapshot-v1"

    closed = client.post(
        "/api/v1/financeiro/competencias/2026-04/fechar",
        headers=_headers(request_id="period-close", csrf_token=csrf_token),
        json={"confirm": True, "motivo": "fechamento mensal"},
    )
    closed_payload = _assert_envelope(closed, status=200, success=True)
    assert closed_payload["period"]["status"] == "fechada"
    assert closed_payload["totals"]["total_geral"] == "300.00"

    reopened = client.post(
        "/api/v1/financeiro/competencias/2026-04/reabrir",
        headers=_headers(request_id="period-reopen", csrf_token=csrf_token),
        json={"motivo": "ajuste autorizado"},
    )
    reopened_payload = _assert_envelope(reopened, status=200, success=True)
    assert reopened_payload["period"]["status"] == "reaberta"

    assert [call[0] for call in calls] == ["detail", "recalculate", "close", "reopen"]
    assert calls[2][2]["confirm"] is True
    assert calls[3][2]["motivo"] == "ajuste autorizado"


def test_period_report_pdf_requires_permission_and_streams_pdf(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get(
        "/api/v1/financeiro/competencias/2026-04/relatorio.pdf",
        headers=_headers(request_id="period-pdf-anonymous"),
    )
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"finance:periods:read"},
        login="finance_period_pdf_no_scope",
    )
    response = no_scope_client.get(
        "/api/v1/financeiro/competencias/2026-04/relatorio.pdf",
        headers=_headers(request_id="period-pdf-forbidden", csrf_token=csrf_token),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"

    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_period_pdf_authorized",
    )
    calls = []

    def _report(competencia, **kwargs):
        calls.append((competencia, kwargs))
        return {
            "content": b"%PDF-1.4\n% test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
            "filename": "relatorio-financeiro-2026-04-previa.pdf",
            "mimetype": "application/pdf",
        }

    monkeypatch.setattr(financeiro_routes, "gerar_relatorio_financeiro_competencia_pdf", _report)

    response = client.get(
        "/api/v1/financeiro/competencias/2026-04/relatorio.pdf",
        headers={**_headers(request_id="period-pdf-ok"), "Accept": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/pdf")
    assert response.data.startswith(b"%PDF-1.4")
    assert response.data.rstrip().endswith(b"%%EOF")
    assert "attachment" in response.headers["Content-Disposition"]
    assert "relatorio-financeiro-2026-04-previa.pdf" in response.headers["Content-Disposition"]
    assert calls[0][0] == "2026-04"
    assert calls[0][1]["actor_user_id"] == 951
    assert calls[0][1]["request_id"] == "period-pdf-ok"


def test_period_report_pdf_returns_404_when_competencia_does_not_exist(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_period_pdf_not_found",
    )

    monkeypatch.setattr(
        financeiro_routes,
        "gerar_relatorio_financeiro_competencia_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(CompetenciaFinanceiraNaoEncontradaErro()),
    )

    response = client.get(
        "/api/v1/financeiro/competencias/2099-12/relatorio.pdf",
        headers={**_headers(request_id="period-pdf-not-found"), "Accept": "application/pdf"},
    )
    payload = _assert_envelope(response, status=404, success=False)
    assert payload["code"] == "competencia_financeira_nao_encontrada"


def test_period_http_translates_domain_errors(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_period_errors",
    )

    monkeypatch.setattr(
        financeiro_routes,
        "fechar_competencia_financeira",
        lambda *args, **kwargs: (_ for _ in ()).throw(CompetenciaFinanceiraJaFechadaErro("2026-04")),
    )
    closed = client.post(
        "/api/v1/financeiro/competencias/2026-04/fechar",
        headers=_headers(request_id="period-already-closed", csrf_token=csrf_token),
        json={"confirm": True},
    )
    closed_payload = _assert_envelope(closed, status=409, success=False)
    assert closed_payload["code"] == "competencia_financeira_ja_fechada"

    monkeypatch.setattr(
        financeiro_routes,
        "fechar_competencia_financeira",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ParametrosNaoElegiveisFechamentoRealErro(
                competencia="2026-04",
                environment="hml",
                blocking_parameters=[{"parameter_id": 51, "reasons": ["classificacao_nao_elegivel:qa-smoke"]}],
            )
        ),
    )
    blocked = client.post(
        "/api/v1/financeiro/competencias/2026-04/fechar",
        headers=_headers(request_id="period-close-gate-blocked", csrf_token=csrf_token),
        json={"confirm": True},
    )
    blocked_payload = _assert_envelope(blocked, status=409, success=False)
    assert blocked_payload["code"] == "finance_parameters_not_release_eligible"
    assert blocked_payload["details"]["blocking_parameters"][0]["parameter_id"] == 51

    monkeypatch.setattr(
        financeiro_routes,
        "reabrir_competencia_financeira",
        lambda *args, **kwargs: (_ for _ in ()).throw(MotivoReaberturaObrigatorioErro()),
    )
    missing_reason = client.post(
        "/api/v1/financeiro/competencias/2026-04/reabrir",
        headers=_headers(request_id="period-reopen-no-reason", csrf_token=csrf_token),
        json={},
    )
    missing_reason_payload = _assert_envelope(missing_reason, status=400, success=False)
    assert missing_reason_payload["code"] == "competencia_financeira_reopen_reason_required"

    monkeypatch.setattr(
        financeiro_routes,
        "reabrir_competencia_financeira",
        lambda *args, **kwargs: (_ for _ in ()).throw(CompetenciaFinanceiraNaoFechadaErro("2026-04")),
    )
    not_closed = client.post(
        "/api/v1/financeiro/competencias/2026-04/reabrir",
        headers=_headers(request_id="period-reopen-not-closed", csrf_token=csrf_token),
        json={"motivo": "ajuste"},
    )
    not_closed_payload = _assert_envelope(not_closed, status=409, success=False)
    assert not_closed_payload["code"] == "competencia_financeira_nao_fechada"


def test_period_endpoints_reject_invalid_competencia_with_400(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_period_invalid_competencia",
    )

    calls = []

    monkeypatch.setattr(financeiro_routes, "detalhar_competencia_financeira", lambda *args, **kwargs: calls.append("detail"))
    monkeypatch.setattr(financeiro_routes, "preflight_calculo_competencia", lambda *args, **kwargs: calls.append("preflight"))
    monkeypatch.setattr(financeiro_routes, "gerar_relatorio_financeiro_competencia_pdf", lambda *args, **kwargs: calls.append("pdf"))
    monkeypatch.setattr(financeiro_routes, "recalcular_competencia_financeira", lambda *args, **kwargs: calls.append("recalc"))
    monkeypatch.setattr(financeiro_routes, "fechar_competencia_financeira", lambda *args, **kwargs: calls.append("close"))
    monkeypatch.setattr(financeiro_routes, "reabrir_competencia_financeira", lambda *args, **kwargs: calls.append("reopen"))

    endpoints = (
        ("GET", "/api/v1/financeiro/competencias/invalida", None),
        ("GET", "/api/v1/financeiro/competencias/invalida/preflight-calculo", None),
        ("GET", "/api/v1/financeiro/competencias/invalida/relatorio.pdf", None),
        ("POST", "/api/v1/financeiro/competencias/invalida/recalcular", {}),
        ("POST", "/api/v1/financeiro/competencias/invalida/fechar", {"confirm": True}),
        ("POST", "/api/v1/financeiro/competencias/invalida/reabrir", {"motivo": "ajuste"}),
    )

    for method, path, payload in endpoints:
        response = client.open(
            path,
            method=method,
            json=payload,
            headers=_headers(
                request_id=f"period-invalid-{method.lower()}",
                csrf_token=csrf_token if method in {"POST", "PATCH"} else None,
            ),
        )
        envelope = _assert_envelope(response, status=400, success=False)
        assert envelope["code"] == "finance_invalid_competence"

    assert calls == []


def test_period_endpoints_reject_invalid_competencia_month_formats(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_period_invalid_competencia_month",
    )

    invalid_values = ("2026-13", "2026-00", "202604")
    for competencia in invalid_values:
        recalc = client.post(
            f"/api/v1/financeiro/competencias/{competencia}/recalcular",
            headers=_headers(request_id=f"period-invalid-month-{competencia}", csrf_token=csrf_token),
            json={},
        )
        recalc_payload = _assert_envelope(recalc, status=400, success=False)
        assert recalc_payload["code"] == "finance_invalid_competence"

        report = client.get(
            f"/api/v1/financeiro/competencias/{competencia}/relatorio.pdf",
            headers={**_headers(request_id=f"period-invalid-pdf-{competencia}"), "Accept": "application/pdf"},
        )
        report_payload = _assert_envelope(report, status=400, success=False)
        assert report_payload["code"] == "finance_invalid_competence"
