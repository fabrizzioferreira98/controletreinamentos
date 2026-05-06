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
