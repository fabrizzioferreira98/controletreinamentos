from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application import financeiro_parametros as usecases
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "application" / "financeiro_parametros.py"
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


def _parameter_row(**overrides):
    row = {
        "id": 1,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "tipo": "duracao_hora_noturna_minutos",
        "funcao": None,
        "categoria": None,
        "valor": Decimal("52.5"),
        "unidade": "minutos",
        "vigencia_inicio": "2026-04-01",
        "vigencia_fim": None,
        "status": "ativo",
        "motivo": "baseline",
        "created_by": 55,
        "updated_by": 55,
    }
    row.update(overrides)
    return row


def _payload(**overrides):
    payload = {
        "tipo": "duracao_hora_noturna_minutos",
        "valor": "52.5",
        "unidade": "minutos",
        "vigencia_inicio": "2026-04-01",
        "vigencia_fim": None,
        "motivo": "hora noturna parametrizada",
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


def test_criar_parametro_financeiro_accepts_52_5_minutes_and_audits(monkeypatch):
    db = _FakeDB()
    audit_calls = []

    monkeypatch.setattr(usecases, "verificar_sobreposicao_vigencia", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "criar_parametro_financeiro_row", lambda *args, **kwargs: _parameter_row())
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.criar_parametro_financeiro(_payload(), actor_user_id=55, db=db)

    assert result["tipo"] == "duracao_hora_noturna_minutos"
    assert result["valor"] == "52.5"
    assert result["unidade"] == "minutos"
    assert result["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert db.commit_count == 1
    assert db.conn.rollback_count == 0
    assert audit_calls[0]["acao"] == "finance.parameter.created"
    assert audit_calls[0]["entidade"] == "finance_parameter"
    assert audit_calls[0]["payload_anterior"] is None
    assert audit_calls[0]["payload_novo"]["parameter"]["valor"] == "52.5"


def test_periodo_diurno_aceita_minutos_do_dia(monkeypatch):
    db = _FakeDB()
    created_rows = []

    def _create_parameter(_db, *, data, **_kwargs):
        created_rows.append(data)
        return _parameter_row(
            tipo=data["tipo"],
            valor=data["valor"],
            unidade=data["unidade"],
            motivo=data["motivo"],
        )

    monkeypatch.setattr(usecases, "verificar_sobreposicao_vigencia", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "criar_parametro_financeiro_row", _create_parameter)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: None)

    inicio = usecases.criar_parametro_financeiro(
        _payload(
            tipo="periodo_diurno_inicio",
            valor="360",
            unidade="minutos_do_dia",
            motivo="periodo inicio",
        ),
        actor_user_id=55,
        db=db,
    )
    fim = usecases.criar_parametro_financeiro(
        _payload(
            tipo="periodo_diurno_fim",
            valor="1080",
            unidade="minutos_do_dia",
            motivo="periodo fim",
        ),
        actor_user_id=55,
        db=db,
    )

    assert inicio["tipo"] == "periodo_diurno_inicio"
    assert inicio["valor"] == "360"
    assert inicio["unidade"] == "minutos_do_dia"
    assert fim["tipo"] == "periodo_diurno_fim"
    assert fim["valor"] == "1080"
    assert fim["unidade"] == "minutos_do_dia"
    assert created_rows[0]["valor"] == Decimal("360")
    assert created_rows[1]["valor"] == Decimal("1080")


def test_parametros_horarios_globais_ignoram_funcao_no_payload(monkeypatch):
    db = _FakeDB()
    created_rows = []

    def _create_parameter(_db, *, data, **_kwargs):
        created_rows.append(data)
        return _parameter_row(
            tipo=data["tipo"],
            funcao=data.get("funcao"),
            valor=data["valor"],
            unidade=data["unidade"],
            motivo=data["motivo"],
        )

    monkeypatch.setattr(usecases, "verificar_sobreposicao_vigencia", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "criar_parametro_financeiro_row", _create_parameter)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: None)

    created = usecases.criar_parametro_financeiro(
        _payload(
            tipo="duracao_hora_noturna_minutos",
            unidade="minutos",
            valor="52.5",
            funcao="Comandante",
        ),
        actor_user_id=55,
        db=db,
    )

    assert created_rows[0]["funcao"] is None
    assert created["funcao"] is None


