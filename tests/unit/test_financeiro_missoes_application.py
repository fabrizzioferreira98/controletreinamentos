from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application import financeiro_missoes as usecases
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_FILE = (
    REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "application" / "financeiro_missoes.py"
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


def _mission_row(**overrides):
    row = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "data_missao": "2026-04-10",
        "data_final": "2026-04-10",
        "cavok_numero_voo": "CAVOK-10",
        "contratante": "Cliente",
        "chamado": "CH-10",
        "aeronave_id": 7,
        "categoria_financeira_aeronave": "A",
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
        "horario_apresentacao": "2026-04-10 08:00:00",
        "horario_abandono": "2026-04-10 18:00:00",
        "pos_exec_min": 0,
        "trecho": "BSB-GRU",
        "houve_pernoite": False,
        "quantidade_pernoites": 0,
        "cobertura_base": False,
        "operacao_especial": None,
        "justificativa": None,
        "status": "ativa",
        "observacoes": "test",
    }
    row.update(overrides)
    return row


def _mission_detail(**overrides):
    row = _mission_row(**overrides)
    row["participantes"] = [
        {
            "id": 1,
            "org_id": row["org_id"],
            "missao_operacional_id": row["id"],
            "tripulante_id": row["comandante_tripulante_id"],
            "funcao": "comandante",
            "status": "ativo",
        },
        {
            "id": 2,
            "org_id": row["org_id"],
            "missao_operacional_id": row["id"],
            "tripulante_id": row["copiloto_tripulante_id"],
            "funcao": "copiloto",
            "status": "ativo",
        },
    ]
    return row


