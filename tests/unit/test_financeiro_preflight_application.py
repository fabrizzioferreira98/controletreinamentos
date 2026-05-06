from __future__ import annotations

import copy

from backend.src.controle_treinamentos.application import financeiro_preflight as usecases
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


class _FakeDB:
    def __init__(self):
        self.commit_called = 0

    def commit(self):
        self.commit_called += 1


def _mission(*, status: str = "ativa") -> dict:
    return {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "data_missao": "2026-04-10",
        "aeronave_id": 7,
        "categoria_financeira_aeronave": "a",
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
        "horario_apresentacao": "2026-04-10 08:00:00",
        "horario_abandono": "2026-04-10 10:00:00",
        "status": status,
        "participantes": [
            {"tripulante_id": 101, "funcao": "comandante", "status": "ativo"},
            {"tripulante_id": 202, "funcao": "copiloto", "status": "ativo"},
        ],
    }


def _parameter(
    parameter_id: int,
    *,
    tipo: str,
    unidade: str,
    valor: str,
    funcao: str | None = None,
    categoria: str | None = None,
    motivo: str = "oficial; GOV_CLASS=hml-release-candidate",
) -> dict:
    return {
        "id": parameter_id,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "tipo": tipo,
        "funcao": funcao,
        "categoria": categoria,
        "valor": valor,
        "unidade": unidade,
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
        "status": "ativo",
        "motivo": motivo,
    }


def _hourly_parameters() -> list[dict]:
    return [
        _parameter(1, tipo="duracao_hora_noturna_minutos", unidade="minutos", valor="52.5"),
        _parameter(2, tipo="periodo_diurno_inicio", unidade="minutos_do_dia", valor="360"),
        _parameter(3, tipo="periodo_diurno_fim", unidade="minutos_do_dia", valor="1080"),
        _parameter(4, tipo="adicional_noturno", funcao="comandante", unidade="valor", valor="92.18"),
        _parameter(5, tipo="domingo_feriado_diurno", funcao="comandante", unidade="valor", valor="92.18"),
        _parameter(6, tipo="domingo_feriado_noturno", funcao="comandante", unidade="valor", valor="184.36"),
        _parameter(7, tipo="adicional_noturno", funcao="copiloto", unidade="valor", valor="46.18"),
        _parameter(8, tipo="domingo_feriado_diurno", funcao="copiloto", unidade="valor", valor="46.18"),
        _parameter(9, tipo="domingo_feriado_noturno", funcao="copiloto", unidade="valor", valor="92.36"),
    ]


def _productivity_parameters() -> list[dict]:
    return [
        _parameter(10, tipo="icao_sdea", funcao="comandante", unidade="valor", valor="300"),
        _parameter(11, tipo="icao_sdea", funcao="copiloto", unidade="valor", valor="150"),
        _parameter(12, tipo="instrutor", unidade="valor", valor="300"),
        _parameter(13, tipo="checador", unidade="valor", valor="300"),
        _parameter(14, tipo="cobertura_base", funcao="comandante", unidade="valor", valor="200"),
        _parameter(15, tipo="cobertura_base", funcao="copiloto", unidade="valor", valor="100"),
        _parameter(16, tipo="missao_categoria_a", funcao="comandante", categoria="categoria a", unidade="valor", valor="300"),
        _parameter(17, tipo="missao_categoria_a", funcao="copiloto", categoria="categoria a", unidade="valor", valor="150"),
        _parameter(18, tipo="garantia_minima", funcao="comandante", categoria="categoria a", unidade="valor", valor="3000"),
        _parameter(19, tipo="garantia_minima", funcao="copiloto", categoria="categoria a", unidade="valor", valor="1500"),
    ]


