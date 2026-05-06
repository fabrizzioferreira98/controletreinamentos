from __future__ import annotations

import json
from datetime import date

import pytest

from backend.src.controle_treinamentos.application.financeiro_bonificacao_horaria import (
    ParametroBonificacaoHorariaNaoElegivelErro,
    calcular_bonificacao_horaria,
)
from backend.src.controle_treinamentos.application.financeiro_bonificacao_produtividade import (
    ParametroBonificacaoProdutividadeNaoElegivelErro,
    calcular_bonificacao_produtividade,
)
from backend.src.controle_treinamentos.application.financeiro_governanca_parametros import (
    CANONICAL_MATRIX,
    EXPECTED_UNITS,
    GOV_CLASS_HML_RELEASE_CANDIDATE,
    GOV_CLASS_LEGACY,
    GOV_CLASS_PRODUCTION_APPROVED,
    GOV_CLASS_QA_SMOKE,
    GovernancaParametrosErro,
    MatrizCanonicaInvalidaErro,
    aplicar_plano_promocao_classificacao,
    assert_no_delete_statement,
    classificar_parametros,
    construir_plano_promocao_hml_release_candidate,
    filtrar_parametros_para_fechamento_real,
    parametro_elegivel_fechamento_real,
    validar_matriz_canonica_para_fechamento_real,
    validar_sem_divergencia_ativa_por_chave_semantica,
    validar_sem_sobreposicao_ativa_por_chave_canonica,
)


def _param(
    parameter_id: int,
    tipo: str,
    valor: str,
    *,
    unidade: str,
    funcao: str | None = None,
    categoria: str | None = None,
    status: str = "ativo",
    motivo: str = "oficial",
    vigencia_inicio: str = "2026-01-01",
    vigencia_fim: str | None = None,
) -> dict:
    return {
        "id": parameter_id,
        "org_id": "default_single_tenant",
        "tipo": tipo,
        "funcao": funcao,
        "categoria": categoria,
        "valor": valor,
        "unidade": unidade,
        "status": status,
        "motivo": motivo,
        "vigencia_inicio": vigencia_inicio,
        "vigencia_fim": vigencia_fim,
    }


def _canonical_rows(*, governance_class: str | None = None) -> list[dict]:
    rows = []
    for idx, spec in enumerate(CANONICAL_MATRIX, start=1):
        reason = "matriz-canonica"
        if governance_class:
            reason = f"matriz-canonica; GOV_CLASS={governance_class}"
        rows.append(
            _param(
                idx,
                spec["tipo"],
                spec["valor"],
                unidade=spec["unidade"],
                funcao=spec.get("funcao"),
                categoria=spec.get("categoria"),
                motivo=reason,
            )
        )
    return rows


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, rows: dict[int, dict]):
        self.rows = rows
        self.queries: list[tuple[str, tuple | None]] = []
        self.audit_inserts: list[tuple[str, tuple | None]] = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        normalized = " ".join(query.lower().split())
        if normalized.startswith("select id, status, vigencia_inicio"):
            parameter_id = int(params[0])
            row = self.rows.get(parameter_id)
            if not row:
                return _Cursor(None)
            return _Cursor(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "vigencia_inicio": row.get("vigencia_inicio"),
                    "vigencia_fim": row.get("vigencia_fim"),
                    "motivo": row.get("motivo"),
                }
            )
        if normalized.startswith("update financeiro_parametros"):
            motivo, _actor_user_id, parameter_id = params
            row = self.rows[int(parameter_id)]
            row["motivo"] = motivo
            return _Cursor(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "vigencia_inicio": row.get("vigencia_inicio"),
                    "vigencia_fim": row.get("vigencia_fim"),
                    "motivo": row.get("motivo"),
                }
            )
        if "insert into auditoria_eventos" in normalized:
            self.audit_inserts.append((query, params))
            return _Cursor(None)
        raise AssertionError(f"Unexpected query: {query}")


def test_parametro_qa_smoke_nao_e_elegivel_para_fechamento_real():
    row = _param(
        1,
        "garantia_minima",
        "3000",
        unidade="valor",
        funcao="comandante",
        categoria="categoria a",
        motivo="QA-HML; GOV_CLASS=qa-smoke",
    )
    assert parametro_elegivel_fechamento_real(row, environment="hml") is False


def test_parametro_hml_release_candidate_e_elegivel_em_hml():
    row = _param(
        2,
        "garantia_minima",
        "3000",
        unidade="valor",
        funcao="comandante",
        categoria="categoria a",
        motivo="oficial; GOV_CLASS=hml-release-candidate",
    )
    assert parametro_elegivel_fechamento_real(row, environment="hml") is True