def _payload(**overrides):
    payload = {
        "competencia": "2026-04",
        "data_missao": "2026-04-10",
        "cavok_numero_voo": "CAVOK-10",
        "contratante": "Cliente",
        "chamado": "CH-10",
        "aeronave_id": 7,
        "categoria_financeira_aeronave": "A",
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
        "horario_apresentacao": "2026-04-10 08:00:00",
        "horario_abandono": "2026-04-10 18:00:00",
        "trecho": "BSB-GRU",
        "status": "ativa",
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

    source = APPLICATION_FILE.read_text(encoding="utf-8")
    assert violations == []
    assert "missao_financeira_id" not in source
    assert "financeiro_missoes_operacionais" not in source


def test_mission_payload_preserva_condicao_operacional_especial_com_compatibilidade_booleana():
    text_payload = usecases._mission_payload(
        _payload(operacao_especial="Palmas turboélice"),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
    )
    legacy_true_payload = usecases._mission_payload(
        _payload(operacao_especial=True),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
    )
    legacy_false_payload = usecases._mission_payload(
        _payload(operacao_especial=False),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
    )

    assert text_payload["operacao_especial"] == "Palmas turboélice"
    assert legacy_true_payload["operacao_especial"] == "especial"
    assert legacy_false_payload["operacao_especial"] is None


def test_mission_payload_persiste_data_final_pos_exec_e_justificativa_separados():
    payload = usecases._mission_payload(
        _payload(
            data_final="2026-04-12",
            pos_exec_min="20",
            quantidade_pernoites="2",
            cobertura_base=True,
            justificativa="Ajuste operacional documentado",
            operacao_especial="Palmas turboélice",
            observacoes="Observacao livre",
        ),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
    )

    assert payload["data_final"] == "2026-04-12"
    assert payload["pos_exec_min"] == 20
    assert payload["quantidade_pernoites"] == 2
    assert payload["houve_pernoite"] is True
    assert payload["cobertura_base"] is True
    assert payload["justificativa"] == "Ajuste operacional documentado"
    assert payload["operacao_especial"] == "Palmas turboélice"
    assert payload["observacoes"] == "Observacao livre"


def test_mission_payload_normaliza_horarios_time_only_da_grade_jornada():
    payload = usecases._mission_payload(
        _payload(
            horario_apresentacao="23:30",
            horario_abandono="01:10",
        ),
        org_id=FINANCE_ORG_SCOPE_DEFAULT,
        actor_user_id=55,
    )

    assert payload["horario_apresentacao"] == "2026-04-10T23:30"
    assert payload["horario_abandono"] == "2026-04-11T01:10"


def test_mission_payload_bloqueia_data_final_anterior_e_pos_exec_negativo():
    with pytest.raises(usecases.FinanceiroDominioErro) as invalid_date:
        usecases._mission_payload(
            _payload(data_final="2026-04-09"),
            org_id=FINANCE_ORG_SCOPE_DEFAULT,
            actor_user_id=55,
        )
    with pytest.raises(usecases.FinanceiroDominioErro) as invalid_pos:
        usecases._mission_payload(
            _payload(pos_exec_min="-1"),
            org_id=FINANCE_ORG_SCOPE_DEFAULT,
            actor_user_id=55,
        )

    assert invalid_date.value.code == "missao_operacional_data_final_invalida"
    assert invalid_pos.value.code == "financeiro_campo_invalido"


def test_criar_missao_operacional_orchestrates_repository_participants_commit_and_audit(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    created = _mission_row()
    detail = _mission_detail()

    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "find_duplicate_missao_operacional", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "create_missao_operacional_with_tripulantes", lambda *args, **kwargs: created)
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.criar_missao_operacional(_payload(), actor_user_id=55, db=db)

    assert result["id"] == 10
    assert result["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert {item["funcao"] for item in result["participantes"]} == {"comandante", "copiloto"}
    assert all("horario_apresentacao" not in item for item in result["participantes"])
    assert all("horario_abandono" not in item for item in result["participantes"])
    assert db.commit_count == 1
    assert db.conn.rollback_count == 0
    assert audit_calls[0]["acao"] == "finance.mission.created"
    assert audit_calls[0]["entidade"] == "finance_mission"
    assert audit_calls[0]["payload_anterior"] is None
    assert audit_calls[0]["payload_novo"]["mission"]["horario_apresentacao"]


def test_criar_missao_operacional_rejects_same_commander_and_copilot():
    db = _FakeDB()

    with pytest.raises(usecases.FinanceiroDominioErro) as exc_info:
        usecases.criar_missao_operacional(
            _payload(copiloto_tripulante_id=101),
            actor_user_id=55,
            db=db,
        )

    assert exc_info.value.code == "missao_operacional_tripulantes_iguais"
    assert db.commit_count == 0


def test_criar_missao_operacional_rejects_duplicate_and_rolls_back(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "find_duplicate_missao_operacional", lambda *args, **kwargs: _mission_row(id=99))

    with pytest.raises(usecases.MissaoOperacionalDuplicadaErro):
        usecases.criar_missao_operacional(_payload(), actor_user_id=55, db=db)

    assert db.commit_count == 0
    assert db.conn.rollback_count == 1


def test_competencia_fechada_bloqueia_mutation_e_competencia_ausente_permite(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(
        usecases,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: {"competencia": "2026-04", "status": "fechada"},
    )

    with pytest.raises(usecases.CompetenciaFinanceiraFechadaErro):
        usecases.validar_competencia_aberta_para_mutacao(db, competencia="2026-04")

    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    usecases.validar_competencia_aberta_para_mutacao(db, competencia="2026-04")


def test_atualizar_missao_operacional_audits_before_after_and_changed_fields(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(trecho="BSB-GRU")
    updated = _mission_row(trecho="BSB-CGH")
    detail = _mission_detail(trecho="BSB-CGH")

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "find_duplicate_missao_operacional", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "update_missao_operacional_row", lambda *args, **kwargs: updated)
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "invalidar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "invalidar_calculos_produtividade_vigentes_da_competencia", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.atualizar_missao_operacional(
        10,
        {"trecho": "BSB-CGH", "motivo": "ajuste operacional"},
        actor_user_id=55,
        db=db,
    )

    assert result["trecho"] == "BSB-CGH"
    assert db.commit_count == 1
    assert audit_calls[0]["acao"] == "finance.mission.updated"
    assert audit_calls[0]["payload_anterior"]["mission"]["trecho"] == "BSB-GRU"
    assert audit_calls[0]["payload_novo"]["mission"]["trecho"] == "BSB-CGH"
    assert "trecho" in audit_calls[0]["payload_novo"]["audit_metadata"]["changed_fields"]


def test_atualizar_missao_operacional_replaces_participants_when_crew_changes(monkeypatch):
    db = _FakeDB()
    replaced = []
    update_calls = []
    before = _mission_row(copiloto_tripulante_id=202)
    updated = _mission_row(copiloto_tripulante_id=303)
    detail = _mission_detail(copiloto_tripulante_id=303)

    def _update_mission(*args, **kwargs):
        update_calls.append(dict(kwargs["data"]))
        return updated

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "find_duplicate_missao_operacional", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "update_missao_operacional_row", _update_mission)
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "invalidar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "invalidar_calculos_produtividade_vigentes_da_competencia", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "replace_missao_tripulantes", lambda *args, **kwargs: replaced.append(kwargs) or [])
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: None)

    result = usecases.atualizar_missao_operacional(
        10,
        {
            "copiloto_tripulante_id": 303,
            "horario_apresentacao": "08:00",
            "horario_abandono": "12:30",
            "motivo": "troca controlada de copiloto",
        },
        actor_user_id=55,
        db=db,
    )

    assert result["copiloto_tripulante_id"] == 303
    assert update_calls[0]["horario_apresentacao"] == "2026-04-10T08:00"
    assert update_calls[0]["horario_abandono"] == "2026-04-10T12:30"
    assert replaced == [
        {
            "missao_operacional_id": 10,
            "comandante_tripulante_id": 101,
            "copiloto_tripulante_id": 303,
            "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        }
    ]
    assert db.commit_count == 1


def test_cancelar_missao_operacional_is_status_mutation_with_audit(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(status="ativa")
    cancelled = _mission_row(status="cancelada")
    detail = _mission_detail(status="cancelada")

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "cancel_missao_operacional_row", lambda *args, **kwargs: cancelled)
    monkeypatch.setattr(usecases, "cancel_missao_tripulantes", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "invalidar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "invalidar_calculos_produtividade_vigentes_da_competencia", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.cancelar_missao_operacional(10, actor_user_id=55, motivo="cancelamento", db=db)

    assert result["mission"]["status"] == "cancelada"
    assert result["calculation_status"] == "cancelada"
    assert result["affected_calculations"] == []
    assert result["action"] == "cancelled"
    assert db.commit_count == 1
    assert [call["acao"] for call in audit_calls] == [
        "finance.mission.cancel.requested",
        "finance.mission.cancelled",
    ]
    assert audit_calls[0]["payload_anterior"]["mission"]["status"] == "ativa"
    assert audit_calls[1]["payload_novo"]["mission"]["status"] == "cancelada"


def test_cancelar_missao_operacional_invalida_calculos_vigentes_e_preserva_missao(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(status="ativa")
    cancelled = _mission_row(status="cancelada")
    detail = _mission_detail(status="cancelada")
    invalidated = [
        {
            "id": 900,
            "org_id": FINANCE_ORG_SCOPE_DEFAULT,
            "missao_operacional_id": 10,
            "tripulante_id": 101,
            "funcao": "comandante",
            "status": "obsoleto",
            "previous_status": "calculado",
            "total": "100.00",
            "calculation_version": "finance-hourly-v1",
        }
    ]

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "cancel_missao_operacional_row", lambda *args, **kwargs: cancelled)
    monkeypatch.setattr(usecases, "cancel_missao_tripulantes", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "invalidar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [dict(item) for item in invalidated])
    monkeypatch.setattr(usecases, "invalidar_calculos_produtividade_vigentes_da_competencia", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.cancelar_missao_operacional(10, actor_user_id=55, motivo="cancelamento", db=db)

    assert result["mission"]["id"] == 10
    assert result["affected_calculations"] == [
        {"id": 900, "mission_id": 10, "tripulante_id": 101, "funcao": "comandante", "status": "obsoleto", "action": "invalidated"}
    ]
    assert result["warnings"][0]["code"] == "finance_calculation_invalidated_by_mission_cancel"
    assert "finance.calculation.invalidated_by_mission_cancel" in [call["acao"] for call in audit_calls]
    calculation_audit = next(call for call in audit_calls if call["acao"] == "finance.calculation.invalidated_by_mission_cancel")
    assert calculation_audit["payload_anterior"]["calculation"]["status"] == "calculado"
    assert calculation_audit["payload_novo"]["calculation"]["status"] == "obsoleto"


def test_cancelar_missao_operacional_e_idempotente_quando_ja_cancelada(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(status="cancelada")
    detail = _mission_detail(status="cancelada")

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "cancel_missao_operacional_row", lambda *args, **kwargs: pytest.fail("cancelamento idempotente nao deve mutar missao de novo"))
    monkeypatch.setattr(usecases, "invalidar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: pytest.fail("cancelamento idempotente nao deve invalidar de novo"))
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.cancelar_missao_operacional(10, actor_user_id=55, motivo="duplo clique", db=db)

    assert result["mission"]["status"] == "cancelada"
    assert result["action"] == "already_cancelled"
    assert result["affected_calculations"] == []
    assert result["warnings"][0]["code"] == "finance_mission_already_cancelled"
    assert audit_calls == []
    assert db.commit_count == 1


def test_cancelar_missao_operacional_bloqueia_competencia_fechada_e_audita_falha(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(status="ativa")

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(
        usecases,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: {"competencia": "2026-04", "status": "fechada"},
    )
    monkeypatch.setattr(usecases, "cancel_missao_operacional_row", lambda *args, **kwargs: pytest.fail("competencia fechada nao deve cancelar"))
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    with pytest.raises(usecases.CompetenciaFinanceiraFechadaErro):
        usecases.cancelar_missao_operacional(10, actor_user_id=55, motivo="bloqueio", db=db)

    assert db.conn.rollback_count == 1
    assert audit_calls[-1]["acao"] == "finance.mission.cancel.failed"


def test_excluir_missao_operacional_soft_delete_e_audit_sem_calculo(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(status="ativa")
    detail_before = _mission_detail(status="ativa")
    deleted_row = _mission_row(status="ativa", deleted_at="2026-05-04T13:00:00", deleted_by=55, delete_reason="erro")
    detail_after = _mission_detail(status="ativa", deleted_at="2026-05-04T13:00:00", deleted_by=55, delete_reason="erro")
    detail_after["participantes"] = [
        {**item, "status": "removido"}
        for item in detail_after["participantes"]
    ]

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        usecases,
        "fetch_missao_operacional_detail",
        lambda *args, **kwargs: detail_after if kwargs.get("include_deleted") else detail_before,
    )
    monkeypatch.setattr(
        usecases,
        "mission_delete_dependency_summary",
        lambda *args, **kwargs: {"calculos_horarios": 0, "calculos_produtividade": 0, "divergencias": 0},
    )
    monkeypatch.setattr(usecases, "remover_missao_tripulantes", lambda *args, **kwargs: detail_after["participantes"])
    monkeypatch.setattr(usecases, "soft_delete_missao_operacional", lambda *args, **kwargs: deleted_row)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.excluir_missao_operacional(10, actor_user_id=55, motivo="erro de lancamento", db=db)

    assert result["action"] == "deleted"
    assert result["deleted"] is True
    assert result["current_result"]["active"] is False
    assert result["affected_dependencies"]["participantes"] == 2
    assert db.commit_count == 1
    assert [call["acao"] for call in audit_calls] == [
        "finance.mission.delete.requested",
        "finance.mission.deleted",
    ]
    assert audit_calls[-1]["payload_novo"]["mission"]["is_deleted"] is True


def test_excluir_missao_operacional_bloqueia_quando_tem_calculo(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    before = _mission_row(status="ativa")
    detail_before = _mission_detail(status="ativa")

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: before)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail_before)
    monkeypatch.setattr(
        usecases,
        "mission_delete_dependency_summary",
        lambda *args, **kwargs: {"calculos_horarios": 1, "calculos_produtividade": 0, "divergencias": 0},
    )
    monkeypatch.setattr(usecases, "soft_delete_missao_operacional", lambda *args, **kwargs: pytest.fail("missao com calculo nao deve ser excluida"))
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    with pytest.raises(usecases.MissaoOperacionalExclusaoBloqueadaErro) as exc_info:
        usecases.excluir_missao_operacional(10, actor_user_id=55, motivo="erro", db=db)

    assert exc_info.value.status == 409
    assert exc_info.value.details["dependencies"]["calculos_horarios"] == 1
    assert db.commit_count == 1
    assert [call["acao"] for call in audit_calls] == [
        "finance.mission.delete.requested",
        "finance.mission.delete.blocked",
    ]


def test_excluir_missao_operacional_e_idempotente_quando_ja_excluida(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    deleted = _mission_row(deleted_at="2026-05-04T13:00:00", deleted_by=55, delete_reason="erro")
    detail = _mission_detail(deleted_at="2026-05-04T13:00:00", deleted_by=55, delete_reason="erro")

    monkeypatch.setattr(usecases, "fetch_missao_operacional", lambda *args, **kwargs: deleted)
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: detail)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: pytest.fail("exclusao idempotente nao deve travar novamente"))
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.excluir_missao_operacional(10, actor_user_id=55, motivo="duplo clique", db=db)

    assert result["action"] == "already_deleted"
    assert result["deleted"] is True
    assert result["warnings"][0]["code"] == "finance_mission_already_deleted"
    assert audit_calls == []
    assert db.commit_count == 1


def test_listar_and_detalhar_return_serializable_contracts(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(usecases, "list_missoes_operacionais_rows", lambda *args, **kwargs: [_mission_row()])
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: _mission_detail())

    collection = usecases.listar_missoes_operacionais(competencia="2026-04", db=db)
    detail = usecases.detalhar_missao_operacional(10, db=db)

    assert collection["items"][0]["id"] == 10
    assert collection["pagination"]["total"] == 1
    assert detail["id"] == 10
    assert {item["funcao"] for item in detail["participantes"]} == {"comandante", "copiloto"}


def test_recalcular_missao_operacional_calcula_persiste_e_audita(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    mission = _mission_detail(horario_apresentacao="2026-04-10 18:00:00", horario_abandono="2026-04-10 19:45:00")
    saved_rows = []

    def _parameter(*_args, tipo, funcao=None, **_kwargs):
        values = {
            "duracao_hora_noturna_minutos": "52.5",
            "periodo_diurno_inicio": "360",
            "periodo_diurno_fim": "1080",
            ("adicional_noturno", "comandante"): "100",
            ("domingo_feriado_diurno", "comandante"): "300",
            ("domingo_feriado_noturno", "comandante"): "400",
            ("adicional_noturno", "copiloto"): "80",
            ("domingo_feriado_diurno", "copiloto"): "200",
            ("domingo_feriado_noturno", "copiloto"): "250",
        }
        value = values.get((tipo, funcao), values.get(tipo))
        return {
            "id": len(str(tipo)) + (1 if funcao == "comandante" else 2 if funcao == "copiloto" else 0),
            "tipo": tipo,
            "funcao": funcao,
            "categoria": None,
            "valor": value,
            "unidade": (
                "minutos"
                if tipo == "duracao_hora_noturna_minutos"
                else "minutos_do_dia"
                if tipo in {"periodo_diurno_inicio", "periodo_diurno_fim"}
                else "valor"
            ),
            "vigencia_inicio": "2026-04-01",
            "vigencia_fim": None,
        }

    def _list_parameters(*args, **kwargs):
        return [_parameter(*args, **kwargs)]

    def _save(_db, *, data, org_id=None):
        row = {
            **data,
            "id": 900 + len(saved_rows),
            "org_id": org_id or FINANCE_ORG_SCOPE_DEFAULT,
            "minutos_noturnos": data["minutos_noturnos_reais"],
        }
        saved_rows.append(row)
        return row

    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "listar_parametros_financeiros_rows", _list_parameters)
    monkeypatch.setattr(usecases, "obsoletar_calculos_vigentes_duplicados_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "listar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "salvar_ou_atualizar_calculo_horario_vigente", _save)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    result = usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

    assert db.commit_count == 1
    assert len(result["calculations"]) == 2
    assert {item["funcao"] for item in result["calculations"]} == {"comandante", "copiloto"}
    comandante = next(item for item in result["calculations"] if item["funcao"] == "comandante")
    copiloto = next(item for item in result["calculations"] if item["funcao"] == "copiloto")
    assert comandante["horas_noturnas_convertidas"] == "2.0000"
    assert comandante["valor_adicional_noturno"] == "200.00"
    assert copiloto["valor_adicional_noturno"] == "160.00"
    assert saved_rows[0]["memoria_calculo"]["steps"][2]["parametro_usado"]["valor"] == "52.5"
    assert [call["acao"] for call in audit_calls] == [
        "finance.mission.recalculation.requested",
        "finance.hourly_bonus.calculated",
        "finance.hourly_bonus.calculated",
        "finance.mission.recalculated",
    ]
    assert audit_calls[-1]["payload_novo"]["audit_metadata"]["calculation_version"] == "finance-hourly-v1"
    assert result["mission_id"] == 10
    assert result["calculation_status"] == "calculado"
    assert result["affected_calculations"][0]["action"] == "updated"
    assert result["current_result"]["total"] == "360.00"


def test_recalcular_missao_operacional_usa_ids_da_missao_quando_participantes_estao_ausentes(monkeypatch):
    db = _FakeDB()
    mission = _mission_detail()
    mission["participantes"] = []
    calculation_calls = []
    saved_rows = []

    def _calculate(*, missao_operacional, participante, **_kwargs):
        calculation_calls.append(participante)
        return {
            "mission_id": missao_operacional["id"],
            "missao_operacional_id": missao_operacional["id"],
            "tripulante_id": participante["tripulante_id"],
            "funcao": participante["funcao"],
            "jornada_total_minutos": 0,
            "minutos_diurnos": 0,
            "minutos_noturnos": 0,
            "minutos_noturnos_reais": 0,
            "horas_noturnas_convertidas": "0.0000",
            "minutos_pre": 0,
            "minutos_pos": 0,
            "domingo_feriado": False,
            "valor_adicional_noturno": "0.00",
            "valor_domingo_feriado_diurno": "0.00",
            "valor_domingo_feriado_noturno": "0.00",
            "valor_pre": "0.00",
            "valor_pos": "0.00",
            "total": "0.00",
            "memoria_calculo": {"steps": []},
            "parametros_usados": [],
            "calculation_version": "finance-hourly-v1",
        }

    def _save(_db, *, data, org_id=None):
        row = {
            **data,
            "id": 900 + len(saved_rows),
            "org_id": org_id or FINANCE_ORG_SCOPE_DEFAULT,
            "status": "calculado",
        }
        saved_rows.append(row)
        return row

    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "_buscar_parametros_vigentes", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "calcular_bonificacao_horaria", _calculate)
    monkeypatch.setattr(usecases, "obsoletar_calculos_vigentes_duplicados_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "listar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "salvar_ou_atualizar_calculo_horario_vigente", _save)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: None)

    result = usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

    assert db.commit_count == 1
    assert len(result["calculations"]) == 2
    assert {item["tripulante_id"] for item in calculation_calls} == {101, 202}
    assert {item["funcao"] for item in calculation_calls} == {"comandante", "copiloto"}


def test_recalcular_missao_operacional_e_idempotente_por_missao_tripulante_funcao(monkeypatch):
    db = _FakeDB()
    mission = _mission_detail()
    current_rows = {}
    writes = []
    audit_actions = []

    def _calculate(*, missao_operacional, participante, **_kwargs):
        return {
            "mission_id": missao_operacional["id"],
            "missao_operacional_id": missao_operacional["id"],
            "tripulante_id": participante["tripulante_id"],
            "funcao": participante["funcao"],
            "jornada_total_minutos": 60,
            "minutos_diurnos": 60,
            "minutos_noturnos": 0,
            "minutos_noturnos_reais": 0,
            "horas_noturnas_convertidas": "0.0000",
            "minutos_pre": 0,
            "minutos_pos": 0,
            "domingo_feriado": False,
            "valor_adicional_noturno": "0.00",
            "valor_domingo_feriado_diurno": "0.00",
            "valor_domingo_feriado_noturno": "0.00",
            "valor_pre": "10.00",
            "valor_pos": "0.00",
            "total": "10.00",
            "memoria_calculo": {"steps": []},
            "parametros_usados": [],
            "calculation_version": "finance-hourly-v1",
        }

    def _upsert(_db, *, data, org_id=None):
        key = (data["tripulante_id"], data["funcao"])
        existing = current_rows.get(key)
        row = {
            **data,
            "id": existing["id"] if existing else 900 + len(current_rows),
            "org_id": org_id or FINANCE_ORG_SCOPE_DEFAULT,
            "status": "calculado",
            "persistence_action": "updated" if existing else "inserted",
            "minutos_noturnos": data.get("minutos_noturnos_reais", 0),
        }
        current_rows[key] = row
        writes.append(row)
        return row

    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "_buscar_parametros_vigentes", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "calcular_bonificacao_horaria", _calculate)
    monkeypatch.setattr(usecases, "obsoletar_calculos_vigentes_duplicados_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "listar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: list(current_rows.values()))
    monkeypatch.setattr(usecases, "salvar_ou_atualizar_calculo_horario_vigente", _upsert)
    monkeypatch.setattr(
        usecases,
        "create_missao_operacional_with_tripulantes",
        lambda *args, **kwargs: pytest.fail("recalculo nao pode criar missao operacional"),
    )
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_actions.append(kwargs["acao"]))

    first = usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)
    second = usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

    assert len(current_rows) == 2
    assert [item["id"] for item in first["calculations"]] == [item["id"] for item in second["calculations"]]
    assert {row["persistence_action"] for row in writes[:2]} == {"inserted"}
    assert {row["persistence_action"] for row in writes[2:]} == {"updated"}
    assert len([acao for acao in audit_actions if acao == "finance.mission.recalculated"]) == 2
    assert "finance.calculation.updated" in audit_actions


