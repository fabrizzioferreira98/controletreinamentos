from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application import financeiro_feriados as usecases
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "application" / "financeiro_feriados.py"
)


class _FakeConn:
    def __init__(self):
        self.rollback_count = 0

    def rollback(self):
        self.rollback_count += 1


class _FakeDB:
    def __init__(self):
        self.conn = _FakeConn()
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1


def _holiday_row(**overrides):
    row = {
        "id": 1,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "data": "2026-04-21",
        "nome": "Tiradentes",
        "tipo": "nacional",
        "localidade": None,
        "status": "ativo",
        "created_by": 55,
        "updated_by": 55,
    }
    row.update(overrides)
    return row


def _payload(**overrides):
    payload = {
        "data": "2026-04-21",
        "nome": "Tiradentes",
        "tipo": "nacional",
        "status": "ativo",
    }
    payload.update(overrides)
    return payload


def _import_candidates(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        candidates = [module] if module else []
        candidates.extend(f"{module}.{alias.name}" if module else alias.name for alias in node.names)
        return candidates
    return []


def test_application_use_case_does_not_import_flask_request_or_frontend():
    tree = ast.parse(APPLICATION_FILE.read_text(encoding="utf-8"), filename=str(APPLICATION_FILE))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        for candidate in _import_candidates(node):
            if candidate.startswith("flask") or "request" in candidate or "frontend" in candidate:
                violations.append(f"{node.lineno}: import '{candidate}'")

    assert violations == []


def test_criar_feriado_nacional_normalizes_localidade_and_audits(monkeypatch):
    db = _FakeDB()
    audit_calls = []

    monkeypatch.setattr(usecases, "verificar_duplicidade_feriado_nacional", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "criar_feriado_nacional_row", lambda *args, **kwargs: _holiday_row())
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.criar_feriado_nacional(
        _payload(localidade="Sao Paulo"),
        actor_user_id=55,
        db=db,
    )

    assert result["tipo"] == "nacional"
    assert result["localidade"] is None
    assert result["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert db.commit_count == 1
    assert db.conn.rollback_count == 0
    assert audit_calls[0]["acao"] == "finance.parameter.created"
    assert audit_calls[0]["entidade"] == "finance_holiday"
    assert audit_calls[0]["payload_novo"]["holiday"]["tipo"] == "nacional"
    assert audit_calls[0]["payload_novo"]["audit_metadata"]["entity_type"] == "finance_holiday"


def test_create_rejects_missing_fields_non_national_type_and_duplicate(monkeypatch):
    db = _FakeDB()
    with pytest.raises(usecases.FeriadoFinanceiroInvalidoErro) as missing_name:
        usecases.criar_feriado_nacional(_payload(nome=""), actor_user_id=55, db=db)
    assert missing_name.value.code == "feriado_financeiro_campo_obrigatorio"

    with pytest.raises(usecases.FeriadoFinanceiroInvalidoErro) as non_national:
        usecases.criar_feriado_nacional(_payload(tipo="municipal"), actor_user_id=55, db=db)
    assert non_national.value.code == "feriado_financeiro_tipo_invalido"

    monkeypatch.setattr(usecases, "verificar_duplicidade_feriado_nacional", lambda *args, **kwargs: _holiday_row(id=99))
    with pytest.raises(usecases.FeriadoFinanceiroDuplicadoErro):
        usecases.criar_feriado_nacional(_payload(), actor_user_id=55, db=db)
    assert db.commit_count == 0
    assert db.conn.rollback_count == 1


def test_update_feriado_nacional_audits_before_after_and_changed_fields(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _holiday_row(nome="Tiradentes")
    updated = _holiday_row(nome="Tiradentes Nacional")

    monkeypatch.setattr(usecases, "detalhar_feriado_nacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "verificar_duplicidade_feriado_nacional", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "atualizar_feriado_nacional_row", lambda *args, **kwargs: updated)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.atualizar_feriado_nacional(
        1,
        {"nome": "Tiradentes Nacional", "localidade": "DF"},
        actor_user_id=55,
        db=db,
    )

    assert result["nome"] == "Tiradentes Nacional"
    assert result["localidade"] is None
    assert db.commit_count == 1
    assert audit_calls[0]["acao"] == "finance.parameter.updated"
    assert audit_calls[0]["entidade"] == "finance_holiday"
    assert "nome" in audit_calls[0]["payload_novo"]["audit_metadata"]["changed_fields"]


def test_update_missing_holiday_and_date_lookup(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(usecases, "detalhar_feriado_nacional", lambda *args, **kwargs: None)
    with pytest.raises(usecases.FeriadoFinanceiroNaoEncontradoErro):
        usecases.atualizar_feriado_nacional(999, {"nome": "Natal"}, actor_user_id=55, db=db)

    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: _holiday_row())
    current = usecases.verificar_feriado_nacional(data="2026-04-21", db=db)
    assert current["nome"] == "Tiradentes"


def test_update_feriado_rejects_empty_unknown_and_noop_payload(monkeypatch):
    db = _FakeDB()
    before = _holiday_row(nome="Tiradentes")

    monkeypatch.setattr(usecases, "detalhar_feriado_nacional", lambda *args, **kwargs: before)

    with pytest.raises(usecases.DomainValidationError) as empty_payload:
        usecases.atualizar_feriado_nacional(1, {}, actor_user_id=55, db=db)
    assert empty_payload.value.code == "finance_holiday_patch_empty_or_invalid"

    with pytest.raises(usecases.DomainValidationError) as unknown_field:
        usecases.atualizar_feriado_nacional(1, {"foo": "bar"}, actor_user_id=55, db=db)
    assert unknown_field.value.code == "finance_holiday_patch_empty_or_invalid"

    with pytest.raises(usecases.DomainValidationError) as noop_payload:
        usecases.atualizar_feriado_nacional(1, {"nome": "Tiradentes"}, actor_user_id=55, db=db)
    assert noop_payload.value.code == "finance_holiday_patch_empty_or_invalid"