def test_parametro_production_approved_e_elegivel_em_producao():
    row = _param(
        3,
        "garantia_minima",
        "3000",
        unidade="valor",
        funcao="comandante",
        categoria="categoria a",
        motivo="oficial; GOV_CLASS=production-approved",
    )
    assert parametro_elegivel_fechamento_real(row, environment="production") is True


def test_brl_nunca_e_elegivel():
    row = _param(
        4,
        "adicional_noturno",
        "92.18",
        unidade="BRL",
        funcao="comandante",
        motivo=f"{GOV_CLASS_PRODUCTION_APPROVED}; GOV_CLASS={GOV_CLASS_PRODUCTION_APPROVED}",
    )
    assert parametro_elegivel_fechamento_real(row, environment="hml") is False


def test_overlap_ativo_por_chave_canonica_gera_falha_de_governanca():
    rows = [
        _param(10, "adicional_noturno", "92.18", unidade="valor", funcao="comandante", vigencia_inicio="2026-01-01"),
        _param(11, "adicional_noturno", "95.00", unidade="valor", funcao="comandante", vigencia_inicio="2026-01-15"),
    ]
    with pytest.raises(GovernancaParametrosErro) as exc:
        validar_sem_sobreposicao_ativa_por_chave_canonica(rows)
    assert exc.value.code == "finance_parameter_active_overlap_detected"


def test_divergencia_ativa_impede_promocao():
    rows = [
        _param(12, "adicional_noturno", "92.18", unidade="valor", funcao="comandante", vigencia_inicio="2026-01-01"),
        _param(13, "adicional_noturno", "95.00", unidade="valor", funcao="comandante", vigencia_inicio="2026-01-01"),
    ]
    with pytest.raises(GovernancaParametrosErro) as exc:
        validar_sem_divergencia_ativa_por_chave_semantica(rows)
    assert exc.value.code == "finance_parameter_active_semantic_divergence_detected"


def test_matriz_canonica_completa_gera_eligible_for_real_closure_maior_que_zero():
    rows = _canonical_rows(governance_class=GOV_CLASS_HML_RELEASE_CANDIDATE)
    result = validar_matriz_canonica_para_fechamento_real(rows, environment="hml")
    assert result["eligible_count"] == len(CANONICAL_MATRIX)
    assert result["eligible_count"] > 0


def test_matriz_incompleta_bloqueia_fechamento_real():
    rows = _canonical_rows(governance_class=GOV_CLASS_HML_RELEASE_CANDIDATE)
    rows = [row for row in rows if row["tipo"] != "periodo_diurno_fim"]
    with pytest.raises(MatrizCanonicaInvalidaErro) as exc:
        validar_matriz_canonica_para_fechamento_real(rows, environment="hml")
    assert exc.value.code == "finance_parameter_canonical_matrix_invalid"


def test_inventario_retorna_classificacao():
    rows = [
        _param(30, "periodo_diurno_inicio", "6", unidade="horario", motivo="QA-HML-smoke; GOV_CLASS=qa-smoke"),
        _param(31, "periodo_diurno_inicio", "360", unidade="minutos_do_dia", motivo="oficial; GOV_CLASS=hml-release-candidate"),
    ]
    classified = classificar_parametros(rows, used_parameter_ids={31})
    by_id = {item["id"]: item for item in classified}
    assert "qa_smoke" in by_id[30]["tags"]
    assert "oficial" in by_id[31]["tags"]
    assert by_id[31]["used_in_persisted_calc"] is True
    assert by_id[30]["used_in_persisted_calc"] is False


def test_filtro_fechamento_real_respeita_classe_hml_release_candidate():
    rows = [
        _param(20, "garantia_minima", "3000", unidade="valor", funcao="comandante", categoria="categoria a", motivo="QA-HML; GOV_CLASS=qa-smoke"),
        _param(
            21,
            "garantia_minima",
            "3000",
            unidade="valor",
            funcao="comandante",
            categoria="categoria a",
            motivo="oficial; GOV_CLASS=hml-release-candidate",
        ),
    ]
    filtered = filtrar_parametros_para_fechamento_real(rows, environment="hml")
    assert [item["id"] for item in filtered] == [21]


def test_periodo_diurno_e_horaria_exigem_unidades_canonicas_no_inventario():
    assert EXPECTED_UNITS["periodo_diurno_inicio"] == "minutos_do_dia"
    assert EXPECTED_UNITS["periodo_diurno_fim"] == "minutos_do_dia"
    assert EXPECTED_UNITS["adicional_noturno"] == "valor"
    assert EXPECTED_UNITS["domingo_feriado_noturno"] == "valor"
    assert EXPECTED_UNITS["pernoite_comum_sem_cobertura"] == "valor"


