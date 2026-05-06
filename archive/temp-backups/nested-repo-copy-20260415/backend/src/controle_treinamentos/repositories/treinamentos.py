from __future__ import annotations

from datetime import timedelta

from ..repositories.dashboard_cache import fetch_cached_rows
from ..services import business_today


def build_training_filters(*, tripulante="", equipamento="", tipo="", status="", periodo=""):
    clauses = []
    params = []
    tripulante = (tripulante or "").strip()
    equipamento = (equipamento or "").strip()
    tipo = (tipo or "").strip()
    status = (status or "").strip()
    periodo = (periodo or "").strip()

    if tripulante:
        if not tripulante.isdigit():
            raise ValueError("Filtro de tripulante inválido.")
        clauses.append("c.id = %s")
        params.append(int(tripulante))
    if equipamento:
        if not equipamento.isdigit():
            raise ValueError("Filtro de equipamento inválido.")
        clauses.append("e.id = %s")
        params.append(int(equipamento))
    if tipo:
        if not tipo.isdigit():
            raise ValueError("Filtro de tipo inválido.")
        clauses.append("tt.id = %s")
        params.append(int(tipo))

    today = business_today()
    if periodo == "7":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=7)])
    elif periodo == "30":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=30)])
    elif periodo == "60":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=60)])
    elif periodo == "90":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento BETWEEN %s AND %s")
        params.extend([today, today + timedelta(days=90)])
    elif periodo == "expired":
        clauses.append("t.data_vencimento IS NOT NULL AND t.data_vencimento < %s")
        params.append(today)

    if status in {"vencido", "a vencer", "regular", "sem informação", "sem informaÃ§Ã£o"}:
        if status in {"sem informação", "sem informaÃ§Ã£o"}:
            clauses.append("t.data_vencimento IS NULL")
        elif status == "vencido":
            clauses.append("t.data_vencimento < %s")
            params.append(today)
        elif status == "a vencer":
            clauses.append("t.data_vencimento >= %s AND t.data_vencimento <= %s")
            params.extend([today, today + timedelta(days=30)])
        elif status == "regular":
            clauses.append("t.data_vencimento > %s")
            params.append(today + timedelta(days=30))

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_clause, tuple(params)


def count_treinamentos(db, *, tripulante="", equipamento="", tipo="", status="", periodo="") -> dict:
    where_clause, params = build_training_filters(
        tripulante=tripulante,
        equipamento=equipamento,
        tipo=tipo,
        status=status,
        periodo=periodo,
    )
    today = business_today()
    row = db.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE t.data_vencimento IS NULL) AS sem_informacao,
            COUNT(*) FILTER (WHERE t.data_vencimento < %s) AS vencido,
            COUNT(*) FILTER (
                WHERE t.data_vencimento >= %s
                  AND t.data_vencimento <= %s
            ) AS a_vencer,
            COUNT(*) FILTER (WHERE t.data_vencimento > %s) AS regular
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN equipamentos e ON e.id = t.equipamento_id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        {where_clause}
        """,
        (today, today, today + timedelta(days=30), today + timedelta(days=30), *params),
    ).fetchone()
    return dict(row)


def fetch_treinamento_detail(db, *, treinamento_id: int):
    row = db.execute(
        """
        SELECT
            t.*,
            c.nome AS tripulante_nome,
            e.nome AS equipamento_nome,
            tt.nome AS tipo_treinamento_nome
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN equipamentos e ON e.id = t.equipamento_id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        WHERE t.id = %s
        """,
        (treinamento_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_treinamento_attachments(db, *, treinamento_id: int):
    rows = db.execute(
        """
        SELECT
            a.id,
            a.treinamento_id,
            a.nome_original,
            a.nome_interno,
            a.mime_type,
            a.tamanho_bytes,
            a.storage_ref,
            a.arquivo_hash,
            a.status,
            a.enviado_por,
            a.enviado_em,
            u.nome AS enviado_por_nome
        FROM treinamento_anexos_pdf a
        LEFT JOIN usuarios u ON u.id = a.enviado_por
        WHERE a.treinamento_id = %s
        ORDER BY a.enviado_em DESC, a.id DESC
        """,
        (treinamento_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_options(db, *, treinamento_id=None, selected_equipment_id=None, selected_tipo_id=None):
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
    attachments = fetch_treinamento_attachments(db, treinamento_id=treinamento_id) if treinamento_id else []
    return {
        "tripulantes": [dict(row) for row in tripulantes],
        "equipamentos": [dict(row) for row in equipamentos],
        "tipos": [dict(row) for row in tipos],
        "attachments": attachments,
    }


def create_treinamento(db, *, data: dict) -> int:
    row = db.execute(
        """
        INSERT INTO treinamentos
        (tripulante_id, equipamento_id, tipo_treinamento_id, data_realizacao, data_vencimento, observacao)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            data["tripulante_id"],
            data["equipamento_id"],
            data["tipo_treinamento_id"],
            data["data_realizacao"],
            data["data_vencimento"],
            data["observacao"],
        ),
    ).fetchone()
    return int(row["id"])