def test_recalcular_missao_operacional_obsoleta_duplicidades_vigentes_preexistentes(monkeypatch):
    db = _FakeDB()
    mission = _mission_detail()
    audit_actions = []
    duplicate = {
        "id": 777,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "missao_operacional_id": 10,
        "tripulante_id": 101,
        "funcao": "comandante",
        "status": "obsoleto",
        "total": "10.00",
    }

    def _calculate(*, missao_operacional, participante, **_kwargs):
        return {
            "mission_id": missao_operacional["id"],
            "missao_operacional_id": missao_operacional["id"],
            "tripulante_id": participante["tripulante_id"],
            "funcao": participante["funcao"],
            "jornada_total_minutos": 0,
            "minutos_diurnos": 0,
            "minutos_noturnos": 0,
            "minutos_noturnos_reais": 0,
            "horas_noturnas_convertidas": "0.0000",
            "minutos_pre": 0,
            "minutos_pos": 0,
            "domingo_feriado": False,
            "valor_adicional_noturno": "0.00",
            "valor_domingo_feriado_diurno": "0.00",
            "valor_domingo_feriado_noturno": "0.00",
            "valor_pre": "0.00",
            "valor_pos": "0.00",
            "total": "0.00",
            "memoria_calculo": {"steps": []},
            "parametros_usados": [],
            "calculation_version": "finance-hourly-v1",
        }

    def _upsert(_db, *, data, org_id=None):
        return {
            **data,
            "id": 900 + (1 if data["funcao"] == "copiloto" else 0),
            "org_id": org_id or FINANCE_ORG_SCOPE_DEFAULT,
            "status": "calculado",
            "persistence_action": "updated",
            "minutos_noturnos": data.get("minutos_noturnos_reais", 0),
        }

    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "_buscar_parametros_vigentes", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "calcular_bonificacao_horaria", _calculate)
    monkeypatch.setattr(usecases, "obsoletar_calculos_vigentes_duplicados_da_missao", lambda *args, **kwargs: [duplicate])
    monkeypatch.setattr(usecases, "listar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "salvar_ou_atualizar_calculo_horario_vigente", _upsert)
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_actions.append(kwargs["acao"]))

    result = usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

    assert result["warnings"][0]["code"] == "finance_calculation_duplicates_superseded"
    assert "finance.calculation.superseded" in audit_actions


