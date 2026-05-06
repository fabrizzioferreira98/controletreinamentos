import pytest

from backend.src.controle_treinamentos.application import financeiro_lancamentos_jornada as jornada
from backend.src.controle_treinamentos.core.domain_errors import DomainValidationError


class _FakeDB:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def _patch_common(monkeypatch):
    calls = {}

    def fake_period_rows(db, **kwargs):
        calls["period_rows"] = kwargs
        return [
            {
                "linha_id": 10,
                "competencia": "2026-04",
                "data": "2026-04-10",
                "tripulante_id": 7,
                "tripulante": {"nome": "Joao Silva"},
                "funcao": "comandante",
                "relatorio_voo": "LA1234",
                "trecho": "GRU-BSB",
                "calculation_status": "calculado",
                "status": "calculado",
                "total": "100.00",
                "avisos": [],
                "erros": [],
            }
        ]

    def fake_consolidado(**kwargs):
        calls["productivity"] = kwargs
        return {
            "linhas_por_tripulante": [
                {
                    "tripulante_id": 7,
                    "tripulante_nome": "Joao Silva",
                    "funcoes": ["comandante"],
                    "total_a_pagar": "200.00",
                }
            ],
            "alertas": [],
            "bloqueios": [],
        }

    monkeypatch.setattr(jornada, "listar_linhas_jornada_periodo", fake_period_rows)
    monkeypatch.setattr(jornada, "_serialize_line", lambda row: row)
    monkeypatch.setattr(jornada, "consolidar_produtividade_jornada", fake_consolidado)
    monkeypatch.setattr(jornada, "_audit", lambda *args, **kwargs: None)
    return calls


def _grade_line(index=1, *, tripulante_id=7, tripulante_nome="Joao Silva", funcao="comandante", total="100.00"):
    return {
        "id": index,
        "linha_id": index,
        "missao_operacional_id": 1000 + index,
        "competencia": "2026-04",
        "data": f"2026-04-{((index - 1) % 28) + 1:02d}",
        "tripulante_id": tripulante_id,
        "tripulante": {"id": tripulante_id, "nome": tripulante_nome},
        "funcao": funcao,
        "aeronave": {"id": 3, "nome": "CITATION V"},
        "relatorio_voo": f"LA{index:04d}",
        "numero_db": str(index),
        "trecho": "GRU-BSB",
        "hora_apresentacao": "07:00",
        "hora_abandono": "16:00",
        "pos_exec_min": 15,
        "minutos_diurnos": 480,
        "minutos_noturnos": 0,
        "pre_calculo_min": 540,
        "pos_calculo_min": 555,
        "valor_normal": total,
        "valor_diurno": "0.00",
        "valor_noturno": "0.00",
        "total": total,
        "status": "ativa",
        "calculation_status": "calculado",
        "avisos": [],
        "erros": [],
    }


def _grade_payload(lines):
    return {
        "contexto": {
            "competencia": "2026-04",
            "funcao_operacional": "comandante",
            "tripulante_id": 7,
            "tripulantes": len({line["tripulante_id"] for line in lines}),
            "resultado_atual": "100.00",
            "status_competencia": "aberta",
        },
        "indicadores": {
            "total_geral": str(sum(float(line["total"]) for line in lines)),
            "quantidade_linhas": len(lines),
            "hora_reduzida_total": 9.25,
            "excecoes": 0,
            "alertas_descanso": len(lines),
            "domingos": 1,
            "feriados": 0,
            "valor_normal": str(sum(float(line["valor_normal"]) for line in lines)),
        },
        "linhas": lines,
    }


def test_indicadores_grade_usam_hora_reduzida_do_calculo_e_nao_total_da_jornada():
    line = {
        "data": "2026-04-01",
        "status": "calculado",
        "calculation_status": "calculado",
        "total": "122.91",
        "pos_calculo_min": 415,
        "horas_noturnas_convertidas": "1.3333",
        "valor_diurno_domingo_feriado": "0.00",
        "valor_noturno_domingo_feriado": "0.00",
    }

    result = jornada._indicator_values([line], [], set())

    assert result["total_geral"] == "122.91"
    assert result["hora_reduzida_total_minutos"] == 80
    assert result["hora_reduzida_total"] == 1.33


