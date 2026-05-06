from __future__ import annotations

from ..constants import PERNOITE_TIPO_OPTIONS
from ..repositories.dashboard_cache import fetch_cached_rows
from ..repositories.queries import fetch_training_attachments


def get_training_form_options(db, *, treinamento_id=None, selected_equipment_id=None, selected_tipo_id=None):
    tripulantes = fetch_cached_rows(
        db,
        cache_key="options:tripulantes:id_nome",
        query="SELECT id, nome FROM tripulantes ORDER BY nome",
    )
    equipamentos = db.execute(
        "SELECT id, nome FROM equipamentos WHERE ativo = 1 OR id = %s ORDER BY nome",
        (selected_equipment_id or 0,),
    ).fetchall()
    tipos = fetch_cached_rows(
        db,
        cache_key=f"options:tipos_treinamento:form:{selected_tipo_id or 0}",
        query=(
            "SELECT id, nome, periodicidade_meses, exige_equipamento "
            "FROM tipos_treinamento WHERE ativo = 1 OR id = %s ORDER BY nome"
        ),
        params=(selected_tipo_id or 0,),
    )
    attachments = []
    if treinamento_id:
        attachments = fetch_training_attachments(db, treinamento_id)

    return {
        "tripulantes": tripulantes,
        "equipamentos": equipamentos,
        "tipos": tipos,
        "attachments": attachments,
    }

def get_missao_form_options(db):
    tripulantes = fetch_cached_rows(
        db,
        cache_key="options:tripulantes:ativos:missao_form",
        query="SELECT id, nome, base, funcao_operacional FROM tripulantes WHERE ativo = 1 ORDER BY nome",
    )
    return {
        "tipo_pernoite_options": PERNOITE_TIPO_OPTIONS,
        "tripulantes": tripulantes,
    }

def get_pernoite_form_options(db):
    tripulantes = fetch_cached_rows(
        db,
        cache_key="options:tripulantes:ativos:pernoite_form",
        query="SELECT id, nome, base FROM tripulantes WHERE ativo = 1 ORDER BY nome",
    )
    missoes = fetch_cached_rows(
        db,
        cache_key="options:missoes:pernoite_form",
        query=(
            "SELECT id, codigo_voo, contratante, data_inicio, data_fim "
            "FROM missoes_operacionais "
            "ORDER BY data_inicio DESC, id DESC LIMIT 500"
        ),
    )
    return {
        "tripulantes": tripulantes,
        "missoes": missoes,
        "tipo_options": PERNOITE_TIPO_OPTIONS,
    }

def get_adicional_excepcional_form_options(db):
    tripulantes = fetch_cached_rows(
        db,
        cache_key="options:tripulantes:id_nome_base",
        query="SELECT id, nome, base FROM tripulantes ORDER BY nome",
    )
    return {
        "tripulantes": tripulantes,
    }
