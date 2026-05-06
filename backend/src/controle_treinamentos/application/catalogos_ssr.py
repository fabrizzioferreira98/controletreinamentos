from __future__ import annotations

from ..constants import DEFAULT_PAGE_SIZE
from ..contracts.equipamentos import validate_finance_categoria
from ..core.audit_utils import audit_event
from ..core.http_utils import build_pagination, get_required_int, get_required_text, normalize_page
from ..db import get_db
from ..repositories.catalogos import (
    count_equipamentos,
    count_tipos_treinamento,
    create_equipamento,
    create_tipo_treinamento,
    delete_equipamento,
    delete_tipo_treinamento,
    equipamento_has_linked_training,
    get_equipamento_by_id,
    get_equipamento_delete_target,
    get_tipo_treinamento_by_id,
    get_tipo_treinamento_delete_target,
    list_equipamentos_page,
    list_tipos_treinamento_page,
    tipo_treinamento_has_linked_training,
    update_equipamento,
    update_tipo_treinamento,
)
from ..repositories.dashboard_cache import clear_catalog_options_cache
from ..service_layers.form_builders import build_equipamento_form_state, build_tipo_form_state


class CatalogoNotFoundError(LookupError):
    pass


class CatalogoValidationError(ValueError):
    def __init__(self, message: str, *, state: dict):
        super().__init__(message)
        self.state = state


def _pagination_state(*, endpoint: str, page: int, per_page: int, total: int) -> dict:
    normalized_page = normalize_page(page, per_page, total)
    return {
        "page": normalized_page,
        "per_page": per_page,
        "offset": (normalized_page - 1) * per_page,
        "pagination": build_pagination(endpoint, normalized_page, per_page, total),
    }


def get_equipamentos_list_context(*, page: int, per_page: int = DEFAULT_PAGE_SIZE) -> dict:
    db = get_db()
    total = count_equipamentos(db)
    paging = _pagination_state(
        endpoint="cadastros.equipamentos_list",
        page=page,
        per_page=per_page,
        total=total,
    )
    return {
        "equipamentos": list_equipamentos_page(db, limit=paging["per_page"], offset=paging["offset"]),
        "pagination": paging["pagination"],
    }


def get_equipamento_form_context(*, equipamento_id: int | None = None) -> dict:
    if equipamento_id is None:
        return {"equipamento": None}
    db = get_db()
    equipamento = get_equipamento_by_id(db, equipamento_id=equipamento_id)
    if not equipamento:
        raise CatalogoNotFoundError("Equipamento nao encontrado.")
    return {"equipamento": equipamento}


def _equipamento_payload(form_data) -> tuple[dict, str, str, str | None, int]:
    state = build_equipamento_form_state(form_data)
    try:
        nome = get_required_text(form_data, "nome", "Nome")
        tipo = get_required_text(form_data, "tipo", "Tipo")
        categoria_financeira = validate_finance_categoria(form_data.get("categoria_financeira"))
    except ValueError as exc:
        raise CatalogoValidationError(str(exc), state=state) from exc
    state["categoria_financeira"] = categoria_financeira or ""
    return state, nome, tipo, categoria_financeira, 1 if form_data.get("ativo") else 0


def create_equipamento_from_form(form_data) -> dict:
    db = get_db()
    state, nome, tipo, categoria_financeira, ativo = _equipamento_payload(form_data)
    created = create_equipamento(
        db,
        nome=nome,
        tipo=tipo,
        categoria_financeira=categoria_financeira,
        ativo=ativo,
    )
    audit_event(db, "equipamento", created["id"], "create", novo=state)
    db.commit()
    clear_catalog_options_cache()
    return {"id": created["id"], "equipamento": state}


def update_equipamento_from_form(*, equipamento_id: int, form_data) -> dict:
    db = get_db()
    equipamento = get_equipamento_by_id(db, equipamento_id=equipamento_id)
    if not equipamento:
        raise CatalogoNotFoundError("Equipamento nao encontrado.")
    state, nome, tipo, categoria_financeira, ativo = _equipamento_payload(form_data)
    update_equipamento(
        db,
        equipamento_id=equipamento_id,
        nome=nome,
        tipo=tipo,
        categoria_financeira=categoria_financeira,
        ativo=ativo,
    )
    audit_event(db, "equipamento", equipamento_id, "update", anterior=equipamento, novo=state)
    db.commit()
    clear_catalog_options_cache()
    return {"id": equipamento_id, "equipamento": state}