def test_motor_produtividade_exige_unidade_valor():
    with pytest.raises(ParametroBonificacaoProdutividadeNaoElegivelErro) as exc:
        calcular_bonificacao_produtividade(
            competencia="2026-04",
            tripulante={
                "id": 1,
                "sdea_ativo": True,
                "sdea_icao_validade": date(2026, 4, 30),
                "instrutor_ativo": False,
                "checador_ativo": False,
            },
            funcao="comandante",
            missoes_operacionais=[],
            parametros_vigentes=[
                _param(1, "icao_sdea", "300", unidade="BRL", funcao="comandante"),
            ],
            cobertura_base=False,
            excecao_palmas_turbohelice=False,
            aplicar_garantia_minima=False,
        )
    assert exc.value.code == "bonificacao_produtividade_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "unidade_invalida_para_tipo" in blocked[1]
    assert "unidade_brl_legacy" in blocked[1]


def test_motor_bonificacao_horaria_exige_unidade_valor_nos_adicionais():
    with pytest.raises(ParametroBonificacaoHorariaNaoElegivelErro) as exc:
        calcular_bonificacao_horaria(
            missao_operacional={
                "id": 101,
                "org_id": "default_single_tenant",
                "competencia": "2026-04",
                "data_missao": "2026-04-29",
                "horario_apresentacao": "2026-04-29T18:00:00",
                "horario_abandono": "2026-04-29T19:45:00",
            },
            participante={"tripulante_id": 200, "funcao": "comandante"},
            parametros_vigentes=[
                _param(1, "duracao_hora_noturna_minutos", "52.5", unidade="minutos"),
                _param(2, "periodo_diurno_inicio", "360", unidade="minutos_do_dia"),
                _param(3, "periodo_diurno_fim", "1080", unidade="minutos_do_dia"),
                _param(4, "adicional_noturno", "10", unidade="BRL", funcao="comandante"),
                _param(5, "domingo_feriado_diurno", "20", unidade="BRL", funcao="comandante"),
                _param(6, "domingo_feriado_noturno", "30", unidade="BRL", funcao="comandante"),
            ],
            domingo_feriado=False,
            feriado=False,
        )
    assert exc.value.code == "bonificacao_horaria_parametro_nao_elegivel"
    blocked = {item["parameter_id"]: set(item["reasons"]) for item in exc.value.details["blocking_parameters"]}
    assert "unidade_invalida_para_tipo" in blocked[4]
    assert "unidade_brl_legacy" in blocked[4]


def test_promocao_nunca_usa_delete():
    assert_no_delete_statement("UPDATE financeiro_parametros SET motivo = 'x' WHERE id = 1")
    with pytest.raises(GovernancaParametrosErro) as exc:
        assert_no_delete_statement("DELETE FROM financeiro_parametros WHERE id = 1")
    assert exc.value.code == "finance_parameter_governance_delete_forbidden"


def test_plano_promocao_define_classes_esperadas():
    rows = _canonical_rows(governance_class=None)
    rows.extend(
        [
            _param(
                101,
                "periodo_diurno_inicio",
                "6",
                unidade="horario",
                status="inativo",
                motivo="QA-HML-smoke; GOV_CLASS=deprecated",
            ),
            _param(
                102,
                "adicional_noturno",
                "10",
                unidade="BRL",
                status="inativo",
                motivo="QA-HML-smoke; GOV_CLASS=qa-smoke",
            ),
        ]
    )
    plan = construir_plano_promocao_hml_release_candidate(rows)
    by_id = {item["parameter_id"]: item for item in plan}

    assert by_id[1]["after"]["governance_class"] == GOV_CLASS_HML_RELEASE_CANDIDATE
    assert by_id[101]["after"]["governance_class"] == GOV_CLASS_QA_SMOKE
    assert by_id[102]["after"]["governance_class"] == GOV_CLASS_LEGACY


def test_audit_log_gerado_em_alteracao_de_classificacao():
    db = _FakeDB(
        {
            1: {
                "id": 1,
                "status": "ativo",
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": None,
                "motivo": "QA-HML endpoint check",
            }
        }
    )
    plan = [
        {
            "parameter_id": 1,
            "action": "promover_classificacao_governanca",
            "before": {"governance_class": GOV_CLASS_QA_SMOKE, "motivo": "QA-HML endpoint check"},
            "after": {
                "governance_class": GOV_CLASS_HML_RELEASE_CANDIDATE,
                "motivo": "QA-HML endpoint check; GOV_CLASS=hml-release-candidate",
            },
        }
    ]

    applied = aplicar_plano_promocao_classificacao(
        db,
        plano=plan,
        actor_user_id=99,
        now_iso="2026-04-30T23:59:59",
    )

    assert len(applied) == 1
    assert len(db.audit_inserts) == 1
    _query, params = db.audit_inserts[0]
    assert params[2] == "finance.parameter.classification.updated"
    payload_after = json.loads(params[4])
    assert payload_after["governance_class"] == GOV_CLASS_HML_RELEASE_CANDIDATE


