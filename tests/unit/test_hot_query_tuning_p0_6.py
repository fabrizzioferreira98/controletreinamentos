from __future__ import annotations

from datetime import date

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.contracts.tripulantes import serialize_tripulante_collection
from backend.src.controle_treinamentos.infra import mailer
from backend.src.controle_treinamentos.repositories.queries import fetch_training_page
from backend.src.controle_treinamentos.repositories.treinamentos import count_treinamentos
from backend.src.controle_treinamentos.repositories.tripulantes import fetch_tripulante_list_page


class _CaptureCursor:
    def __init__(self, *, row=None, rows=None):
        self._row = row or {}
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _CaptureDB:
    def __init__(self, *, row=None, rows=None):
        self.row = row or {}
        self.rows = rows or []
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _CaptureCursor(row=self.row, rows=self.rows)


def test_fetch_tripulante_list_page_uses_photo_hint_without_blob_resolution(monkeypatch):
    db = _CaptureDB(
        rows=[
            {
                "id": 7,
                "nome": "Lucas Silva",
                "cpf": "123",
                "licenca_anac": "456",
                "email": "lucas@local.test",
                "telefone": "11999999999",
                "base": "Sao Paulo",
                "status": "Ativo",
                "ativo": 1,
                "funcao_operacional": "comandante",
                "categoria_operacional": "A",
                "sdea_ativo": 1,
                "instrutor_ativo": 0,
                "checador_ativo": 0,
                "elegivel_adicional_excepcional": 1,
                "photo_source_hint": "base64",
                "possui_foto": True,
            }
        ]
    )

    rows = fetch_tripulante_list_page(db, nome="Lucas", limit=20, offset=0)
    query, params = db.calls[0]

    assert "AS photo_source_hint" in query
    assert "foto_mime_type" not in query
    assert params[-2:] == (20, 0)

    app = create_app()
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("list path should not read media blob")),
    )

    with app.test_request_context():
        payload = serialize_tripulante_collection(items=rows, page=1, per_page=20, total=1)

    assert payload["items"][0]["possui_foto"] is True
    assert payload["items"][0]["photo_source"] == "base64"
    assert payload["items"][0]["photo_compat_residual"] is True


def test_count_treinamentos_filters_by_training_ids_without_lookup_joins(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.treinamentos.business_today",
        lambda: date(2026, 4, 16),
    )
    db = _CaptureDB(row={"total": 3, "sem_informacao": 0, "vencido": 1, "a_vencer": 1, "regular": 1})

    payload = count_treinamentos(db, tripulante="7", equipamento="3", tipo="2", status="regular", periodo="30")
    query, params = db.calls[0]

    assert payload["total"] == 3
    assert "FROM treinamentos t" in query
    assert "JOIN tripulantes" not in query
    assert "LEFT JOIN equipamentos" not in query
    assert "JOIN tipos_treinamento" not in query
    assert "t.tripulante_id = %s" in query
    assert "t.equipamento_id = %s" in query
    assert "t.tipo_treinamento_id = %s" in query
    assert 7 in params
    assert 3 in params
    assert 2 in params
    assert date(2026, 5, 16) in params


def test_fetch_training_page_ranks_before_equipment_join(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.repositories.queries.business_today",
        lambda: date(2026, 4, 16),
    )
    db = _CaptureDB(
        rows=[
            {
                "id": 55,
                "tripulante_id": 7,
                "equipamento_id": None,
                "tipo_treinamento_id": 2,
                "segmento_teorico_id": 26,
                "aeronave_modelo": "King Air B200/200/C90A/C90GT",
                "ctac_solo_horas": None,
                "ctac_voo_pic_sic_horas": None,
                "ctac_voo_crew_horas": None,
                "data_realizacao": date(2026, 4, 1),
                "data_vencimento": date(2026, 10, 1),
                "tripulante_nome": "Lucas Silva",
                "equipamento_nome": None,
                "tipo_treinamento_nome": "CQ IFR",
                "status_calculado": "regular",
            }
        ]
    )

    rows = fetch_training_page(db, where_clause="WHERE t.tripulante_id = %s", params=(7,), limit=20, offset=0)
    query, params = db.calls[0]

    assert rows[0]["status_class"] == "status-green"
    assert "WITH ranked AS" in query
    assert "LEFT JOIN equipamentos e ON e.id = ranked.equipamento_id" in query
    assert "JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id" in query
    assert "t.segmento_teorico_id" in query
    assert "t.aeronave_modelo" in query
    assert rows[0]["segmento_teorico_id"] == 26
    assert rows[0]["aeronave_modelo"] == "King Air B200/200/C90A/C90GT"
    assert 7 in params
    assert params[-2:] == (20, 0)


def test_fetch_notification_training_rows_caps_lookahead_and_embeds_sent_state(monkeypatch):
    monkeypatch.setattr(mailer, "business_today", lambda: date(2026, 4, 16))
    monkeypatch.setenv("NOTIFICATION_LOOKAHEAD_DAYS", "180")
    db = _CaptureDB(rows=[])
    monkeypatch.setattr(mailer, "get_db", lambda: db)

    mailer.fetch_notification_training_rows(include_details=False)
    query, params = db.calls[0]

    assert "WITH eligible AS" in query
    assert "already_sent_today" in query
    assert "CAST(nt.enviado_em AS DATE) = %s" in query
    assert params[3] == date(2026, 7, 15)
    assert params[4] == date(2026, 4, 16)


def test_build_notification_blocks_pair_uses_inline_sent_state_without_extra_query(monkeypatch):
    monkeypatch.setattr(mailer, "business_today", lambda: date(2026, 4, 16))
    monkeypatch.setattr(
        mailer,
        "fetch_sent_notification_map",
        lambda _ids: (_ for _ in ()).throw(AssertionError("inline sent state should avoid extra query")),
    )

    rows = [
        {
            "treinamento_id": 1,
            "data_vencimento": "2026-04-20",
            "tripulante_nome": "Trip 1",
            "tripulante_email": "trip1@local.test",
            "equipamento_nome": "B200",
            "tipo_treinamento_nome": "CQ IFR",
            "gatilho": "30",
            "already_sent_today": True,
        },
        {
            "treinamento_id": 2,
            "data_vencimento": "2026-04-21",
            "tripulante_nome": "Trip 2",
            "tripulante_email": "trip2@local.test",
            "equipamento_nome": "B200",
            "tipo_treinamento_nome": "CQ IFR",
            "gatilho": "30",
            "already_sent_today": False,
        },
    ]

    blocks, blocks_all = mailer.build_notification_blocks_pair(rows)

    assert len(blocks_all["em_30_dias"]) == 2
    assert [item["treinamento_id"] for item in blocks["em_30_dias"]] == [2]