def delete_equipamento_with_guards(*, equipamento_id: int) -> dict:
    db = get_db()
    equipamento = get_equipamento_delete_target(db, equipamento_id=equipamento_id)
    if not equipamento:
        raise CatalogoNotFoundError("Equipamento nao encontrado.")
    if equipamento_has_linked_training(db, equipamento_id=equipamento_id):
        return {"deleted": False, "blocked": True}
    audit_event(db, "equipamento", equipamento_id, "delete", anterior=equipamento)
    delete_equipamento(db, equipamento_id=equipamento_id)
    db.commit()
    clear_catalog_options_cache()
    return {"deleted": True, "blocked": False}


def get_tipos_treinamento_list_context(*, page: int, per_page: int = DEFAULT_PAGE_SIZE) -> dict:
    db = get_db()
    total = count_tipos_treinamento(db)
    paging = _pagination_state(
        endpoint="cadastros.tipos_list",
        page=page,
        per_page=per_page,
        total=total,
    )
    return {
        "tipos": list_tipos_treinamento_page(db, limit=paging["per_page"], offset=paging["offset"]),
        "pagination": paging["pagination"],
    }


def get_tipo_treinamento_form_context(*, tipo_id: int | None = None) -> dict:
    if tipo_id is None:
        return {"tipo": None}
    db = get_db()
    tipo = get_tipo_treinamento_by_id(db, tipo_id=tipo_id)
    if not tipo:
        raise CatalogoNotFoundError("Tipo de treinamento nao encontrado.")
    return {"tipo": tipo}


def _tipo_treinamento_payload(form_data) -> tuple[dict, str, int, int, int]:
    state = build_tipo_form_state(form_data)
    try:
        nome = get_required_text(form_data, "nome", "Nome")
        periodicidade_meses = get_required_int(form_data, "periodicidade_meses", "Periodicidade em meses")
        if periodicidade_meses <= 0:
            raise ValueError("O campo 'Periodicidade em meses' deve ser maior que zero.")
    except ValueError as exc:
        raise CatalogoValidationError(str(exc), state=state) from exc
    return (
        state,
        nome,
        periodicidade_meses,
        1 if form_data.get("exige_equipamento") else 0,
        1 if form_data.get("ativo") else 0,
    )


def create_tipo_treinamento_from_form(form_data) -> dict:
    db = get_db()
    state, nome, periodicidade_meses, exige_equipamento, ativo = _tipo_treinamento_payload(form_data)
    created = create_tipo_treinamento(
        db,
        nome=nome,
        periodicidade_meses=periodicidade_meses,
        exige_equipamento=exige_equipamento,
        ativo=ativo,
    )
    audit_event(db, "tipo_treinamento", created["id"], "create", novo=state)
    db.commit()
    clear_catalog_options_cache()
    return {"id": created["id"], "tipo": state}


def update_tipo_treinamento_from_form(*, tipo_id: int, form_data) -> dict:
    db = get_db()
    tipo = get_tipo_treinamento_by_id(db, tipo_id=tipo_id)
    if not tipo:
        raise CatalogoNotFoundError("Tipo de treinamento nao encontrado.")
    state, nome, periodicidade_meses, exige_equipamento, ativo = _tipo_treinamento_payload(form_data)
    update_tipo_treinamento(
        db,
        tipo_id=tipo_id,
        nome=nome,
        periodicidade_meses=periodicidade_meses,
        exige_equipamento=exige_equipamento,
        ativo=ativo,
    )
    audit_event(db, "tipo_treinamento", tipo_id, "update", anterior=tipo, novo=state)
    db.commit()
    clear_catalog_options_cache()
    return {"id": tipo_id, "tipo": state}


def delete_tipo_treinamento_with_guards(*, tipo_id: int) -> dict:
    db = get_db()
    tipo = get_tipo_treinamento_delete_target(db, tipo_id=tipo_id)
    if not tipo:
        raise CatalogoNotFoundError("Tipo de treinamento nao encontrado.")
    if tipo_treinamento_has_linked_training(db, tipo_id=tipo_id):
        return {"deleted": False, "blocked": True}
    audit_event(db, "tipo_treinamento", tipo_id, "delete", anterior=tipo)
    delete_tipo_treinamento(db, tipo_id=tipo_id)
    db.commit()
    clear_catalog_options_cache()
    return {"deleted": True, "blocked": False}
