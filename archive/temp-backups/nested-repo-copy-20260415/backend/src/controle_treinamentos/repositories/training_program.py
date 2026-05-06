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


def fetch_training_master_type_for_write(
    db,
    *,
    tipo_treinamento_id: int,
    include_inactive: bool = False,
) -> dict | None:
    params = [int(tipo_treinamento_id)]
    where = "WHERE id = %s"
    if not include_inactive:
        where += " AND ativo = 1"
    row = db.execute(
        f"""
        SELECT id, nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo
        FROM tipos_treinamento
        {where}
        LIMIT 1
        """,
        tuple(params),
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


def fetch_training_master_segment_for_write(
    db,
    *,
    segmento_id: int,
    tipo_treinamento_id: int | None = None,
    include_inactive: bool = False,
) -> dict | None:
    clauses = ["st.id = %s"]
    params: list = [int(segmento_id)]
    if tipo_treinamento_id is not None:
        clauses.append("st.tipo_treinamento_id = %s")
        params.append(int(tipo_treinamento_id))
    if not include_inactive:
        clauses.append("st.ativo = 1")
    row = db.execute(
        f"""
        SELECT st.*
        FROM segmentos_teoricos st
        WHERE {' AND '.join(clauses)}
        LIMIT 1
        """,
        tuple(params),
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


def fetch_training_master_hour_for_write(
    db,
    *,
    hora_id: int,
    include_inactive: bool = False,
) -> dict | None:
    clauses = ["hv.id = %s"]
    if not include_inactive:
        clauses.append("hv.ativo = 1")
    row = db.execute(
        f"""
        SELECT hv.*
        FROM horas_voo_aeronave hv
        WHERE {' AND '.join(clauses)}
        LIMIT 1
        """,
        (int(hora_id),),
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


def fetch_training_program_tripulante_detail(db, *, tripulante_id: int) -> dict | None:
    row = db.execute(
        """
        SELECT c.id, c.nome, COALESCE(p.matricula, c.licenca_anac, '') AS matricula
        FROM tripulantes c
        LEFT JOIN pilotos p ON p.tripulante_id = c.id
        WHERE c.id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    return dict(row) if row else None


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


def sync_training_master_type_periodicidade(db, *, tipo_treinamento_id: int) -> None:
    row = db.execute(
        """
        SELECT COALESCE(MAX(periodicidade_meses), 0) AS periodicidade_meses
        FROM segmentos_teoricos
        WHERE tipo_treinamento_id = %s
          AND ativo = 1
        """,
        (tipo_treinamento_id,),
    ).fetchone()
    periodicidade = int(row["periodicidade_meses"] or 0) if row else 0
    db.execute(
        "UPDATE tipos_treinamento SET periodicidade_meses = %s WHERE id = %s",
        (periodicidade, tipo_treinamento_id),
    )


def create_training_master_type(db, *, data: dict) -> int:
    row = db.execute(
        """
        INSERT INTO tipos_treinamento (nome, codigo, descricao, periodicidade_meses, exige_equipamento, ativo)
        VALUES (%s, %s, %s, 0, %s, %s)
        RETURNING id
        """,
        (
            data["nome"],
            data["codigo"],
            data["descricao"],
            data["exige_equipamento"],
            data["ativo"],
        ),
    ).fetchone()
    return int(row["id"])


def update_training_master_type(db, *, tipo_treinamento_id: int, data: dict) -> None:
    db.execute(
        """
        UPDATE tipos_treinamento
        SET nome = %s,
            codigo = %s,
            descricao = %s,
            exige_equipamento = %s,
            ativo = %s
        WHERE id = %s
        """,
        (
            data["nome"],
            data["codigo"],
            data["descricao"],
            data["exige_equipamento"],
            data["ativo"],
            tipo_treinamento_id,
        ),
    )


def training_master_type_has_records(db, *, tipo_treinamento_id: int) -> bool:
    row = db.execute(
        "SELECT id FROM treinamentos WHERE tipo_treinamento_id = %s LIMIT 1",
        (tipo_treinamento_id,),
    ).fetchone()
    return bool(row)


def delete_training_master_type_cascade(db, *, tipo_treinamento_id: int) -> None:
    db.execute("DELETE FROM horas_voo_aeronave WHERE tipo_treinamento_id = %s", (tipo_treinamento_id,))
    db.execute("DELETE FROM segmentos_teoricos WHERE tipo_treinamento_id = %s", (tipo_treinamento_id,))
    db.execute("DELETE FROM tipos_treinamento WHERE id = %s", (tipo_treinamento_id,))


def create_training_master_segment(db, *, data: dict) -> int:
    row = db.execute(
        """
        INSERT INTO segmentos_teoricos
        (
            tipo_treinamento_id,
            modelo_segmento,
            nome_segmento,
            carga_horaria,
            carga_teorica,
            carga_pratica,
            periodicidade_meses,
            observacao,
            ativo
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            data["tipo_treinamento_id"],
            data["modelo_segmento"],
            data["nome_segmento"],
            data["carga_horaria"],
            data["carga_teorica"],
            data["carga_pratica"],
            data["periodicidade_meses"],
            data["observacao"],
            data["ativo"],
        ),
    ).fetchone()
    return int(row["id"])


def update_training_master_segment(db, *, segmento_id: int, data: dict) -> None:
    db.execute(
        """
        UPDATE segmentos_teoricos
        SET tipo_treinamento_id = %s,
            modelo_segmento = %s,
            nome_segmento = %s,
            carga_horaria = %s,
            carga_teorica = %s,
            carga_pratica = %s,
            periodicidade_meses = %s,
            observacao = %s,
            ativo = %s
        WHERE id = %s
        """,
        (
            data["tipo_treinamento_id"],
            data["modelo_segmento"],
            data["nome_segmento"],
            data["carga_horaria"],
            data["carga_teorica"],
            data["carga_pratica"],
            data["periodicidade_meses"],
            data["observacao"],
            data["ativo"],
            segmento_id,
        ),
    )


def training_master_segment_has_records(db, *, segmento_id: int) -> bool:
    row = db.execute(
        "SELECT id FROM treinamentos WHERE segmento_teorico_id = %s LIMIT 1",
        (segmento_id,),
    ).fetchone()
    return bool(row)


def delete_training_master_segment(db, *, segmento_id: int) -> None:
    db.execute("DELETE FROM segmentos_teoricos WHERE id = %s", (segmento_id,))


def create_training_master_hour(db, *, data: dict) -> int:
    row = db.execute(
        """
        INSERT INTO horas_voo_aeronave
        (
            tipo_treinamento_id,
            aeronave_modelo,
            solo_horas,
            voo_pic_sic_horas,
            voo_crew_horas,
            observacao,
            ativo
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            data["tipo_treinamento_id"],
            data["aeronave_modelo"],
            data["solo_horas"],
            data["voo_pic_sic_horas"],
            data["voo_crew_horas"],
            data["observacao"],
            data["ativo"],
        ),
    ).fetchone()
    return int(row["id"])


def update_training_master_hour(db, *, hora_id: int, data: dict) -> None:
    db.execute(
        """
        UPDATE horas_voo_aeronave
        SET tipo_treinamento_id = %s,
            aeronave_modelo = %s,
            solo_horas = %s,
            voo_pic_sic_horas = %s,
            voo_crew_horas = %s,
            observacao = %s,
            ativo = %s
        WHERE id = %s
        """,
        (
            data["tipo_treinamento_id"],
            data["aeronave_modelo"],
            data["solo_horas"],
            data["voo_pic_sic_horas"],
            data["voo_crew_horas"],
            data["observacao"],
            data["ativo"],
            hora_id,
        ),
    )


def delete_training_master_hour(db, *, hora_id: int) -> None:
    db.execute("DELETE FROM horas_voo_aeronave WHERE id = %s", (hora_id,))


def create_training_program_record(db, *, data: dict) -> int:
    row = db.execute(
        """
        INSERT INTO treinamentos
        (
            tripulante_id,
            equipamento_id,
            tipo_treinamento_id,
            segmento_teorico_id,
            aeronave_modelo,
            ctac_solo_horas,
            ctac_voo_pic_sic_horas,
            ctac_voo_crew_horas,
            data_realizacao,
            data_vencimento,
            observacao
        )
        VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            data["tripulante_id"],
            data["tipo_treinamento_id"],
            data["segmento_teorico_id"],
            data["aeronave_modelo"],
            data["ctac_solo_horas"],
            data["ctac_voo_pic_sic_horas"],
            data["ctac_voo_crew_horas"],
            data["data_realizacao"],
            data["data_vencimento"],
            data["observacao"],
        ),
    ).fetchone()
    return int(row["id"])


def update_training_program_record(db, *, treinamento_id: int, data: dict) -> None:
    db.execute(
        """
        UPDATE treinamentos
        SET tripulante_id = %s,
            tipo_treinamento_id = %s,
            segmento_teorico_id = %s,
            aeronave_modelo = %s,
            ctac_solo_horas = %s,
            ctac_voo_pic_sic_horas = %s,
            ctac_voo_crew_horas = %s,
            data_realizacao = %s,
            data_vencimento = %s,
            observacao = %s
        WHERE id = %s
        """,
        (
            data["tripulante_id"],
            data["tipo_treinamento_id"],
            data["segmento_teorico_id"],
            data["aeronave_modelo"],
            data["ctac_solo_horas"],
            data["ctac_voo_pic_sic_horas"],
            data["ctac_voo_crew_horas"],
            data["data_realizacao"],
            data["data_vencimento"],
            data["observacao"],
            treinamento_id,
        ),
    )


def delete_training_program_record_attachments(db, *, treinamento_id: int) -> None:
    db.execute("DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = %s", (treinamento_id,))


def delete_training_program_record_notifications(db, *, treinamento_id: int) -> None:
    db.execute("DELETE FROM notificacoes_treinamento WHERE treinamento_id = %s", (treinamento_id,))


def delete_training_program_record(db, *, treinamento_id: int) -> None:
    db.execute("DELETE FROM treinamentos WHERE id = %s", (treinamento_id,))
