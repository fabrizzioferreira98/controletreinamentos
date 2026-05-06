from __future__ import annotations

from ..core.document_storage import database_blob_for_persistence


def _query_tripulante_file_only(db, *, tripulante_id: int):
    return db.execute(
        """
        SELECT
            a.id,
            a.tripulante_id,
            a.tipo_documento,
            a.nome_original,
            a.nome_interno,
            a.mime_type,
            a.tamanho_bytes,
            a.storage_ref,
            (a.arquivo_pdf IS NOT NULL) AS has_db_blob,
            a.arquivo_hash,
            a.status,
            a.enviado_por,
            a.enviado_em,
            a.substitui_arquivo_id,
            a.removido_por,
            a.removido_em,
            a.motivo_status,
            ue.nome AS enviado_por_nome,
            ur.nome AS removido_por_nome,
            'tripulante_file'::TEXT AS origem,
            a.id AS origem_id,
            NULL::BIGINT AS treinamento_id,
            'Aba File'::TEXT AS origem_label
        FROM tripulante_arquivos_pdf a
        LEFT JOIN usuarios ue ON ue.id = a.enviado_por
        LEFT JOIN usuarios ur ON ur.id = a.removido_por
        WHERE a.tripulante_id = %s
        ORDER BY a.enviado_em DESC, a.id DESC
        """,
        (tripulante_id,),
    ).fetchall()


def fetch_tripulante_file_rows(db, *, tripulante_id: int, include_training: bool = True):
    if not include_training:
        return _query_tripulante_file_only(db, tripulante_id=tripulante_id)
    return db.execute(
        """
        SELECT *
        FROM (
            SELECT
                a.id,
                a.tripulante_id,
                a.tipo_documento,
                a.nome_original,
                a.nome_interno,
                a.mime_type,
                a.tamanho_bytes,
                a.storage_ref,
                (a.arquivo_pdf IS NOT NULL) AS has_db_blob,
                a.arquivo_hash,
                a.status,
                a.enviado_por,
                a.enviado_em,
                a.substitui_arquivo_id,
                a.removido_por,
                a.removido_em,
                a.motivo_status,
                ue.nome AS enviado_por_nome,
                ur.nome AS removido_por_nome,
                'tripulante_file'::TEXT AS origem,
                a.id AS origem_id,
                NULL::BIGINT AS treinamento_id,
                'Aba File'::TEXT AS origem_label
            FROM tripulante_arquivos_pdf a
            LEFT JOIN usuarios ue ON ue.id = a.enviado_por
            LEFT JOIN usuarios ur ON ur.id = a.removido_por
            WHERE a.tripulante_id = %s

            UNION ALL

            SELECT
                tpdf.id,
                t.tripulante_id,
                COALESCE(NULLIF(TRIM(tt.nome), ''), 'treinamento') AS tipo_documento,
                tpdf.nome_original,
                tpdf.nome_interno,
                tpdf.mime_type,
                tpdf.tamanho_bytes,
                tpdf.storage_ref,
                (tpdf.arquivo_pdf IS NOT NULL) AS has_db_blob,
                tpdf.arquivo_hash,
                COALESCE(NULLIF(TRIM(tpdf.status), ''), 'ativo') AS status,
                tpdf.enviado_por,
                tpdf.enviado_em,
                NULL::BIGINT AS substitui_arquivo_id,
                NULL::INTEGER AS removido_por,
                NULL::TIMESTAMP AS removido_em,
                NULL::TEXT AS motivo_status,
                ue.nome AS enviado_por_nome,
                NULL::TEXT AS removido_por_nome,
                'treinamento'::TEXT AS origem,
                tpdf.id AS origem_id,
                t.id AS treinamento_id,
                COALESCE(NULLIF(TRIM(tt.nome), ''), 'Treinamento') AS origem_label
            FROM treinamento_anexos_pdf tpdf
            JOIN treinamentos t ON t.id = tpdf.treinamento_id
            LEFT JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
            LEFT JOIN usuarios ue ON ue.id = tpdf.enviado_por
            WHERE t.tripulante_id = %s
              AND COALESCE(NULLIF(TRIM(tpdf.status), ''), 'ativo') <> 'removido'
        ) consolidados
        ORDER BY enviado_em DESC, id DESC
        """,
        (tripulante_id, tripulante_id),
    ).fetchall()


def find_tripulante_file_by_id(db, *, tripulante_id: int, arquivo_id: int):
    return db.execute(
        """
        SELECT
            id,
            tripulante_id,
            tipo_documento,
            nome_original,
            nome_interno,
            mime_type,
            tamanho_bytes,
            storage_ref,
            arquivo_pdf,
            arquivo_hash,
            status,
            enviado_por,
            enviado_em,
            substitui_arquivo_id,
            removido_por,
            removido_em,
            motivo_status
        FROM tripulante_arquivos_pdf
        WHERE id = %s
          AND tripulante_id = %s
        """,
        (arquivo_id, tripulante_id),
    ).fetchone()


def find_training_attachment_by_tripulante(db, *, tripulante_id: int, anexo_id: int):
    return db.execute(
        """
        SELECT
            tpdf.id,
            tpdf.treinamento_id,
            tpdf.nome_original,
            tpdf.mime_type,
            tpdf.storage_ref,
            (tpdf.arquivo_pdf IS NOT NULL) AS has_db_blob,
            tpdf.arquivo_pdf
        FROM treinamento_anexos_pdf tpdf
        JOIN treinamentos t ON t.id = tpdf.treinamento_id
        WHERE tpdf.id = %s
          AND t.tripulante_id = %s
          AND COALESCE(NULLIF(TRIM(tpdf.status), ''), 'ativo') <> 'removido'
        """,
        (anexo_id, tripulante_id),
    ).fetchone()


def find_active_duplicate_hash(
    db,
    *,
    tripulante_id: int,
    arquivo_hash: str,
    exclude_id: int | None = None,
):
    query = """
        SELECT id, nome_original
        FROM tripulante_arquivos_pdf
        WHERE tripulante_id = %s
          AND arquivo_hash = %s
          AND status = 'ativo'
    """
    params: list = [tripulante_id, arquivo_hash]
    if exclude_id is not None:
        query += " AND id <> %s"
        params.append(exclude_id)
    query += " LIMIT 1"
    return db.execute(query, tuple(params)).fetchone()


def insert_tripulante_file(
    db,
    *,
    tripulante_id: int,
    tipo_documento: str,
    payload: dict,
    enviado_por: int,
    substitui_arquivo_id: int | None = None,
):
    return db.execute(
        """
        INSERT INTO tripulante_arquivos_pdf
        (
            tripulante_id,
            tipo_documento,
            nome_original,
            nome_interno,
            mime_type,
            tamanho_bytes,
            storage_ref,
            arquivo_pdf,
            arquivo_hash,
            status,
            enviado_por,
            substitui_arquivo_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ativo', %s, %s)
        RETURNING id
        """,
        (
            tripulante_id,
            tipo_documento,
            payload["nome_original"],
            payload["nome_interno"],
            payload["mime_type"],
            payload["tamanho_bytes"],
            payload["storage_ref"],
            database_blob_for_persistence(payload, allow_legacy_database_blob=False),
            payload["arquivo_hash"],
            enviado_por,
            substitui_arquivo_id,
        ),
    ).fetchone()
