from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

from backend.src.controle_treinamentos.application.financeiro_governanca_parametros import (
    aplicar_plano_saneamento,
    classificar_parametros,
    construir_plano_saneamento_seguro,
    detectar_divergencias_ativas,
    detectar_sobreposicoes_ativas,
)


@dataclass
class DbWrapper:
    conn: any

    def execute(self, query, params=None):
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        return cursor

    def commit(self):
        self.conn.commit()


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _read_rows(cur) -> list[dict]:
    cur.execute(
        """
        SELECT id, org_id, tipo, funcao, categoria, valor::text AS valor, unidade,
               vigencia_inicio::text AS vigencia_inicio, vigencia_fim::text AS vigencia_fim,
               status, motivo, created_at::text AS created_at, updated_at::text AS updated_at
        FROM financeiro_parametros
        ORDER BY id
        """
    )
    return cur.fetchall()


def _read_used_ids(cur) -> list[int]:
    cur.execute(
        """
        WITH used_hourly AS (
          SELECT DISTINCT (e->>'parameter_id')::int AS parameter_id
          FROM financeiro_calculos_horarios h
          CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(h.parametros_usados)='array' THEN h.parametros_usados ELSE '[]'::jsonb END
          ) AS e
          WHERE e ? 'parameter_id' AND (e->>'parameter_id') ~ '^[0-9]+$'
        ), used_productivity AS (
          SELECT DISTINCT (e->>'parameter_id')::int AS parameter_id
          FROM financeiro_calculos_produtividade p
          CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(p.parametros_usados)='array' THEN p.parametros_usados ELSE '[]'::jsonb END
          ) AS e
          WHERE e ? 'parameter_id' AND (e->>'parameter_id') ~ '^[0-9]+$'
        )
        SELECT DISTINCT parameter_id
        FROM (
          SELECT parameter_id FROM used_hourly
          UNION ALL
          SELECT parameter_id FROM used_productivity
        ) u
        ORDER BY parameter_id
        """
    )
    return [row["parameter_id"] for row in cur.fetchall()]


def _summary(rows: list[dict], used_ids: list[int], classified: list[dict], plan: list[dict]) -> dict:
    strict_overlap = detectar_sobreposicoes_ativas(rows, include_unit=True)
    strict_div = detectar_divergencias_ativas(rows, include_unit=True)
    semantic_overlap = detectar_sobreposicoes_ativas(rows, include_unit=False)
    semantic_div = detectar_divergencias_ativas(rows, include_unit=False)
    return {
        "total": len(rows),
        "active_total": sum(1 for row in rows if str(row.get("status") or "").strip().lower() == "ativo"),
        "inactive_total": sum(1 for row in rows if str(row.get("status") or "").strip().lower() != "ativo"),
        "used_parameter_ids": used_ids,
        "count_legacy_brl": sum(1 for row in classified if "legado_brl" in row.get("tags", [])),
        "count_active_legacy_brl": sum(
            1
            for row in classified
            if "legado_brl" in row.get("tags", []) and str(row.get("status") or "").strip().lower() == "ativo"
        ),
        "count_qa_smoke": sum(1 for row in classified if "qa_smoke" in row.get("tags", [])),
        "count_not_used": sum(1 for row in classified if "nao_usado" in row.get("tags", [])),
        "count_overlap_strict": len(strict_overlap),
        "count_divergent_strict": len(strict_div),
        "count_overlap_semantic": len(semantic_overlap),
        "count_divergent_semantic": len(semantic_div),
        "count_canonical_active": sum(1 for row in classified if "canonico_ativo" in row.get("tags", [])),
        "plan_count": len(plan),
        "plan_parameter_ids": [int(item["parameter_id"]) for item in plan],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Governanca de parametros financeiros para HML (ct_hml).")
    parser.add_argument(
        "--env-file",
        default="archive/temp-backups/release-parity-20260422-150732/env/hml.env",
        help="Arquivo de ambiente com DATABASE_URL do HML.",
    )
    parser.add_argument(
        "--output-dir",
        default="ops/artifacts/financeiro-hml-governance",
        help="Diretorio dos artefatos before/after.",
    )
    parser.add_argument("--apply", action="store_true", help="Aplica saneamento (sem --apply executa apenas preview).")
    parser.add_argument(
        "--actor-user-id",
        type=int,
        default=1,
        help="Usuario para trilha de auditoria (auditoria_eventos.realizado_por).",
    )
    args = parser.parse_args()

    env_file = Path(args.env_file)
    if not env_file.exists():
        raise SystemExit(f"Env file not found: {env_file}")
    env = _load_env_file(env_file)
    database_url = (env.get("DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL missing in env file.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT current_database() AS db, current_user AS user")
    meta = cur.fetchone()
    if meta["db"] != "ct_hml":
        conn.rollback()
        conn.close()
        raise SystemExit(f"Refusing to run outside ct_hml. current_database={meta['db']}")

    rows = _read_rows(cur)
    used_ids = _read_used_ids(cur)
    classified = classificar_parametros(rows, used_parameter_ids=set(used_ids))
    plan = construir_plano_saneamento_seguro(rows, reference_date=date.today())
    summary = _summary(rows, used_ids, classified, plan)

    preview_file = output_dir / f"hml-governance-preview-{stamp}.json"
    preview_file.write_text(
        json.dumps(
            {
                "database": {"name": meta["db"], "user": meta["user"]},
                "summary": summary,
                "plan": plan,
                "rows": classified,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"PREVIEW_FILE={preview_file}")
    print(f"SUMMARY={json.dumps(summary, ensure_ascii=False)}")

    if not args.apply:
        conn.rollback()
        conn.close()
        return 0

    before_rows = [row for row in rows if int(row["id"]) in summary["plan_parameter_ids"]]
    wrapper = DbWrapper(conn)
    applied = aplicar_plano_saneamento(
        wrapper,
        plano=plan,
        actor_user_id=int(args.actor_user_id),
        now_iso=datetime.utcnow().replace(microsecond=0).isoformat(),
    )
    wrapper.commit()

    cur_after = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    after_rows = _read_rows(cur_after)
    used_after = _read_used_ids(cur_after)
    classified_after = classificar_parametros(after_rows, used_parameter_ids=set(used_after))
    summary_after = _summary(after_rows, used_after, classified_after, plan=[])

    apply_file = output_dir / f"hml-governance-apply-{stamp}.json"
    apply_file.write_text(
        json.dumps(
            {
                "database": {"name": meta["db"], "user": meta["user"]},
                "applied_count": len(applied),
                "applied": applied,
                "before": before_rows,
                "after": [row for row in after_rows if int(row["id"]) in summary["plan_parameter_ids"]],
                "summary_after": summary_after,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"APPLY_FILE={apply_file}")
    print(f"APPLIED_COUNT={len(applied)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
