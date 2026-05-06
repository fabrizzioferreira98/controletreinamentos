from flask import render_template

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.constants import TRIPULANTE_CATEGORIA_OPTIONS, TRIPULANTE_FUNCAO_OPTIONS, TRIPULANTE_STATUS_OPTIONS


def test_tripulantes_template_renders_without_avatar_undefined(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    app = create_app()
    with app.test_request_context("/tripulantes"):
        html = render_template(
            "tripulantes_list.html",
            tripulantes=[
                {
                    "id": 1,
                    "nome": "Ana Silva",
                    "cpf": "000.000.000-00",
                    "licenca_anac": "123456",
                    "telefone": "",
                    "base": "GYN",
                    "status": "Ativo",
                    "ativo": 1,
                    "funcao_operacional": "comandante",
                    "categoria_operacional": "A",
                    "sdea_ativo": 0,
                    "instrutor_ativo": 0,
                    "checador_ativo": 0,
                    "possui_foto": False,
                    "whatsapp_url": "",
                }
            ],
            filtros={"nome": "", "status": "", "base": "", "funcao": "", "categoria": "", "ativo": ""},
            bases=[],
            statuses=TRIPULANTE_STATUS_OPTIONS,
            funcoes=TRIPULANTE_FUNCAO_OPTIONS,
            categorias=TRIPULANTE_CATEGORIA_OPTIONS,
            pagination={"page": 1, "pages": 1, "total": 1, "has_prev": False, "has_next": False},
        )

    assert "Ana Silva" in html
    assert "Tripulantes" in html