def test_indicadores_grade_ignoram_linha_sem_calculo_persistido():
    calculated = {
        "data": "2026-04-01",
        "status": "calculado",
        "calculation_status": "calculado",
        "total": "122.91",
        "pos_calculo_min": 415,
        "horas_noturnas_convertidas": "1.3333",
        "valor_diurno_domingo_feriado": "0.00",
        "valor_noturno_domingo_feriado": "0.00",
    }
    pending = {
        "data": "2026-04-02",
        "status": "pendente",
        "calculation_status": "pendente",
        "total": "999.99",
        "pos_calculo_min": 999,
        "horas_noturnas_convertidas": "9.9999",
        "valor_diurno_domingo_feriado": "0.00",
        "valor_noturno_domingo_feriado": "0.00",
    }

    result = jornada._indicator_values([calculated, pending], [], set())

    assert result["total_geral"] == "122.91"
    assert result["linhas_calculadas"] == 1
    assert result["linhas_pendentes_calculo"] == 1
    assert result["hora_reduzida_total_minutos"] == 80


def test_linha_serializada_nao_confunde_jornada_total_com_pre_pos_calculo():
    row = {
        "linha_id": 9,
        "missao_operacional_id": 6,
        "competencia": "2026-04",
        "data_missao": "2026-04-04",
        "data_final": "2026-04-04",
        "linha_tripulante_id": 91,
        "linha_funcao": "comandante",
        "linha_status": "ativo",
        "missao_status": "ativa",
        "jornada_total_minutos": 795,
        "minutos_diurnos": 705,
        "minutos_noturnos_reais": 90,
        "horas_noturnas_convertidas": "1.7143",
        "minutos_pre": 0,
        "minutos_pos": 0,
        "pos_exec_min": 0,
        "calculo_total": "158.02",
        "calculo_horario_id": 17,
        "calculo_status": "calculado",
    }

    result = jornada._serialize_line(row)

    assert result["jornada_total_minutos"] == 795
    assert result["pre_calculo_min"] == 0
    assert result["pos_calculo_min"] == 0
    assert result["hora_reduzida_minutos"] == 103
    assert result["total"] == "158.02"


def test_extrato_periodo_retorna_horaria_produtividade_e_totais(monkeypatch):
    calls = _patch_common(monkeypatch)

    result = jornada.gerar_extrato_periodo_jornada(
        data_inicio="2026-04-01",
        data_fim="2026-04-30",
        tripulante_id=7,
        funcao="comandante",
        tipo="ambos",
        org_id="org-a",
        db=_FakeDB(),
    )

    assert calls["period_rows"] == {
        "data_inicio": "2026-04-01",
        "data_fim": "2026-04-30",
        "org_id": "org-a",
        "funcao": "comandante",
        "tripulante_id": 7,
        "limit": 5000,
        "offset": 0,
    }
    assert calls["productivity"]["competencia"] == "2026-04"
    assert result["subtotais"] == {"horaria": "100.00", "produtividade": "200.00"}
    assert result["total_geral"] == "300.00"
    assert [line["tipo"] for line in result["linhas"]] == ["produtividade", "horaria"]
    assert result["filters"]["tipo"] == "ambos"


def test_extrato_periodo_bloqueia_data_inicial_maior_que_final(monkeypatch):
    _patch_common(monkeypatch)

    with pytest.raises(DomainValidationError) as exc:
        jornada.gerar_extrato_periodo_jornada(
            data_inicio="2026-04-30",
            data_fim="2026-04-01",
            tipo="horaria",
            org_id="org-a",
            db=_FakeDB(),
        )

    assert exc.value.code == "finance_journey_extract_invalid_period"


def test_extrato_periodo_nao_prorrateia_produtividade_em_periodo_parcial(monkeypatch):
    calls = _patch_common(monkeypatch)

    result = jornada.gerar_extrato_periodo_jornada(
        data_inicio="2026-04-10",
        data_fim="2026-04-12",
        tipo="produtividade",
        org_id="org-a",
        db=_FakeDB(),
    )

    assert "productivity" not in calls
    assert result["linhas"] == []
    assert result["total_geral"] == "0.00"
    assert result["alertas"][0]["code"] == "produtividade_periodo_parcial"


def test_extrato_periodo_pdf_reusa_mesmo_recorte(monkeypatch):
    _patch_common(monkeypatch)
    db = _FakeDB()

    result = jornada.exportar_extrato_periodo_pdf(
        data_inicio="2026-04-01",
        data_fim="2026-04-30",
        tipo="ambos",
        actor_user_id=42,
        org_id="org-a",
        db=db,
    )

    assert result["mimetype"] == "application/pdf"
    assert result["filename"] == "extrato-periodo-2026-04-01-2026-04-30.pdf"
    assert result["content"].startswith(b"%PDF")
    assert result["metadata"]["total_geral"] == "300.00"
    assert db.committed is True