def _patch_mission_dependencies(monkeypatch, *, mission: dict, parameters: list[dict], divergences: list[dict] | None = None):
    monkeypatch.setattr(usecases, "fetch_missao_operacional_detail", lambda *args, **kwargs: mission)
    monkeypatch.setattr(
        usecases,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: {"competencia": "2026-04", "status": "aberta"},
    )
    monkeypatch.setattr(usecases, "verificar_feriado_nacional_por_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        usecases,
        "_load_parameters_for_types",
        lambda *args, **kwargs: copy.deepcopy(parameters),
    )
    monkeypatch.setattr(
        usecases,
        "listar_divergencias_financeiras_rows",
        lambda *args, **kwargs: copy.deepcopy(divergences or []),
    )


def _patch_competencia_dependencies(
    monkeypatch,
    *,
    period_status: str = "em_conferencia",
    missions: list[dict] | None = None,
    parameters: list[dict] | None = None,
    release_eligible: bool = True,
    release_blocking_parameters: list[dict] | None = None,
):
    default_missions = missions or [
        {
            "id": 10,
            "org_id": FINANCE_ORG_SCOPE_DEFAULT,
            "competencia": "2026-04",
            "status": "ativa",
            "comandante_tripulante_id": 101,
            "copiloto_tripulante_id": 202,
            "horario_apresentacao": "2026-04-10 08:00:00",
            "horario_abandono": "2026-04-10 10:00:00",
            "categoria_financeira_aeronave": "a",
        }
    ]
    params = parameters or _productivity_parameters()
    monkeypatch.setattr(
        usecases,
        "detalhar_competencia_financeira",
        lambda *args, **kwargs: {
            "period": {
                "id": 7,
                "org_id": FINANCE_ORG_SCOPE_DEFAULT,
                "competencia": "2026-04",
                "status": period_status,
            },
            "snapshot": {"parametros_usados": []},
            "divergences": [],
        },
    )
    monkeypatch.setattr(
        usecases,
        "fetch_competencia_financeira",
        lambda *args, **kwargs: {"competencia": "2026-04", "status": period_status},
    )
    monkeypatch.setattr(usecases, "list_missoes_operacionais", lambda *args, **kwargs: copy.deepcopy(default_missions))
    monkeypatch.setattr(usecases, "_load_parameters_for_types", lambda *args, **kwargs: copy.deepcopy(params))
    monkeypatch.setattr(
        usecases,
        "avaliar_elegibilidade_fechamento_real_snapshot",
        lambda **kwargs: {
            "environment": "hml",
            "release_eligible": release_eligible,
            "blocking_parameters": copy.deepcopy(release_blocking_parameters or []),
            "next_action": "Promover parametros canonicos.",
        },
    )
    monkeypatch.setattr(usecases, "listar_eventos_auditoria_financeira_rows", lambda *args, **kwargs: [{"id": 1}])


def test_preflight_missao_calculavel(monkeypatch):
    db = _FakeDB()
    _patch_mission_dependencies(monkeypatch, mission=_mission(), parameters=_hourly_parameters())

    result = usecases.preflight_calculo_missao(10, db=db)

    assert result["calculavel"] is True
    assert result["bloqueios"] == []
    assert result["can_execute_actions"]["recalcular_missao"] is True
    assert db.commit_called == 0


def test_preflight_missao_cancelada(monkeypatch):
    _patch_mission_dependencies(monkeypatch, mission=_mission(status="cancelada"), parameters=_hourly_parameters())

    result = usecases.preflight_calculo_missao(10, db=_FakeDB())

    assert result["calculavel"] is False
    assert {item["code"] for item in result["bloqueios"]} >= {
        "finance_preflight_mission_cancelled",
        "finance_preflight_mission_not_active",
    }


def test_preflight_missao_parametro_ausente(monkeypatch):
    params = [item for item in _hourly_parameters() if item["tipo"] != "periodo_diurno_fim"]
    _patch_mission_dependencies(monkeypatch, mission=_mission(), parameters=params)

    result = usecases.preflight_calculo_missao(10, db=_FakeDB())

    assert result["calculavel"] is False
    assert result["parametros_faltantes"]
    assert any(item["code"] == "finance_preflight_parameter_missing" for item in result["bloqueios"])


