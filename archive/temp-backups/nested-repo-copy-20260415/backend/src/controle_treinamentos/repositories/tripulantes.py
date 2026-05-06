from __future__ import annotations

from ..constants import TRIPULANTE_CATEGORIA_OPTIONS, TRIPULANTE_FUNCAO_OPTIONS
from ..core.http_utils import digits_only
from ..service_layers.domain_validation import tripulante_status_filter_values


def build_tripulante_filters(*, nome="", status="", base="", funcao="", categoria="", ativo=""):
    clauses = []
    params = []
    nome = (nome or "").strip()
    status = (status or "").strip()
    base = (base or "").strip()
    funcao = (funcao or "").strip()
    categoria = (categoria or "").strip()
    ativo = str(ativo or "").strip()

    if nome:
        clauses.append("nome LIKE %s")
        params.append(f"%{nome}%")
    if status:
        status_values = tripulante_status_filter_values(status)
        if len(status_values) == 1:
            clauses.append("status = %s")
            params.append(status_values[0])
        elif len(status_values) > 1:
            clauses.append("status = ANY(%s)")
            params.append(list(status_values))
    if base:
        clauses.append("base = %s")
        params.append(base)
    if funcao in TRIPULANTE_FUNCAO_OPTIONS:
        clauses.append("funcao_operacional = %s")
        params.append(funcao)
    if categoria in TRIPULANTE_CATEGORIA_OPTIONS:
        clauses.append("categoria_operacional = %s")
        params.append(categoria)
    if ativo in {"1", "0"}:
        clauses.append("ativo = %s")
        params.append(int(ativo))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, tuple(params)


def count_tripulantes(db, *, nome="", status="", base="", funcao="", categoria="", ativo="") -> int:
    where, params = build_tripulante_filters(
        nome=nome,
        status=status,
        base=base,
        funcao=funcao,
        categoria=categoria,
        ativo=ativo,
    )
    row = db.execute(
        f"SELECT COUNT(*) AS total FROM tripulantes {where}",
        params,
    ).fetchone()
    return int(row["total"] or 0)


