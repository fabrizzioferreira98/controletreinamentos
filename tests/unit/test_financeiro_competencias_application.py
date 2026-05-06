from __future__ import annotations

import pytest

from backend.src.controle_treinamentos.application import financeiro_competencias
from backend.src.controle_treinamentos.application.financeiro_competencias import (
    CompetenciaFinanceiraJaFechadaErro,
    CompetenciaFinanceiraNaoFechadaErro,
    ConfirmacaoFechamentoObrigatoriaErro,
    MotivoReaberturaObrigatorioErro,
    ParametrosNaoElegiveisFechamentoRealErro,
    detalhar_competencia_financeira,
    fechar_competencia_financeira,
    reabrir_competencia_financeira,
    recalcular_competencia_financeira,
)
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


class _FakeConn:
    def __init__(self):
        self.rollback_called = False

    def rollback(self):
        self.rollback_called = True


class _FakeDB:
    def __init__(self):
        self.conn = _FakeConn()
        self.committed = False

    def commit(self):
        self.committed = True


def _period_row(**overrides):
    payload = {
        "id": 7,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "status": "em_conferencia",
        "totals_snapshot": {"total_geral": "300.00"},
        "fechamento_snapshot": None,
        "closed_by": None,
        "closed_at": None,
        "reopen_reason": None,
    }
    payload.update(overrides)
    return payload


def _active_parameter(
    parameter_id: int,
    *,
    tipo: str,
    valor: str,
    unidade: str,
    funcao: str | None = None,
    categoria: str | None = None,
    motivo: str = "oficial; GOV_CLASS=hml-release-candidate",
    vigencia_inicio: str = "2026-01-01",
    vigencia_fim: str | None = None,
    status: str = "ativo",
) -> dict:
    return {
        "id": parameter_id,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "tipo": tipo,
        "funcao": funcao,
        "categoria": categoria,
        "valor": valor,
        "unidade": unidade,
        "vigencia_inicio": vigencia_inicio,
        "vigencia_fim": vigencia_fim,
        "status": status,
        "motivo": motivo,
    }


def _configure_close_flow(monkeypatch):
    audit_calls = []
    monkeypatch.setattr(financeiro_competencias, "fetch_competencia_financeira", lambda *args, **kwargs: _period_row())
    monkeypatch.setattr(
        financeiro_competencias,
        "fechar_competencia_row",
        lambda *args, **kwargs: _period_row(
            status="fechada",
            totals_snapshot=kwargs["totals"],
            fechamento_snapshot=kwargs["snapshot"],
            closed_by=kwargs["closed_by"],
            closed_at="2026-04-30T12:00:00",
        ),
    )
    monkeypatch.setattr(financeiro_competencias, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))
    return audit_calls


def _install_snapshot_sources(
    monkeypatch,
    *,
    hourly_used: list[dict] | None = None,
    productivity_used: list[dict] | None = None,
    active_parameters: list[dict] | None = None,
):
    default_parameters = [
        _active_parameter(
            51,
            tipo="adicional_noturno",
            valor="92.18",
            unidade="valor",
            funcao="comandante",
        ),
        _active_parameter(
            52,
            tipo="missao_categoria_a",
            valor="300.00",
            unidade="valor",
            funcao="comandante",
            categoria="categoria a",
        ),
    ]
    active_rows = [dict(item) for item in (active_parameters or default_parameters)]
    by_id = {int(item["id"]): dict(item) for item in active_rows}

    hourly_parameters = hourly_used or [
        {
            "parameter_id": 51,
            "tipo": "adicional_noturno",
            "funcao": "comandante",
            "valor": "92.18",
            "unidade": "valor",
            "vigencia_inicio": "2026-01-01",
        }
    ]
    productivity_parameters = productivity_used or [
        {
            "parameter_id": 52,
            "tipo": "missao_categoria_a",
            "funcao": "comandante",
            "categoria": "categoria a",
            "valor": "300.00",
            "unidade": "valor",
            "vigencia_inicio": "2026-01-01",
        }
    ]

    monkeypatch.setattr(
        financeiro_competencias,
        "list_missoes_operacionais",
        lambda *args, **kwargs: [
            {
                "id": 10,
                "org_id": FINANCE_ORG_SCOPE_DEFAULT,
                "competencia": "2026-04",
                "data_missao": "2026-04-10",
                "comandante_tripulante_id": 101,
                "copiloto_tripulante_id": 102,
                "horario_apresentacao": "2026-04-10T08:00:00",
                "horario_abandono": "2026-04-10T12:00:00",
                "status": "ativa",
            }
        ],
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "listar_calculos_horarios",
        lambda *args, **kwargs: [
            {
                "id": 21,
                "org_id": FINANCE_ORG_SCOPE_DEFAULT,
                "missao_operacional_id": 10,
                "competencia": "2026-04",
                "tripulante_id": 101,
                "funcao": "comandante",
                "total": "100.00",
                "memoria_calculo": {"steps": [{"rule_key": "hora"}]},
                "parametros_usados": [dict(item) for item in hourly_parameters],
                "status": "calculado",
            }
        ],
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "listar_calculos_produtividade",
        lambda *args, **kwargs: [
            {
                "id": 31,
                "org_id": FINANCE_ORG_SCOPE_DEFAULT,
                "competencia": "2026-04",
                "tripulante_id": 101,
                "funcao": "comandante",
                "produtividade_calculada": "200.00",
                "garantia_minima": "150.00",
                "total_devido": "200.00",
                "memoria_calculo": {"steps": [{"rule_key": "produtividade"}]},
                "parametros_usados": [dict(item) for item in productivity_parameters],
                "status": "calculado",
            }
        ],
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "listar_divergencias_competencia",
        lambda *args, **kwargs: [
            {
                "id": 41,
                "org_id": FINANCE_ORG_SCOPE_DEFAULT,
                "competencia": "2026-04",
                "severidade": "informativa",
                "codigo": "info",
                "mensagem": "Divergencia informativa",
                "entidade_tipo": "finance_period",
                "entidade_id": 7,
                "detalhes": {},
                "status": "aberta",
            }
        ],
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "listar_parametros_financeiros_rows",
        lambda *args, **kwargs: [dict(item) for item in active_rows],
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "listar_parametros_financeiros_por_ids",
        lambda *args, **kwargs: [
            dict(by_id[item_id]) for item_id in kwargs.get("parameter_ids", []) if item_id in by_id
        ],
    )