def test_recalcular_missao_operacional_faz_rollback_e_audita_falha(monkeypatch):
    db = _FakeDB()
    mission = _mission_detail()
    audit_actions = []
    writes = []

    def _calculate(**_kwargs):
        raise usecases.FinanceiroDominioErro("Parametros ausentes.", code="financeiro_parametros_ausentes")

    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: mission)
    monkeypatch.setattr(usecases, "fetch_competencia_financeira", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(usecases, "_buscar_parametros_vigentes", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "calcular_bonificacao_horaria", _calculate)
    monkeypatch.setattr(usecases, "obsoletar_calculos_vigentes_duplicados_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "listar_calculos_horarios_vigentes_da_missao", lambda *args, **kwargs: [])
    monkeypatch.setattr(usecases, "salvar_ou_atualizar_calculo_horario_vigente", lambda *args, **kwargs: writes.append(kwargs))
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: audit_actions.append(kwargs["acao"]))

    with pytest.raises(usecases.FinanceiroDominioErro):
        usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

    assert db.conn.rollback_count == 1
    assert writes == []
    assert "finance.calculation.failed" in audit_actions


def test_recalcular_missao_operacional_bloqueia_cancelada_e_competencia_fechada(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: _mission_detail(status="cancelada"))

    with pytest.raises(usecases.MissaoOperacionalCanceladaErro):
        usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: _mission_detail())
    monkeypatch.setattr(usecases, "lock_missao_operacional", lambda *args, **kwargs: _mission_detail())
    monkeypatch.setattr(
        usecases,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: {"competencia": "2026-04", "status": "fechada"},
    )
    monkeypatch.setattr(usecases, "record_audit_event", lambda *args, **kwargs: None)
    with pytest.raises(usecases.CompetenciaFinanceiraFechadaErro):
        usecases.recalcular_missao_operacional(10, actor_user_id=55, db=db)