def test_preflight_missao_parametro_brl_qa_sem_classificacao_overlap_e_divergencia(monkeypatch):
    params = _hourly_parameters()
    params[0]["unidade"] = "BRL"
    params[0]["motivo"] = "legacy; GOV_CLASS=legacy"
    params[1]["motivo"] = "qa-smoke; GOV_CLASS=qa-smoke"
    params[2]["motivo"] = "oficial sem marker"
    params.append(
        _parameter(
            99,
            tipo="adicional_noturno",
            funcao="comandante",
            unidade="valor",
            valor="93.00",
            motivo="oficial; GOV_CLASS=hml-release-candidate",
        )
    )
    _patch_mission_dependencies(
        monkeypatch,
        mission=_mission(),
        parameters=params,
        divergences=[
            {
                "id": 5,
                "org_id": FINANCE_ORG_SCOPE_DEFAULT,
                "competencia": "2026-04",
                "severity": "bloqueante",
                "code": "finance_overlap",
                "message": "Sobreposicao detectada.",
                "entity_type": "finance_mission",
                "entity_id": 10,
                "mission_id": 10,
                "status": "aberta",
                "metadata": {},
                "detected_at": "2026-04-10T12:00:00",
            }
        ],
    )

    result = usecases.preflight_calculo_missao(10, db=_FakeDB())

    assert result["calculavel"] is False
    assert result["parametros_nao_elegiveis"]
    assert result["dados_qa_detectados"]
    assert any(item["code"] == "finance_preflight_parameter_not_eligible" for item in result["bloqueios"])
    assert any(item["code"] == "finance_preflight_mission_divergence_blocking" for item in result["bloqueios"])


def test_preflight_competencia_fechada(monkeypatch):
    _patch_competencia_dependencies(monkeypatch, period_status="fechada")

    result = usecases.preflight_calculo_competencia("2026-04", db=_FakeDB())

    assert result["calculavel"] is False
    assert result["fechavel"] is False
    assert any(item["code"] == "finance_preflight_competencia_fechada" for item in result["bloqueios"])


def test_preflight_competencia_fechavel(monkeypatch):
    _patch_competencia_dependencies(monkeypatch, period_status="em_conferencia", release_eligible=True)

    result = usecases.preflight_calculo_competencia("2026-04", db=_FakeDB())

    assert result["calculavel"] is True
    assert result["fechavel"] is True
    assert result["can_execute_actions"]["fechar_competencia"] is True
    assert result["next_action"]


def test_preflight_competencia_nao_fechavel_por_gate(monkeypatch):
    _patch_competencia_dependencies(
        monkeypatch,
        release_eligible=False,
        release_blocking_parameters=[
            {
                "parameter_id": 19,
                "tipo": "garantia_minima",
                "funcao": "copiloto",
                "categoria": "categoria a",
                "unidade": "valor",
                "valor": "1500.00",
                "reasons": ["classificacao_nao_elegivel:qa-smoke"],
            }
        ],
    )

    result = usecases.preflight_calculo_competencia("2026-04", db=_FakeDB())

    assert result["calculavel"] is False
    assert result["fechavel"] is False
    assert any(item["code"] == "finance_preflight_release_gate_blocked" for item in result["bloqueios"])
    assert result["parametros_nao_elegiveis"]


def test_preflight_competencia_parametro_ausente(monkeypatch):
    params = [item for item in _productivity_parameters() if item["tipo"] != "garantia_minima"]
    _patch_competencia_dependencies(monkeypatch, parameters=params)

    result = usecases.preflight_calculo_competencia("2026-04", db=_FakeDB())

    assert result["calculavel"] is False
    assert any(item["tipo"] == "garantia_minima" for item in result["parametros_faltantes"])


def test_preflight_competencia_resposta_tem_next_action_e_sem_mutacao(monkeypatch):
    db = _FakeDB()
    _patch_competencia_dependencies(monkeypatch, release_eligible=False)

    result = usecases.preflight_calculo_competencia("2026-04", db=db)

    assert result["next_action"]
    assert db.commit_called == 0