def test_extrato_periodo_pdf_bloqueia_linha_horaria_sem_calculo_persistido(monkeypatch):
    calls = _patch_common(monkeypatch)
    calls.clear()

    def fake_period_rows(db, **kwargs):
        calls["period_rows"] = kwargs
        return [
            {
                "linha_id": 10,
                "competencia": "2026-04",
                "data": "2026-04-10",
                "tripulante_id": 7,
                "tripulante": {"nome": "Joao Silva"},
                "funcao": "comandante",
                "calculation_status": "pendente",
                "status": "pendente",
                "total": "999.00",
                "avisos": [{"code": "calculation_pending", "message": "Linha ainda sem calculo horario vigente."}],
                "erros": [],
            }
        ]

    monkeypatch.setattr(jornada, "listar_linhas_jornada_periodo", fake_period_rows)

    with pytest.raises(DomainValidationError) as exc:
        jornada.exportar_extrato_periodo_pdf(
            data_inicio="2026-04-01",
            data_fim="2026-04-30",
            tipo="horaria",
            actor_user_id=42,
            org_id="org-a",
            db=_FakeDB(),
        )

    assert exc.value.code == "finance_hourly_unpersisted_lines"
    assert exc.value.status == 409


def test_grade_pdf_exporta_recorte_atual_e_filename(monkeypatch):
    line = _grade_line()
    calls = {}
    db = _FakeDB()

    def fake_grade(**kwargs):
        calls["grade"] = kwargs
        return _grade_payload([line])

    monkeypatch.setattr(jornada, "listar_grade_jornada", fake_grade)
    monkeypatch.setattr(jornada, "_audit", lambda *args, **kwargs: calls.setdefault("audit", kwargs))

    result = jornada.exportar_grade_jornada_pdf(
        competencia="2026-04",
        funcao="comandante",
        tripulante_id=7,
        actor_user_id=42,
        org_id="org-a",
        db=db,
    )

    assert calls["grade"]["competencia"] == "2026-04"
    assert calls["grade"]["funcao"] == "comandante"
    assert calls["grade"]["tripulante_id"] == 7
    assert calls["grade"]["org_id"] == "org-a"
    assert result["mimetype"] == "application/pdf"
    assert result["filename"] == "lancamentos-jornada-2026-04-comandante-tripulante-7.pdf"
    assert result["content"].startswith(b"%PDF")
    assert b"%%EOF" in result["content"][-4096:]
    assert result["metadata"]["record_count"] == 1
    assert calls["audit"]["event_name"] == "finance.journey_grid.exported"
    assert db.committed is True


def test_grade_pdf_bloqueia_linha_sem_calculo_persistido(monkeypatch):
    pending = _grade_line(total="999.00")
    pending["status"] = "pendente"
    pending["calculation_status"] = "pendente"
    calls = {}

    def fake_grade(**kwargs):
        calls["grade"] = kwargs
        return _grade_payload([pending])

    monkeypatch.setattr(jornada, "listar_grade_jornada", fake_grade)
    monkeypatch.setattr(jornada, "_audit", lambda *args, **kwargs: calls.setdefault("audit", kwargs))

    with pytest.raises(DomainValidationError) as exc:
        jornada.exportar_grade_jornada_pdf(
            competencia="2026-04",
            funcao="comandante",
            tripulante_id=7,
            actor_user_id=42,
            org_id="org-a",
            db=_FakeDB(),
        )

    assert exc.value.code == "finance_hourly_unpersisted_lines"
    assert exc.value.status == 409
    assert "audit" not in calls


def test_grade_pdf_suporta_muitas_linhas_para_paginacao(monkeypatch):
    lines = [_grade_line(index=i + 1, total="10.00") for i in range(80)]
    monkeypatch.setattr(jornada, "listar_grade_jornada", lambda **kwargs: _grade_payload(lines))
    monkeypatch.setattr(jornada, "_audit", lambda *args, **kwargs: None)

    result = jornada.exportar_grade_jornada_pdf(
        competencia="2026-04",
        actor_user_id=42,
        org_id="org-a",
        db=_FakeDB(),
    )

    assert result["content"].startswith(b"%PDF")
    assert result["metadata"]["record_count"] == 80
    assert len(result["content"]) > 10000