def update_treinamento(db, *, treinamento_id: int, data: dict) -> None:
    db.execute(
        """
        UPDATE treinamentos
        SET tripulante_id = %s, equipamento_id = %s, tipo_treinamento_id = %s,
            data_realizacao = %s, data_vencimento = %s, observacao = %s
        WHERE id = %s
        """,
        (
            data["tripulante_id"],
            data["equipamento_id"],
            data["tipo_treinamento_id"],
            data["data_realizacao"],
            data["data_vencimento"],
            data["observacao"],
            treinamento_id,
        ),
    )


def fetch_treinamento_delete_target(db, *, treinamento_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT t.id, t.tripulante_id, c.nome AS tripulante_nome
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        WHERE t.id = %s
        """,
        (treinamento_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_treinamento_notifications(db, *, treinamento_id: int) -> None:
    db.execute("DELETE FROM notificacoes_treinamento WHERE treinamento_id = %s", (treinamento_id,))


def delete_treinamento(db, *, treinamento_id: int) -> None:
    db.execute("DELETE FROM treinamentos WHERE id = %s", (treinamento_id,))


def create_treinamento_attachment_record(db, *, treinamento_id: int, parsed: dict, enviado_por: int) -> int:
    row = db.execute(
        """
        INSERT INTO treinamento_anexos_pdf
        (
            treinamento_id, nome_original, nome_interno, mime_type, tamanho_bytes,
            storage_ref, arquivo_pdf, arquivo_hash, status, enviado_por
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ativo', %s)
        RETURNING id
        """,
        (
            treinamento_id,
            parsed["nome_original"],
            parsed["nome_interno"],
            parsed["mime_type"],
            parsed["tamanho_bytes"],
            parsed["storage_ref"],
            parsed["arquivo_pdf"],
            parsed["arquivo_hash"],
            enviado_por,
        ),
    ).fetchone()
    return int(row["id"])


def fetch_treinamento_attachment_row(db, *, treinamento_id: int, anexo_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT
            id,
            treinamento_id,
            nome_original,
            nome_interno,
            mime_type,
            storage_ref,
            arquivo_pdf,
            tamanho_bytes,
            arquivo_hash,
            status,
            enviado_por,
            enviado_em
        FROM treinamento_anexos_pdf
        WHERE id = %s AND treinamento_id = %s
        """,
        (anexo_id, treinamento_id),
    ).fetchone()
    return dict(row) if row else None


def delete_treinamento_attachment_record(db, *, treinamento_id: int, anexo_id: int) -> None:
    db.execute(
        "DELETE FROM treinamento_anexos_pdf WHERE id = %s AND treinamento_id = %s",
        (anexo_id, treinamento_id),
    )


def delete_treinamento_attachments(db, *, treinamento_id: int) -> None:
    db.execute("DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = %s", (treinamento_id,))
