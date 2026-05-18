from __future__ import annotations

import pytest

from backend.src.controle_treinamentos.application import financeiro_produtividade_relatorio_geral as report
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


class _FakeDB:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def _row(**overrides):
    payload = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "tripulante_id": 101,
        "tripulante_nome": "Ada Produtividade",
        "funcao": "comandante",
        "tripulante_categoria_operacional": "A",
        "categoria_aplicavel": "A",
        "valor_icao": "10.00",
        "valor_instrutor": "20.00",
        "valor_checador": "30.00",
        "valor_missoes_categoria_a": "100.00",
        "valor_missoes_categoria_b": "50.00",
        "valor_cobertura_base": "40.00",
        "valor_pernoite_comum": "25.00",
        "valor_excecao_palmas": "5.00",
        "produtividade_calculada": "280.00",
        "garantia_minima": "200.00",
        "total_devido": "280.00",
        "memoria_calculo": {
            "totals": {
                "produtividade_calculada": "280.00",
                "garantia_minima": "200.00",
                "excedente": "80.00",
                "total_devido": "280.00",
            },
            "warnings": [],
        },
        "parametros_usados": [],
        "calculation_version": "finance-productivity-v1",
        "status": "calculado",
    }
    payload.update(overrides)
    return payload


def _consolidar(monkeypatch, rows, *, funcao="comandante", incluir_zerados=True, categoria=None):
    calls = []

    def _fake_rows(db, **kwargs):
        calls.append(kwargs)
        return rows

    monkeypatch.setattr(report, "listar_calculos_produtividade", _fake_rows)
    result = report.consolidar_relatorio_geral_produtividade(
        competencia="2026-04",
        funcao=funcao,
        incluir_zerados=incluir_zerados,
        categoria=categoria,
        db=object(),
    )
    return result, calls


def test_agrega_comandantes_por_competencia_e_funcao(monkeypatch):
    rows = [
        _row(),
        _row(
            id=11,
            tripulante_id=102,
            tripulante_nome="Bia Produtividade",
            valor_icao="0.00",
            valor_instrutor="0.00",
            valor_checador="0.00",
            valor_missoes_categoria_a="70.00",
            valor_missoes_categoria_b="0.00",
            valor_cobertura_base="0.00",
            valor_pernoite_comum="0.00",
            valor_excecao_palmas="0.00",
            produtividade_calculada="70.00",
            garantia_minima="100.00",
            total_devido="100.00",
            memoria_calculo={"totals": {"total_devido": "100.00"}},
        ),
    ]

    result, calls = _consolidar(monkeypatch, rows)

    assert calls[0]["competencia"] == "2026-04"
    assert calls[0]["funcao"] == "comandante"
    assert calls[0]["org_id"] == FINANCE_ORG_SCOPE_DEFAULT
    assert calls[0]["limit"] == 10000
    assert result["titulo"] == "RELATÓRIO GERAL DE PRODUTIVIDADE - COMANDANTES"
    assert [item["tripulante_id"] for item in result["items"]] == [101, 102]
    assert result["totais"]["tripulantes"] == 2
    assert result["totais"]["produtividade_apurada"] == "350.00"
    assert result["totais"]["total_produtividade"] == "380.00"


def test_agrega_copilotos_por_competencia(monkeypatch):
    rows = [
        _row(
            funcao="copiloto",
            tripulante_id=201,
            tripulante_nome="Caio Copiloto",
            valor_missoes_categoria_a="80.00",
            valor_missoes_categoria_b="0.00",
            produtividade_calculada="210.00",
            total_devido="210.00",
            memoria_calculo={"totals": {"total_devido": "210.00"}},
        )
    ]

    result, calls = _consolidar(monkeypatch, rows, funcao="copiloto")

    assert calls[0]["funcao"] == "copiloto"
    assert result["titulo"] == "RELATÓRIO GERAL DE PRODUTIVIDADE - COPILOTOS"
    assert result["items"][0]["funcao"] == "copiloto"


