from __future__ import annotations

from ..auth import normalize_permissions


def build_tripulante_form_state(source=None):
    data = dict(source or {})
    for key in (
        "nome",
        "cpf",
        "licenca_anac",
        "email",
        "telefone",
        "base",
        "status",
        "funcao_operacional",
        "categoria_operacional",
        "observacoes",
        "foto_base64",
    ):
        data.setdefault(key, "")
    data.setdefault("funcao_operacional", "outro")
    data.setdefault("categoria_operacional", "N/A")
    data.setdefault("ativo", True)
    data.setdefault("sdea_ativo", False)
    data.setdefault("sdea_icao_validade", "")
    data.setdefault("instrutor_ativo", False)
    data.setdefault("instrutor_inicio", "")
    data.setdefault("instrutor_fim", "")
    data.setdefault("checador_ativo", False)
    data.setdefault("checador_inicio", "")
    data.setdefault("checador_fim", "")
    data.setdefault("checador_carta_designacao", "")
    data.setdefault("elegivel_adicional_excepcional", False)
    data.setdefault("remove_foto", False)
    if isinstance(data.get("remove_foto"), str):
        data["remove_foto"] = data["remove_foto"] == "1"
    for bool_key in ("ativo", "sdea_ativo", "instrutor_ativo", "checador_ativo", "elegivel_adicional_excepcional"):
        if isinstance(data.get(bool_key), str):
            data[bool_key] = data[bool_key] in {"on", "1", "true", "True"}
    return data

def build_pernoite_form_state(source=None):
    data = dict(source or {})
    for key in ("tripulante_id", "data_pernoite", "tipo_pernoite", "quantidade", "observacoes"):
        data.setdefault(key, "")
    data.setdefault("tipo_pernoite", "cobertura_base")
    return data

def build_adicional_excepcional_form_state(source=None):
    data = dict(source or {})
    for key in ("tripulante_id", "competencia", "valor", "observacao"):
        data.setdefault(key, "")
    data.setdefault("ativo", True)
    if isinstance(data.get("ativo"), str):
        data["ativo"] = data["ativo"] in {"on", "1", "true", "True"}
    return data

def build_equipamento_form_state(source=None):
    data = dict(source or {})
    data.setdefault("nome", "")
    data.setdefault("tipo", "")
    data.setdefault("categoria_financeira", "")
    data.setdefault("ativo", False)
    if isinstance(data.get("ativo"), str):
        data["ativo"] = data["ativo"] == "on"
    return data

def build_tipo_form_state(source=None):
    data = dict(source or {})
    data.setdefault("nome", "")
    data.setdefault("periodicidade_meses", "")
    data.setdefault("exige_equipamento", True)
    data.setdefault("ativo", False)
    if isinstance(data.get("exige_equipamento"), str):
        data["exige_equipamento"] = data["exige_equipamento"] == "on"
    if isinstance(data.get("ativo"), str):
        data["ativo"] = data["ativo"] == "on"
    return data

def build_treinamento_form_state(source=None):
    data = dict(source or {})
    data.setdefault("tripulante_id", "")
    data.setdefault("equipamento_id", "")
    data.setdefault("tipo_treinamento_id", "")
    data.setdefault("data_realizacao", "")
    data.setdefault("data_vencimento", "")
    data.setdefault("due_date_mode", "auto")
    data.setdefault("observacao", "")
    return data

def build_usuario_form_state(source=None):
    data = dict(source or {})
    data.setdefault("nome", "")
    data.setdefault("login", "")
    data.setdefault("email", "")
    data.setdefault("perfil", "operador")
    data.setdefault("ativo", False)
    raw_permissions = []
    if source is not None and hasattr(source, "getlist"):
        raw_permissions = source.getlist("permission_keys")
    elif isinstance(data.get("permission_keys"), list):
        raw_permissions = data.get("permission_keys") or []
    data["permission_keys"] = sorted(normalize_permissions(raw_permissions, perfil=data.get("perfil", "operador")))
    if isinstance(data.get("ativo"), str):
        data["ativo"] = data["ativo"] == "on"
    return data

def build_notificacao_form_state(source=None):
    data = dict(source or {})
    data.setdefault("email_destinatario", "")
    data.setdefault("ativo", False)
    if isinstance(data.get("ativo"), str):
        data["ativo"] = data["ativo"] == "on"
    return data