def test_detalhar_competencia_financeira_monta_snapshot_preview(monkeypatch):
    _install_snapshot_sources(monkeypatch)
    monkeypatch.setattr(financeiro_competencias, "fetch_competencia_financeira", lambda *args, **kwargs: None)

    result = detalhar_competencia_financeira("2026-04", db=_FakeDB())

    assert result["period"]["status"] == "aberta"
    assert result["totals"]["mission_count"] == 1
    assert result["totals"]["total_horario"] == "100.00"
    assert result["totals"]["total_produtividade"] == "200.00"
    assert result["totals"]["total_geral"] == "300.00"
    assert result["snapshot"]["missoes_operacionais"]
    assert result["snapshot"]["calculos_horarios"]
    assert result["snapshot"]["calculos_produtividade"]
    assert result["snapshot"]["parametros_usados"]
    assert result["snapshot"]["divergencias"]
    assert result["snapshot"]["release_gate"]["release_eligible"] is True


def test_recalcular_competencia_atualiza_status_em_conferencia(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(
        financeiro_competencias,
        "recalcular_produtividade_competencia",
        lambda *args, **kwargs: {"items": [{"total_devido": "200.00"}]},
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "_build_period_snapshot",
        lambda *args, **kwargs: {"totals": {"total_geral": "300.00"}, "divergencias": []},
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "avaliar_elegibilidade_fechamento_real_snapshot",
        lambda **kwargs: {"release_eligible": False, "blocking_parameters": [{"parameter_id": 99}], "environment": "hml"},
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "upsert_competencia_em_conferencia",
        lambda *args, **kwargs: _period_row(status="em_conferencia", totals_snapshot={"total_geral": "300.00"}),
    )

    result = recalcular_competencia_financeira("2026-04", actor_user_id=501, db=db)

    assert db.committed is True
    assert result["period"]["status"] == "em_conferencia"
    assert result["totals"]["total_geral"] == "300.00"
    assert result["period"]["snapshot"]["release_gate"]["release_eligible"] is False


def test_fechar_competencia_exige_confirmacao_e_gera_snapshot_audit(monkeypatch):
    db = _FakeDB()
    _install_snapshot_sources(monkeypatch)
    audit_calls = _configure_close_flow(monkeypatch)

    with pytest.raises(ConfirmacaoFechamentoObrigatoriaErro):
        fechar_competencia_financeira("2026-04", {}, actor_user_id=501, db=db)

    result = fechar_competencia_financeira(
        "2026-04",
        {"confirm": True, "motivo": "fechamento mensal"},
        actor_user_id=501,
        db=db,
    )

    assert db.committed is True
    assert result["period"]["status"] == "fechada"
    assert result["snapshot"]["totals"]["total_geral"] == "300.00"
    assert result["snapshot"]["parametros_usados"]
    assert result["snapshot"]["release_gate"]["release_eligible"] is True
    assert result["snapshot"]["release_gate"]["mode"] == "fechamento"
    assert audit_calls[0]["acao"] == "finance.period.closed"
    assert audit_calls[0]["payload_anterior"]
    assert audit_calls[0]["payload_novo"]


def test_fechar_competencia_bloqueia_parametro_qa_smoke_sem_audit(monkeypatch):
    db = _FakeDB()
    _install_snapshot_sources(
        monkeypatch,
        active_parameters=[
            _active_parameter(
                51,
                tipo="adicional_noturno",
                valor="92.18",
                unidade="valor",
                funcao="comandante",
                motivo="qa-smoke; GOV_CLASS=qa-smoke",
            )
        ],
        productivity_used=[],
    )
    audit_calls = _configure_close_flow(monkeypatch)

    with pytest.raises(ParametrosNaoElegiveisFechamentoRealErro) as exc:
        fechar_competencia_financeira("2026-04", {"confirm": True}, actor_user_id=501, db=db)

    assert exc.value.code == "finance_parameters_not_release_eligible"
    assert exc.value.details["blocking_parameters"][0]["parameter_id"] == 51
    assert "classificacao_nao_elegivel:qa-smoke" in exc.value.details["blocking_parameters"][0]["reasons"]
    assert exc.value.details["next_action"]
    assert audit_calls == []
    assert db.committed is False


def test_fechar_competencia_bloqueia_parametro_brl(monkeypatch):
    _install_snapshot_sources(
        monkeypatch,
        active_parameters=[
            _active_parameter(
                51,
                tipo="adicional_noturno",
                valor="92.18",
                unidade="BRL",
                funcao="comandante",
                motivo="legacy; GOV_CLASS=legacy",
            )
        ],
        productivity_used=[],
    )
    _configure_close_flow(monkeypatch)

    with pytest.raises(ParametrosNaoElegiveisFechamentoRealErro) as exc:
        fechar_competencia_financeira("2026-04", {"confirm": True}, actor_user_id=501, db=_FakeDB())

    assert "unidade_brl_legacy" in exc.value.details["blocking_parameters"][0]["reasons"]


def test_fechar_competencia_bloqueia_parametro_sobreposto(monkeypatch):
    _install_snapshot_sources(
        monkeypatch,
        active_parameters=[
            _active_parameter(
                51,
                tipo="adicional_noturno",
                valor="92.18",
                unidade="valor",
                funcao="comandante",
                motivo="oficial; GOV_CLASS=hml-release-candidate",
                vigencia_inicio="2026-01-01",
            ),
            _active_parameter(
                53,
                tipo="adicional_noturno",
                valor="92.18",
                unidade="valor",
                funcao="comandante",
                motivo="oficial; GOV_CLASS=hml-release-candidate",
                vigencia_inicio="2026-01-15",
            ),
        ],
        productivity_used=[],
    )
    _configure_close_flow(monkeypatch)

    with pytest.raises(ParametrosNaoElegiveisFechamentoRealErro) as exc:
        fechar_competencia_financeira("2026-04", {"confirm": True}, actor_user_id=501, db=_FakeDB())

    assert "sobreposicao_semantica_ativa" in exc.value.details["blocking_parameters"][0]["reasons"]


def test_fechar_competencia_bloqueia_parametro_sem_classificacao(monkeypatch):
    _install_snapshot_sources(
        monkeypatch,
        active_parameters=[
            _active_parameter(
                51,
                tipo="adicional_noturno",
                valor="92.18",
                unidade="valor",
                funcao="comandante",
                motivo="parametro oficial sem marker",
            )
        ],
        productivity_used=[],
    )
    _configure_close_flow(monkeypatch)

    with pytest.raises(ParametrosNaoElegiveisFechamentoRealErro) as exc:
        fechar_competencia_financeira("2026-04", {"confirm": True}, actor_user_id=501, db=_FakeDB())

    assert "classificacao_ausente" in exc.value.details["blocking_parameters"][0]["reasons"]


def test_fechar_competencia_bloqueia_competencia_ja_fechada(monkeypatch):
    monkeypatch.setattr(
        financeiro_competencias,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: _period_row(status="fechada"),
    )

    with pytest.raises(CompetenciaFinanceiraJaFechadaErro):
        fechar_competencia_financeira("2026-04", {"confirm": True}, actor_user_id=501, db=_FakeDB())


def test_reabrir_competencia_exige_motivo_status_fechado_e_audit_log(monkeypatch):
    db = _FakeDB()
    audit_calls = []
    monkeypatch.setattr(
        financeiro_competencias,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: _period_row(status="fechada", fechamento_snapshot={"totals": {"total_geral": "300.00"}}),
    )
    monkeypatch.setattr(
        financeiro_competencias,
        "reabrir_competencia_row",
        lambda *args, **kwargs: _period_row(
            status="reaberta",
            reopen_reason=kwargs["motivo"],
            reopened_by=kwargs["reopened_by"],
        ),
    )
    monkeypatch.setattr(financeiro_competencias, "record_audit_event", lambda *args, **kwargs: audit_calls.append(kwargs))

    with pytest.raises(MotivoReaberturaObrigatorioErro):
        reabrir_competencia_financeira("2026-04", {}, actor_user_id=501, db=db)

    result = reabrir_competencia_financeira(
        "2026-04",
        {"motivo": "ajuste autorizado"},
        actor_user_id=501,
        db=db,
    )

    assert result["period"]["status"] == "reaberta"
    assert audit_calls[0]["acao"] == "finance.period.reopened"

    monkeypatch.setattr(financeiro_competencias, "fetch_competencia_financeira", lambda *args, **kwargs: _period_row(status="aberta"))
    with pytest.raises(CompetenciaFinanceiraNaoFechadaErro):
        reabrir_competencia_financeira("2026-04", {"motivo": "x"}, actor_user_id=501, db=_FakeDB())