def test_exclui_obsoletos_cancelados_excluidos_e_preview(monkeypatch):
    rows = [
        _row(status="obsoleto", total_devido="999.00"),
        _row(id=11, tripulante_id=102, status="cancelado", total_devido="999.00"),
        _row(id=12, tripulante_id=103, status="excluido", total_devido="999.00"),
        _row(id=13, tripulante_id=104, preview=True, total_devido="999.00"),
        _row(id=14, tripulante_id=105, tripulante_nome="Valido"),
    ]

    result, _calls = _consolidar(monkeypatch, rows)

    assert len(result["items"]) == 1
    assert result["items"][0]["tripulante_id"] == 105
    assert result["contexto"]["usa_preview"] is False


def test_nao_mistura_funcoes(monkeypatch):
    rows = [
        _row(funcao="comandante", tripulante_id=101),
        _row(id=11, funcao="copiloto", tripulante_id=201, total_devido="999.00"),
    ]

    result, _calls = _consolidar(monkeypatch, rows, funcao="comandante")

    assert len(result["items"]) == 1
    assert result["items"][0]["funcao"] == "comandante"


def test_componentes_e_total_uso_memoria_persistida(monkeypatch):
    result, _calls = _consolidar(monkeypatch, [_row()])

    item = result["items"][0]
    assert item["icao_sdea"] == "10.00"
    assert item["instrutor"] == "20.00"
    assert item["checador"] == "30.00"
    assert item["missoes"] == "150.00"
    assert item["cobertura_base"] == "40.00"
    assert item["pernoite_comum"] == "25.00"
    assert item["condicao_especial"] == "5.00"
    assert item["produtividade_apurada"] == "280.00"
    assert item["garantia_minima"] == "200.00"
    assert item["excedente"] == "80.00"
    assert item["total_produtividade"] == "280.00"
    assert item["fonte_dados"] == "financeiro_calculos_produtividade_persistidos_vigentes"


def test_filtra_categoria_quando_parametro_seguro(monkeypatch):
    rows = [
        _row(categoria_aplicavel="A", tripulante_id=101),
        _row(
            id=11,
            categoria_aplicavel="B",
            tripulante_categoria_operacional="B",
            tripulante_id=102,
            total_devido="999.00",
        ),
    ]

    result, _calls = _consolidar(monkeypatch, rows, categoria="A")

    assert [item["tripulante_id"] for item in result["items"]] == [101]
    assert result["filters"]["categoria"] == "A"


def test_relatorio_geral_padrao_limita_a_categoria_ab_ou_adicional_excepcional(monkeypatch):
    rows = [
        _row(tripulante_id=101, tripulante_categoria_operacional="A", categoria_aplicavel="A"),
        _row(
            id=11,
            tripulante_id=102,
            tripulante_nome="Bia Categoria B",
            tripulante_categoria_operacional="B",
            categoria_aplicavel="B",
            valor_excecao_palmas="0.00",
            produtividade_calculada="275.00",
            total_devido="275.00",
            memoria_calculo={"totals": {"total_devido": "275.00"}},
        ),
        _row(
            id=12,
            tripulante_id=103,
            tripulante_nome="Caio Excepcional",
            tripulante_categoria_operacional="N/A",
            categoria_aplicavel="nao_aplicavel",
            tripulante_elegivel_adicional_excepcional=1,
            valor_missoes_categoria_a="0.00",
            valor_missoes_categoria_b="0.00",
            valor_excecao_palmas="5000.00",
            produtividade_calculada="5000.00",
            garantia_minima="0.00",
            total_devido="5000.00",
            memoria_calculo={"totals": {"total_devido": "5000.00"}},
        ),
        _row(
            id=13,
            tripulante_id=104,
            tripulante_nome="Dora Fora Recorte",
            tripulante_categoria_operacional="N/A",
            categoria_aplicavel="nao_aplicavel",
            tripulante_elegivel_adicional_excepcional=0,
            valor_missoes_categoria_a="0.00",
            valor_missoes_categoria_b="0.00",
            valor_excecao_palmas="0.00",
            produtividade_calculada="999.00",
            total_devido="999.00",
            memoria_calculo={"totals": {"total_devido": "999.00"}},
        ),
    ]

    result, _calls = _consolidar(monkeypatch, rows)

    assert [item["tripulante_id"] for item in result["items"]] == [101, 102, 103]
    assert result["totais"]["tripulantes"] == 3
    assert result["totais"]["total_produtividade"] == "5555.00"