def fetch_tripulante_list_page(
    db,
    *,
    nome="",
    status="",
    base="",
    funcao="",
    categoria="",
    ativo="",
    limit=20,
    offset=0,
):
    where, params = build_tripulante_filters(
        nome=nome,
        status=status,
        base=base,
        funcao=funcao,
        categoria=categoria,
        ativo=ativo,
    )
    rows = db.execute(
        f"""
        SELECT
            id,
            nome,
            cpf,
            licenca_anac,
            email,
            telefone,
            base,
            status,
            ativo,
            funcao_operacional,
            categoria_operacional,
            sdea_ativo,
            instrutor_ativo,
            checador_ativo,
            elegivel_adicional_excepcional,
            COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes
        {where}
        ORDER BY nome
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_tripulante_detail(db, *, tripulante_id: int):
    row = db.execute(
        """
        SELECT
            id,
            nome,
            cpf,
            licenca_anac,
            email,
            telefone,
            base,
            status,
            observacoes,
            ativo,
            funcao_operacional,
            categoria_operacional,
            sdea_ativo,
            instrutor_ativo,
            checador_ativo,
            elegivel_adicional_excepcional,
            foto_storage_ref,
            foto_mime_type,
            COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_tripulante_for_write(db, *, tripulante_id: int):
    row = db.execute(
        """
        SELECT
            *,
            COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_tripulante_dependencies(db, *, tripulante_id: int):
    row = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM treinamentos WHERE tripulante_id = %s) AS treinamentos,
            (SELECT COUNT(*) FROM missao_tripulantes WHERE tripulante_id = %s) AS missoes,
            (SELECT COUNT(*) FROM pernoites_operacionais WHERE tripulante_id = %s) AS pernoites,
            (SELECT COUNT(*) FROM produtividade_adicionais_excepcionais WHERE tripulante_id = %s) AS adicionais,
            (SELECT COUNT(*) FROM produtividade_conferencias WHERE tripulante_id = %s) AS conferencias,
            (SELECT COUNT(*) FROM tripulante_arquivos_pdf WHERE tripulante_id = %s) AS arquivos_file
        """,
        (tripulante_id, tripulante_id, tripulante_id, tripulante_id, tripulante_id, tripulante_id),
    ).fetchone()
    return dict(row) if row else {}


def find_linked_pilot_ids(db, *, tripulante_id: int) -> list[int]:
    rows = db.execute(
        "SELECT id FROM pilotos WHERE tripulante_id = %s",
        (tripulante_id,),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def find_tripulante_by_cpf(db, cpf: str, *, exclude_id: int | None = None):
    cpf_digits = digits_only(cpf)
    if len(cpf_digits) != 11:
        return None
    return db.execute(
        """
        SELECT id
        FROM tripulantes
        WHERE regexp_replace(COALESCE(cpf, ''), '\\D', '', 'g') = %s
          AND (%s IS NULL OR id != %s)
        LIMIT 1
        """,
        (cpf_digits, exclude_id, exclude_id),
    ).fetchone()


def create_tripulante(db, *, data: dict) -> int:
    row = db.execute(
        """
        INSERT INTO tripulantes (
            nome, cpf, licenca_anac, email, telefone, base, status, observacoes, foto_base64,
            foto_storage_ref, foto_mime_type, possui_foto, ativo, funcao_operacional, categoria_operacional,
            sdea_ativo, instrutor_ativo, checador_ativo, elegivel_adicional_excepcional
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            data["nome"],
            data["cpf"],
            data["licenca_anac"],
            data["email"],
            data["telefone"],
            data["base"],
            data["status"],
            data["observacoes"],
            None,
            None,
            None,
            False,
            1 if data["ativo"] else 0,
            data["funcao_operacional"],
            data["categoria_operacional"],
            1 if data["sdea_ativo"] else 0,
            1 if data["instrutor_ativo"] else 0,
            1 if data["checador_ativo"] else 0,
            1 if data["elegivel_adicional_excepcional"] else 0,
        ),
    ).fetchone()
    return int(row["id"])


def update_tripulante_photo_state(db, *, tripulante_id: int, photo_state: dict) -> None:
    db.execute(
        """
        UPDATE tripulantes
        SET foto_base64 = %s,
            foto_storage_ref = %s,
            foto_mime_type = %s,
            possui_foto = %s
        WHERE id = %s
        """,
        (
            photo_state["foto_base64"],
            photo_state["foto_storage_ref"],
            photo_state["foto_mime_type"],
            photo_state["possui_foto"],
            tripulante_id,
        ),
    )


def update_tripulante(db, *, tripulante_id: int, data: dict, photo_state: dict) -> None:
    db.execute(
        """
        UPDATE tripulantes
        SET nome = %s, cpf = %s, licenca_anac = %s, email = %s, telefone = %s, base = %s, status = %s,
            observacoes = %s, foto_base64 = %s, foto_storage_ref = %s, foto_mime_type = %s,
            possui_foto = %s, ativo = %s, funcao_operacional = %s, categoria_operacional = %s,
            sdea_ativo = %s, instrutor_ativo = %s, checador_ativo = %s, elegivel_adicional_excepcional = %s
        WHERE id = %s
        """,
        (
            data["nome"],
            data["cpf"],
            data["licenca_anac"],
            data["email"],
            data["telefone"],
            data["base"],
            data["status"],
            data["observacoes"],
            photo_state["foto_base64"],
            photo_state["foto_storage_ref"],
            photo_state["foto_mime_type"],
            photo_state["possui_foto"],
            1 if data["ativo"] else 0,
            data["funcao_operacional"],
            data["categoria_operacional"],
            1 if data["sdea_ativo"] else 0,
            1 if data["instrutor_ativo"] else 0,
            1 if data["checador_ativo"] else 0,
            1 if data["elegivel_adicional_excepcional"] else 0,
            tripulante_id,
        ),
    )


def fetch_tripulante_delete_target(db, *, tripulante_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT id, nome, cpf, licenca_anac, base, status, ativo, foto_storage_ref
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return dict(row) if row else None


def inactivate_tripulante(db, *, tripulante_id: int, status: str) -> None:
    db.execute(
        "UPDATE tripulantes SET ativo = 0, status = %s WHERE id = %s",
        (status, tripulante_id),
    )


def delete_historico_status_piloto_by_pilot_ids(db, *, linked_pilot_ids: list[int]) -> None:
    db.execute("DELETE FROM historico_status_piloto WHERE piloto_id = ANY(%s)", (linked_pilot_ids,))


def delete_pilotos_by_ids(db, *, linked_pilot_ids: list[int]) -> None:
    db.execute("DELETE FROM pilotos WHERE id = ANY(%s)", (linked_pilot_ids,))


def delete_tripulante(db, *, tripulante_id: int) -> None:
    db.execute("DELETE FROM tripulantes WHERE id = %s", (tripulante_id,))
