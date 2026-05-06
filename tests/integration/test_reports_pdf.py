from backend.src.controle_treinamentos.reports import (
    build_habilitacoes_consolidado_pdf,
    build_tripulante_treinamentos_pdf,
    build_user_guide_pdf,
)


def test_build_consolidado_pdf_returns_binary_pdf():
    payload = build_habilitacoes_consolidado_pdf(
        summary={
            "total_tripulantes": 1,
            "total_habilitacoes": 1,
            "total_em_dia": 1,
            "total_vencer_90": 0,
            "total_vencer_60": 0,
            "total_vencer_30": 0,
            "total_critico_15": 0,
            "total_vencido": 0,
        },
        tripulantes_grouped=[
            {
                "tripulante_nome": "Teste",
                "base": "Goiania",
                "habilitacoes": [
                    {
                        "habilitacao_nome": "CQ IFR",
                        "data_vencimento": "31/12/2026",
                        "days_remaining_label": "280 dias",
                        "status_label": "Em dia",
                        "status_key": "em_dia",
                    }
                ],
            }
        ],
        filtros_aplicados={"nome": "-", "base": "-", "status": "-", "tipo": "-"},
        emitted_at="23/03/2026 17:00",
    )
    assert isinstance(payload, (bytes, bytearray))
    assert payload.startswith(b"%PDF")
    assert len(payload) > 1500


def test_build_user_guide_pdf_returns_binary_pdf():
    payload = build_user_guide_pdf(emitted_at="24/03/2026 09:00")
    assert isinstance(payload, (bytes, bytearray))
    assert payload.startswith(b"%PDF")
    assert len(payload) > 2500


def test_build_tripulante_treinamentos_pdf_returns_binary_pdf():
    payload = build_tripulante_treinamentos_pdf(
        tripulante={
            "nome": "Teste",
            "cpf": "000.000.000-00",
            "licenca_anac": "123456",
            "email": "teste@empresa.com",
            "telefone": "(62) 99999-9999",
            "base": "Goiania",
            "status": "Ativo",
        },
        treinamentos=[
            {
                "equipamento_nome": "CITATION V",
                "tipo_treinamento_nome": "CQ IFR 12 MESES",
                "data_realizacao": "2025-03-21",
                "data_vencimento": "2026-03-21",
                "status_calculado": "vencido",
                "observacao": "",
            }
        ],
        resumo={
            "total": 1,
            "vencido": 1,
            "a vencer": 0,
            "regular": 0,
        },
        emitted_at="24/03/2026 10:00",
    )
    assert isinstance(payload, (bytes, bytearray))
    assert payload.startswith(b"%PDF")
    assert len(payload) > 1500
