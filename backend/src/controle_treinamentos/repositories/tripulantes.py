from __future__ import annotations

from ..constants import TRIPULANTE_CATEGORIA_OPTIONS, TRIPULANTE_FUNCAO_OPTIONS
from ..core.http_utils import digits_only
from ..service_layers.tripulante_operational_status import (
    build_tripulante_operational_base_contract,
    build_tripulante_operational_status_contract,
    canonical_pilot_status,
)


def _decorate_tripulante_row(row):
    if not row:
        return None
    payload = dict(row)
    payload.update(build_tripulante_operational_base_contract(payload))
    payload.update(build_tripulante_operational_status_contract(payload))
    return payload


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
        clauses.append("t.nome LIKE %s")
        params.append(f"%{nome}%")
    if status:
        pilot_status = canonical_pilot_status(status)
        clauses.append("LOWER(TRIM(COALESCE(p.status, ''))) = %s")
        params.append(pilot_status or (status or "").strip().lower())
    if base:
        clauses.append("LOWER(TRIM(COALESCE(pb.nome, ''))) = LOWER(%s)")
        params.append(base)
    if funcao in TRIPULANTE_FUNCAO_OPTIONS:
        clauses.append("t.funcao_operacional = %s")
        params.append(funcao)
    if categoria in TRIPULANTE_CATEGORIA_OPTIONS:
        clauses.append("t.categoria_operacional = %s")
        params.append(categoria)
    if ativo in {"1", "0"}:
        clauses.append("t.ativo = %s")
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
        f"""
        SELECT COUNT(*) AS total
        FROM tripulantes t
        LEFT JOIN pilotos p ON p.tripulante_id = t.id
        LEFT JOIN bases pb ON pb.id = p.base_id
        {where}
        """,
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
            t.id,
            t.nome,
            t.cpf,
            t.licenca_anac,
            t.email,
            t.telefone,
            t.base AS base_snapshot_compat,
            p.base_id AS piloto_base_id,
            pb.nome AS piloto_base_nome,
            t.status AS status_snapshot_compat,
            p.status AS piloto_status,
            t.ativo,
            t.funcao_operacional,
            t.categoria_operacional,
            t.sdea_ativo,
            t.sdea_icao_validade,
            t.instrutor_ativo,
            t.instrutor_inicio,
            t.instrutor_fim,
            t.checador_ativo,
            t.checador_inicio,
            t.checador_fim,
            t.checador_carta_designacao,
            t.elegivel_adicional_excepcional,
            CASE
                WHEN t.foto_storage_ref IS NOT NULL AND TRIM(t.foto_storage_ref) <> '' THEN 'storage'
                WHEN t.foto_base64 IS NOT NULL AND TRIM(t.foto_base64) <> '' THEN 'base64'
                ELSE 'empty'
            END AS photo_source_hint,
            COALESCE(
                (
                    (t.foto_base64 IS NOT NULL AND TRIM(t.foto_base64) <> '')
                    OR (t.foto_storage_ref IS NOT NULL AND TRIM(t.foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes t
        LEFT JOIN pilotos p ON p.tripulante_id = t.id
        LEFT JOIN bases pb ON pb.id = p.base_id
        {where}
        ORDER BY t.nome
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    ).fetchall()
    return [_decorate_tripulante_row(row) for row in rows]


def fetch_tripulante_detail(db, *, tripulante_id: int):
    row = db.execute(
        """
        SELECT
            t.id,
            t.nome,
            t.cpf,
            t.licenca_anac,
            t.email,
            t.telefone,
            t.base AS base_snapshot_compat,
            p.base_id AS piloto_base_id,
            pb.nome AS piloto_base_nome,
            t.status AS status_snapshot_compat,
            p.status AS piloto_status,
            t.observacoes,
            t.ativo,
            t.funcao_operacional,
            t.categoria_operacional,
            t.sdea_ativo,
            t.sdea_icao_validade,
            t.instrutor_ativo,
            t.instrutor_inicio,
            t.instrutor_fim,
            t.checador_ativo,
            t.checador_inicio,
            t.checador_fim,
            t.checador_carta_designacao,
            t.elegivel_adicional_excepcional,
            t.foto_base64,
            t.foto_storage_ref,
            t.foto_mime_type,
            COALESCE(
                (
                    (t.foto_base64 IS NOT NULL AND TRIM(t.foto_base64) <> '')
                    OR (t.foto_storage_ref IS NOT NULL AND TRIM(t.foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes t
        LEFT JOIN pilotos p ON p.tripulante_id = t.id
        LEFT JOIN bases pb ON pb.id = p.base_id
        WHERE t.id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return _decorate_tripulante_row(row)


def fetch_tripulante_for_write(db, *, tripulante_id: int):
    row = db.execute(
        """
        SELECT
            t.*,
            t.base AS base_snapshot_compat,
            p.base_id AS piloto_base_id,
            pb.nome AS piloto_base_nome,
            t.status AS status_snapshot_compat,
            p.status AS piloto_status,
            COALESCE(
                (
                    (t.foto_base64 IS NOT NULL AND TRIM(t.foto_base64) <> '')
                    OR (t.foto_storage_ref IS NOT NULL AND TRIM(t.foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes t
        LEFT JOIN pilotos p ON p.tripulante_id = t.id
        LEFT JOIN bases pb ON pb.id = p.base_id
        WHERE t.id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return _decorate_tripulante_row(row)


def fetch_tripulante_dependencies(db, *, tripulante_id: int):
    row = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM treinamentos WHERE tripulante_id = %s) AS treinamentos,
            (SELECT COUNT(*) FROM pernoites_operacionais WHERE tripulante_id = %s) AS pernoites,
            (SELECT COUNT(*) FROM tripulante_arquivos_pdf WHERE tripulante_id = %s) AS arquivos_file,
            (
                SELECT COUNT(*)
                FROM financeiro_missoes_operacionais
                WHERE comandante_tripulante_id = %s OR copiloto_tripulante_id = %s
            ) AS financeiro_missoes,
            (SELECT COUNT(*) FROM financeiro_missao_tripulantes WHERE tripulante_id = %s) AS financeiro_missao_tripulantes,
            (SELECT COUNT(*) FROM financeiro_calculos_horarios WHERE tripulante_id = %s) AS financeiro_calculos_horarios,
            (SELECT COUNT(*) FROM financeiro_calculos_produtividade WHERE tripulante_id = %s) AS financeiro_calculos_produtividade
        """,
        (
            tripulante_id,
            tripulante_id,
            tripulante_id,
            tripulante_id,
            tripulante_id,
            tripulante_id,
            tripulante_id,
            tripulante_id,
        ),
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
            nome, cpf, licenca_anac, email, telefone, base, status, observacoes,
            foto_storage_ref, foto_mime_type, possui_foto, ativo, funcao_operacional, categoria_operacional,
            sdea_ativo, sdea_icao_validade, instrutor_ativo, instrutor_inicio, instrutor_fim,
            checador_ativo, checador_inicio, checador_fim, checador_carta_designacao,
            elegivel_adicional_excepcional
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            False,
            1 if data["ativo"] else 0,
            data["funcao_operacional"],
            data["categoria_operacional"],
            1 if data["sdea_ativo"] else 0,
            data["sdea_icao_validade"],
            1 if data["instrutor_ativo"] else 0,
            data["instrutor_inicio"],
            data["instrutor_fim"],
            1 if data["checador_ativo"] else 0,
            data["checador_inicio"],
            data["checador_fim"],
            data["checador_carta_designacao"],
            1 if data["elegivel_adicional_excepcional"] else 0,
        ),
    ).fetchone()
    return int(row["id"])


def update_tripulante_photo_state(db, *, tripulante_id: int, photo_state: dict) -> None:
    clear_legacy_photo_base64 = bool(photo_state.get("clear_legacy_photo_base64"))
    if clear_legacy_photo_base64:
        query = """
        UPDATE tripulantes
        SET foto_base64 = NULL,
            foto_storage_ref = %s,
            foto_mime_type = %s,
            possui_foto = %s
        WHERE id = %s
        """
    else:
        query = """
        UPDATE tripulantes
        SET foto_storage_ref = %s,
            foto_mime_type = %s,
            possui_foto = %s
        WHERE id = %s
        """
    db.execute(
        query,
        (
            photo_state["foto_storage_ref"],
            photo_state["foto_mime_type"],
            photo_state["possui_foto"],
            tripulante_id,
        ),
    )


def update_tripulante(db, *, tripulante_id: int, data: dict, photo_state: dict) -> None:
    clear_legacy_photo_base64 = bool(photo_state.get("clear_legacy_photo_base64"))
    if clear_legacy_photo_base64:
        query = """
        UPDATE tripulantes
        SET nome = %s, cpf = %s, licenca_anac = %s, email = %s, telefone = %s,
            observacoes = %s, foto_base64 = NULL, foto_storage_ref = %s, foto_mime_type = %s,
            possui_foto = %s, ativo = %s, funcao_operacional = %s, categoria_operacional = %s,
            sdea_ativo = %s, sdea_icao_validade = %s,
            instrutor_ativo = %s, instrutor_inicio = %s, instrutor_fim = %s,
            checador_ativo = %s, checador_inicio = %s, checador_fim = %s,
            checador_carta_designacao = %s,
            elegivel_adicional_excepcional = %s
        WHERE id = %s
        """
    else:
        query = """
        UPDATE tripulantes
        SET nome = %s, cpf = %s, licenca_anac = %s, email = %s, telefone = %s,
            observacoes = %s, foto_storage_ref = %s, foto_mime_type = %s,
            possui_foto = %s, ativo = %s, funcao_operacional = %s, categoria_operacional = %s,
            sdea_ativo = %s, sdea_icao_validade = %s,
            instrutor_ativo = %s, instrutor_inicio = %s, instrutor_fim = %s,
            checador_ativo = %s, checador_inicio = %s, checador_fim = %s,
            checador_carta_designacao = %s,
            elegivel_adicional_excepcional = %s
        WHERE id = %s
        """
    db.execute(
        query,
        (
            data["nome"],
            data["cpf"],
            data["licenca_anac"],
            data["email"],
            data["telefone"],
            data["observacoes"],
            photo_state["foto_storage_ref"],
            photo_state["foto_mime_type"],
            photo_state["possui_foto"],
            1 if data["ativo"] else 0,
            data["funcao_operacional"],
            data["categoria_operacional"],
            1 if data["sdea_ativo"] else 0,
            data["sdea_icao_validade"],
            1 if data["instrutor_ativo"] else 0,
            data["instrutor_inicio"],
            data["instrutor_fim"],
            1 if data["checador_ativo"] else 0,
            data["checador_inicio"],
            data["checador_fim"],
            data["checador_carta_designacao"],
            1 if data["elegivel_adicional_excepcional"] else 0,
            tripulante_id,
        ),
    )


def fetch_tripulante_delete_target(db, *, tripulante_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT
            t.id,
            t.nome,
            t.cpf,
            t.licenca_anac,
            t.base AS base_snapshot_compat,
            p.base_id AS piloto_base_id,
            pb.nome AS piloto_base_nome,
            t.status AS status_snapshot_compat,
            p.status AS piloto_status,
            t.ativo,
            t.foto_storage_ref
        FROM tripulantes t
        LEFT JOIN pilotos p ON p.tripulante_id = t.id
        LEFT JOIN bases pb ON pb.id = p.base_id
        WHERE t.id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return _decorate_tripulante_row(row)


def inactivate_tripulante(db, *, tripulante_id: int, status_snapshot_compat: str) -> None:
    db.execute(
        "UPDATE tripulantes SET ativo = 0, status = %s WHERE id = %s",
        (status_snapshot_compat, tripulante_id),
    )


def delete_historico_status_piloto_by_pilot_ids(db, *, linked_pilot_ids: list[int]) -> None:
    db.execute("DELETE FROM historico_status_piloto WHERE piloto_id = ANY(%s)", (linked_pilot_ids,))


def delete_pilotos_by_ids(db, *, linked_pilot_ids: list[int]) -> None:
    db.execute("DELETE FROM pilotos WHERE id = ANY(%s)", (linked_pilot_ids,))


def delete_tripulante(db, *, tripulante_id: int) -> None:
    db.execute("DELETE FROM tripulantes WHERE id = %s", (tripulante_id,))
