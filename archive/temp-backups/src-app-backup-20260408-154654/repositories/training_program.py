from __future__ import annotations

from ..services import business_today, calculate_training_status


def _ctac_required(value: str | None) -> bool:
    return "conforme ctac" in str(value or "").strip().lower()


def _segment_order_sql() -> str:
    return """
        CASE st.modelo_segmento
            WHEN 'Gerais' THEN 1
            WHEN 'Específicos' THEN 2
            WHEN 'Especiais' THEN 3
            WHEN 'Solo e Voo' THEN 4
            ELSE 5
        END,
        st.nome_segmento
    """


def fetch_training_master_types(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            tt.id,
            tt.nome,
            tt.codigo,
            tt.descricao,
            tt.periodicidade_meses,
            tt.exige_equipamento,
            tt.ativo,
            COUNT(DISTINCT st.id) AS total_segmentos,
            COUNT(DISTINCT hv.id) AS total_horas_voo
        FROM tipos_treinamento tt
        LEFT JOIN segmentos_teoricos st ON st.tipo_treinamento_id = tt.id
        LEFT JOIN horas_voo_aeronave hv ON hv.tipo_treinamento_id = tt.id
        GROUP BY tt.id
        ORDER BY tt.nome
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_master_type_detail(db, *, tipo_treinamento_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT
            tt.id,
            tt.nome,
            tt.codigo,
            tt.descricao,
            tt.periodicidade_meses,
            tt.exige_equipamento,
            tt.ativo,
            COUNT(DISTINCT st.id) AS total_segmentos,
            COUNT(DISTINCT hv.id) AS total_horas_voo
        FROM tipos_treinamento tt
        LEFT JOIN segmentos_teoricos st ON st.tipo_treinamento_id = tt.id
        LEFT JOIN horas_voo_aeronave hv ON hv.tipo_treinamento_id = tt.id
        WHERE tt.id = %s
        GROUP BY tt.id
        """,
        (tipo_treinamento_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_training_master_segments(db, *, tipo_treinamento_id: int | None = None) -> list[dict]:
    params: list = []
    where = ""
    if tipo_treinamento_id is not None:
        where = "WHERE st.tipo_treinamento_id = %s"
        params.append(int(tipo_treinamento_id))
    rows = db.execute(
        f"""
        SELECT
            st.id,
            st.tipo_treinamento_id,
            st.referencia_original_id,
            st.modelo_segmento,
            st.nome_segmento,
            st.carga_horaria,
            st.carga_teorica,
            st.carga_pratica,
            st.periodicidade_meses,
            st.observacao,
            st.ativo,
            tt.nome AS tipo_treinamento_nome,
            tt.codigo AS tipo_treinamento_codigo
        FROM segmentos_teoricos st
        JOIN tipos_treinamento tt ON tt.id = st.tipo_treinamento_id
        {where}
        ORDER BY tt.nome, {_segment_order_sql()}
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_master_segment_detail(db, *, segmento_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT
            st.*,
            tt.nome AS tipo_treinamento_nome,
            tt.codigo AS tipo_treinamento_codigo
        FROM segmentos_teoricos st
        JOIN tipos_treinamento tt ON tt.id = st.tipo_treinamento_id
        WHERE st.id = %s
        """,
        (segmento_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_training_master_hours(db, *, tipo_treinamento_id: int | None = None) -> list[dict]:
    params: list = []
    where = ""
    if tipo_treinamento_id is not None:
        where = "WHERE hv.tipo_treinamento_id = %s"
        params.append(int(tipo_treinamento_id))
    rows = db.execute(
        f"""
        SELECT
            hv.id,
            hv.tipo_treinamento_id,
            hv.referencia_original_id,
            hv.aeronave_modelo,
            hv.solo_horas,
            hv.voo_pic_sic_horas,
            hv.voo_crew_horas,
            hv.observacao,
            hv.ativo,
            tt.nome AS tipo_treinamento_nome,
            tt.codigo AS tipo_treinamento_codigo
        FROM horas_voo_aeronave hv
        JOIN tipos_treinamento tt ON tt.id = hv.tipo_treinamento_id
        {where}
        ORDER BY tt.nome, hv.aeronave_modelo
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_master_hour_detail(db, *, hora_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT
            hv.*,
            tt.nome AS tipo_treinamento_nome,
            tt.codigo AS tipo_treinamento_codigo
        FROM horas_voo_aeronave hv
        JOIN tipos_treinamento tt ON tt.id = hv.tipo_treinamento_id
        WHERE hv.id = %s
        """,
        (hora_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_training_program_tripulantes(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            c.id,
            c.nome,
            COALESCE(p.matricula, c.licenca_anac, '') AS matricula
        FROM tripulantes c
        LEFT JOIN pilotos p ON p.tripulante_id = c.id
        WHERE c.ativo = 1
        ORDER BY c.nome
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_program_active_types(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            id,
            nome,
            codigo,
            descricao,
            periodicidade_meses,
            exige_equipamento,
            ativo
        FROM tipos_treinamento
        WHERE ativo = 1
        ORDER BY nome
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_program_aircraft_models(db, *, tipo_treinamento_id: int | None = None) -> list[dict]:
    params: list = []
    where = "WHERE hv.ativo = 1"
    if tipo_treinamento_id is not None:
        where += " AND hv.tipo_treinamento_id = %s"
        params.append(int(tipo_treinamento_id))
    rows = db.execute(
        f"""
        SELECT
            hv.aeronave_modelo,
            COUNT(*) AS total_registros
        FROM horas_voo_aeronave hv
        {where}
        GROUP BY hv.aeronave_modelo
        ORDER BY hv.aeronave_modelo
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_program_segments_for_type(db, *, tipo_treinamento_id: int) -> list[dict]:
    rows = db.execute(
        f"""
        SELECT
            st.id,
            st.tipo_treinamento_id,
            st.referencia_original_id,
            st.modelo_segmento,
            st.nome_segmento,
            st.carga_horaria,
            st.carga_teorica,
            st.carga_pratica,
            st.periodicidade_meses,
            st.observacao,
            st.ativo
        FROM segmentos_teoricos st
        WHERE st.tipo_treinamento_id = %s
          AND st.ativo = 1
        ORDER BY {_segment_order_sql()}
        """,
        (tipo_treinamento_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_training_program_hour_for_type_and_model(
    db,
    *,
    tipo_treinamento_id: int,
    aeronave_modelo: str,
) -> dict | None:
    row = db.execute(
        """
        SELECT
            hv.*,
            tt.nome AS tipo_treinamento_nome
        FROM horas_voo_aeronave hv
        JOIN tipos_treinamento tt ON tt.id = hv.tipo_treinamento_id
        WHERE hv.tipo_treinamento_id = %s
          AND LOWER(hv.aeronave_modelo) = LOWER(%s)
          AND hv.ativo = 1
        ORDER BY hv.id
        LIMIT 1
        """,
        (tipo_treinamento_id, aeronave_modelo),
    ).fetchone()
    return dict(row) if row else None


def fetch_training_program_record_list(
    db,
    *,
    tripulante_id: int | None = None,
    tipo_treinamento_id: int | None = None,
    aeronave_modelo: str | None = None,
) -> list[dict]:
    clauses = ["t.segmento_teorico_id IS NOT NULL"]
    params: list = []
    if tripulante_id is not None:
        clauses.append("t.tripulante_id = %s")
        params.append(int(tripulante_id))
    if tipo_treinamento_id is not None:
        clauses.append("t.tipo_treinamento_id = %s")
        params.append(int(tipo_treinamento_id))
    if aeronave_modelo:
        clauses.append("LOWER(COALESCE(t.aeronave_modelo, '')) = LOWER(%s)")
        params.append(str(aeronave_modelo))
    where = f"WHERE {' AND '.join(clauses)}"
    rows = db.execute(
        f"""
        SELECT
            t.id,
            t.tripulante_id,
            t.equipamento_id,
            t.tipo_treinamento_id,
            t.segmento_teorico_id,
            t.aeronave_modelo,
            t.ctac_solo_horas,
            t.ctac_voo_pic_sic_horas,
            t.ctac_voo_crew_horas,
            t.data_realizacao,
            t.data_vencimento,
            t.observacao,
            c.nome AS tripulante_nome,
            COALESCE(p.matricula, c.licenca_anac, '') AS tripulante_matricula,
            tt.nome AS tipo_treinamento_nome,
            tt.codigo AS tipo_treinamento_codigo,
            st.nome_segmento,
            st.modelo_segmento,
            st.periodicidade_meses,
            COALESCE(hv.observacao, '') AS horas_voo_observacao,
            COUNT(a.id) AS total_anexos
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN pilotos p ON p.tripulante_id = c.id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        LEFT JOIN segmentos_teoricos st ON st.id = t.segmento_teorico_id
        LEFT JOIN horas_voo_aeronave hv
            ON hv.tipo_treinamento_id = t.tipo_treinamento_id
           AND LOWER(hv.aeronave_modelo) = LOWER(COALESCE(t.aeronave_modelo, ''))
           AND hv.ativo = 1
        LEFT JOIN treinamento_anexos_pdf a
            ON a.treinamento_id = t.id
           AND a.status = 'ativo'
        {where}
        GROUP BY
            t.id,
            c.id,
            p.matricula,
            tt.id,
            st.id,
            hv.id
        ORDER BY
            COALESCE(t.data_realizacao, t.data_vencimento) DESC NULLS LAST,
            c.nome,
            tt.nome,
            st.nome_segmento
        """,
        tuple(params),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["status_calculado"] = calculate_training_status(item.get("data_vencimento"), reference=business_today())
        item["ctac_required"] = _ctac_required(item.get("horas_voo_observacao"))
        items.append(item)
    return items


def fetch_training_program_record_detail(db, *, treinamento_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT
            t.id,
            t.tripulante_id,
            t.equipamento_id,
            t.tipo_treinamento_id,
            t.segmento_teorico_id,
            t.aeronave_modelo,
            t.ctac_solo_horas,
            t.ctac_voo_pic_sic_horas,
            t.ctac_voo_crew_horas,
            t.data_realizacao,
            t.data_vencimento,
            t.observacao,
            c.nome AS tripulante_nome,
            COALESCE(p.matricula, c.licenca_anac, '') AS tripulante_matricula,
            tt.nome AS tipo_treinamento_nome,
            tt.codigo AS tipo_treinamento_codigo,
            st.nome_segmento,
            st.modelo_segmento,
            st.periodicidade_meses,
            st.carga_horaria,
            st.carga_teorica,
            st.carga_pratica,
            COALESCE(hv.solo_horas, 0) AS solo_horas_referencia,
            COALESCE(hv.voo_pic_sic_horas, 0) AS voo_pic_sic_horas_referencia,
            COALESCE(hv.voo_crew_horas, 0) AS voo_crew_horas_referencia,
            COALESCE(hv.observacao, '') AS horas_voo_observacao
        FROM treinamentos t
        JOIN tripulantes c ON c.id = t.tripulante_id
        LEFT JOIN pilotos p ON p.tripulante_id = c.id
        JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        LEFT JOIN segmentos_teoricos st ON st.id = t.segmento_teorico_id
        LEFT JOIN horas_voo_aeronave hv
            ON hv.tipo_treinamento_id = t.tipo_treinamento_id
           AND LOWER(hv.aeronave_modelo) = LOWER(COALESCE(t.aeronave_modelo, ''))
           AND hv.ativo = 1
        WHERE t.id = %s
          AND t.segmento_teorico_id IS NOT NULL
        LIMIT 1
        """,
        (treinamento_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["status_calculado"] = calculate_training_status(item.get("data_vencimento"), reference=business_today())
    item["ctac_required"] = _ctac_required(item.get("horas_voo_observacao"))
    return item