def test_criar_parametro_pernoite_comum_exige_funcao_e_audita(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    created_rows = []

    def _create_parameter(_db, *, data, **_kwargs):
        created_rows.append(data)
        return _parameter_row(
            tipo=data["tipo"],
            funcao=data["funcao"],
            valor=data["valor"],
            unidade=data["unidade"],
            motivo=data["motivo"],
        )

    monkeypatch.setattr(usecases, "verificar_sobreposicao_vigencia", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "criar_parametro_financeiro_row", _create_parameter)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.criar_parametro_financeiro(
        _payload(
            tipo="pernoite_comum_sem_cobertura",
            unidade="valor",
            valor="80.00",
            funcao="Comandante",
            motivo="Valor aprovado para pernoite comum sem cobertura; GOV_CLASS=hml-release-candidate",
        ),
        actor_user_id=55,
        db=db,
    )

    assert result["tipo"] == "pernoite_comum_sem_cobertura"
    assert created_rows[0]["funcao"] == "comandante"
    assert created_rows[0]["unidade"] == "valor"
    assert audit_calls[0]["acao"] == "finance.parameter.created"


def test_parametro_pernoite_comum_sem_funcao_e_bloqueado():
    db = _FakeDB()

    with pytest.raises(usecases.ParametroFinanceiroInvalidoErro) as exc:
        usecases.criar_parametro_financeiro(
            _payload(
                tipo="pernoite_comum_sem_cobertura",
                unidade="valor",
                valor="80.00",
                funcao="",
            ),
            actor_user_id=55,
            db=db,
        )

    assert exc.value.code == "parametro_financeiro_funcao_obrigatoria"
    assert db.commit_count == 0


@pytest.mark.parametrize(
    ("tipo", "valor", "unidade"),
    [
        ("periodo_diurno_inicio", "06:00", "minutos_do_dia"),
        ("periodo_diurno_fim", "18:00", "minutos_do_dia"),
        ("periodo_diurno_inicio", "6", "minutos_do_dia"),
        ("periodo_diurno_fim", "18", "minutos_do_dia"),
        ("periodo_diurno_inicio", "-1", "minutos_do_dia"),
        ("periodo_diurno_fim", "1440", "minutos_do_dia"),
        ("periodo_diurno_inicio", "360", "horario"),
    ],
)
def test_periodo_diurno_rejeita_contrato_invalido(tipo, valor, unidade):
    db = _FakeDB()

    with pytest.raises(usecases.ParametroFinanceiroInvalidoErro):
        usecases.criar_parametro_financeiro(
            _payload(tipo=tipo, valor=valor, unidade=unidade),
            actor_user_id=55,
            db=db,
        )

    assert db.commit_count == 0


def test_create_rejects_invalid_validity_required_value_and_overlap(monkeypatch):
    db = _FakeDB()
    with pytest.raises(usecases.ParametroFinanceiroInvalidoErro) as invalid_validity:
        usecases.criar_parametro_financeiro(
            _payload(vigencia_inicio="2026-05-01", vigencia_fim="2026-04-30"),
            actor_user_id=55,
            db=db,
        )
    assert invalid_validity.value.code == "parametro_financeiro_vigencia_invalida"

    with pytest.raises(usecases.ParametroFinanceiroInvalidoErro) as missing_value:
        usecases.criar_parametro_financeiro(_payload(valor=""), actor_user_id=55, db=db)
    assert missing_value.value.code == "parametro_financeiro_campo_obrigatorio"

    monkeypatch.setattr(usecases, "verificar_sobreposicao_vigencia", lambda *args, **kwargs: _parameter_row(id=99))
    with pytest.raises(usecases.ParametroFinanceiroSobrepostoErro):
        usecases.criar_parametro_financeiro(_payload(), actor_user_id=55, db=db)
    assert db.commit_count == 0
    assert db.conn.rollback_count == 1


def test_update_parametro_financeiro_audits_before_after_and_changed_fields(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _parameter_row(valor=Decimal("52.5"))
    updated = _parameter_row(valor=Decimal("60"), motivo="ajuste")

    monkeypatch.setattr(usecases, "detalhar_parametro_financeiro", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "verificar_sobreposicao_vigencia", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "atualizar_parametro_financeiro_row", lambda *args, **kwargs: updated)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.atualizar_parametro_financeiro(
        1,
        {"valor": "60", "motivo": "ajuste"},
        actor_user_id=55,
        db=db,
    )

    assert result["valor"] == "60"
    assert db.commit_count == 1
    assert audit_calls[0]["acao"] == "finance.parameter.updated"
    assert audit_calls[0]["payload_anterior"]["parameter"]["valor"] == "52.5"
    assert audit_calls[0]["payload_novo"]["parameter"]["valor"] == "60"
    assert "valor" in audit_calls[0]["payload_novo"]["audit_metadata"]["changed_fields"]


def test_update_missing_parameter_and_current_lookup(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(usecases, "detalhar_parametro_financeiro", lambda *args, **kwargs: None)
    with pytest.raises(usecases.ParametroFinanceiroNaoEncontradoErro):
        usecases.atualizar_parametro_financeiro(999, {"valor": "60"}, actor_user_id=55, db=db)

    monkeypatch.setattr(usecases, "buscar_parametro_vigente_row", lambda *args, **kwargs: _parameter_row())
    current = usecases.buscar_parametro_vigente(
        tipo="duracao_hora_noturna_minutos",
        vigencia_em="2026-04-15",
        unidade="minutos",
        db=db,
    )
    assert current["valor"] == "52.5"


def test_update_parametro_rejects_empty_unknown_and_noop_payload(monkeypatch):
    db = _FakeDB()
    before = _parameter_row(valor=Decimal("52.5"), motivo="baseline")

    monkeypatch.setattr(usecases, "detalhar_parametro_financeiro", lambda *args, **kwargs: before)

    with pytest.raises(usecases.DomainValidationError) as empty_payload:
        usecases.atualizar_parametro_financeiro(1, {}, actor_user_id=55, db=db)
    assert empty_payload.value.code == "finance_parameter_patch_empty_or_invalid"

    with pytest.raises(usecases.DomainValidationError) as unknown_field:
        usecases.atualizar_parametro_financeiro(1, {"foo": "bar"}, actor_user_id=55, db=db)
    assert unknown_field.value.code == "finance_parameter_patch_empty_or_invalid"

    with pytest.raises(usecases.DomainValidationError) as noop_payload:
        usecases.atualizar_parametro_financeiro(1, {"valor": "52.5"}, actor_user_id=55, db=db)
    assert noop_payload.value.code == "finance_parameter_patch_empty_or_invalid"