def test_categoria_visual_usa_cadastro_quando_calculo_nao_aplicavel(monkeypatch):
    rows = [
        _row(
            tripulante_id=301,
            tripulante_nome="Dora Sem Missao",
            tripulante_categoria_operacional="B",
            categoria_aplicavel="nao_aplicavel",
            valor_icao="300.00",
            valor_instrutor="0.00",
            valor_checador="0.00",
            valor_missoes_categoria_a="0.00",
            valor_missoes_categoria_b="0.00",
            valor_cobertura_base="0.00",
            valor_pernoite_comum="0.00",
            valor_excecao_palmas="0.00",
            produtividade_calculada="300.00",
            garantia_minima="6000.00",
            total_devido="6000.00",
            memoria_calculo={"totals": {"total_devido": "6000.00"}},
        )
    ]

    result, _calls = _consolidar(monkeypatch, rows, categoria="B")

    assert result["items"][0]["categoria"] == "B"
    assert "NAO_APLICAVEL" not in result["items"][0].values()


def test_exclui_zerados_quando_parametro_false(monkeypatch):
    result, _calls = _consolidar(
        monkeypatch,
        [
            _row(
                valor_icao="0.00",
                valor_instrutor="0.00",
                valor_checador="0.00",
                valor_missoes_categoria_a="0.00",
                valor_missoes_categoria_b="0.00",
                valor_cobertura_base="0.00",
                valor_pernoite_comum="0.00",
                valor_excecao_palmas="0.00",
                produtividade_calculada="0.00",
                garantia_minima="0.00",
                total_devido="0.00",
                memoria_calculo={"totals": {"total_devido": "0.00"}},
            )
        ],
        incluir_zerados=False,
    )

    assert result["items"] == []
    assert result["totais"]["tripulantes"] == 0


def test_status_nao_final_gera_pendencia(monkeypatch):
    result, _calls = _consolidar(monkeypatch, [_row(status="recalculo_pendente")])

    item = result["items"][0]
    assert item["possui_pendencias"] is True
    assert item["pendencias"][0]["code"] == "calculo_produtividade_status_nao_final"
    assert result["pendencias"][0]["code"] == "calculo_produtividade_status_nao_final"


def test_exporta_pdf_relatorio_geral_produtividade_valido_e_auditado(monkeypatch):
    rows = [_row()]
    db = _FakeDB()
    audit_calls = []

    monkeypatch.setattr(report, "listar_calculos_produtividade", lambda _db, **_kwargs: rows)
    monkeypatch.setattr(report, "record_audit_event", lambda *args, **kwargs: audit_calls.append((args, kwargs)))

    result = report.exportar_relatorio_geral_produtividade_pdf(
        competencia="2026-04",
        funcao="comandante",
        actor_user_id=77,
        request_id="req-1",
        correlation_id="corr-1",
        db=db,
    )

    assert result["filename"] == "relatorio-geral-produtividade-comandantes-2026-04.pdf"
    assert result["mimetype"] == "application/pdf"
    assert result["content"].startswith(b"%PDF")
    assert b"%%EOF" in result["content"][-4096:]
    assert result["metadata"]["record_count"] == 1
    assert result["metadata"]["totais"]["total_produtividade"] == "280.00"
    assert db.committed is True
    assert audit_calls
    assert audit_calls[0][1]["acao"] == "finance.export.generated"
    assert (
        audit_calls[0][1]["payload_novo"]["metadata"]["source_endpoint"]
        == "/api/v1/financeiro/produtividade/relatorio-geral.pdf"
    )


def test_exporta_pdf_bloqueia_pendencia(monkeypatch):
    rows = [_row(status="recalculo_pendente")]
    db = _FakeDB()
    audit_calls = []

    monkeypatch.setattr(report, "listar_calculos_produtividade", lambda _db, **_kwargs: rows)
    monkeypatch.setattr(report, "record_audit_event", lambda *args, **kwargs: audit_calls.append((args, kwargs)))

    with pytest.raises(report.DomainValidationError) as exc:
        report.exportar_relatorio_geral_produtividade_pdf(
            competencia="2026-04",
            funcao="comandante",
            actor_user_id=77,
            db=db,
        )

    assert exc.value.status == 409
    assert exc.value.code == "finance_productivity_general_report_pending_calculations"
    assert exc.value.details["pendencias"][0]["code"] == "calculo_produtividade_status_nao_final"
    assert db.committed is False
    assert audit_calls == []
