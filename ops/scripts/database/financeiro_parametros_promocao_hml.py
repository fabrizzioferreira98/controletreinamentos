from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

from backend.src.controle_treinamentos.application.financeiro_governanca_parametros import (
    GOV_CLASS_DEPRECATED,
    GOV_CLASS_HML_RELEASE_CANDIDATE,
    GOV_CLASS_LEGACY,
    GOV_CLASS_PRODUCTION_APPROVED,
    GOV_CLASS_QA_SMOKE,
    aplicar_plano_promocao_classificacao,
    classificar_parametros,
    construir_plano_promocao_hml_release_candidate,
    contar_elegiveis_fechamento_real,
    detectar_divergencias_ativas,
    detectar_sobreposicoes_ativas,
    validar_matriz_canonica_completa,
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


def _count_by_class(classified: list[dict]) -> dict[str, int]:
    classes = [
        GOV_CLASS_QA_SMOKE,
        GOV_CLASS_HML_RELEASE_CANDIDATE,
        GOV_CLASS_PRODUCTION_APPROVED,
        GOV_CLASS_LEGACY,
        GOV_CLASS_DEPRECATED,
        "unclassified",
    ]
    result = {key: 0 for key in classes}
    for row in classified:
        cls = row.get("governance_class") or "unclassified"
        result[cls] = result.get(cls, 0) + 1
    return result


def _summary(rows: list[dict], used_ids: list[int], classified: list[dict], plan: list[dict]) -> dict:
    class_counts = _count_by_class(classified)
    canonical_active_ids = sorted(int(row["id"]) for row in classified if "canonico_ativo" in row.get("tags", []))

    return {
        "total": len(rows),
        "active_total": sum(1 for row in rows if str(row.get("status") or "").strip().lower() == "ativo"),
        "inactive_total": sum(1 for row in rows if str(row.get("status") or "").strip().lower() != "ativo"),
        "used_parameter_ids": used_ids,
        "canonical_active_ids": canonical_active_ids,
        "canonical_active_count": len(canonical_active_ids),
        "eligible_for_real_closure_hml": contar_elegiveis_fechamento_real(rows, environment="hml"),
        "eligible_for_real_closure_production": contar_elegiveis_fechamento_real(rows, environment="production"),
        "count_active_legacy_brl": sum(
            1
            for row in classified
            if "legado_brl" in row.get("tags", []) and str(row.get("status") or "").strip().lower() == "ativo"
        ),
        "count_overlap_semantic": len(detectar_sobreposicoes_ativas(rows, include_unit=False)),
        "count_divergent_semantic": len(detectar_divergencias_ativas(rows, include_unit=False)),
        "classification_counts": class_counts,
        "plan_count": len(plan),
        "plan_parameter_ids": [int(item["parameter_id"]) for item in plan],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Promocao controlada de classificacao de parametros financeiros em HML.")
    parser.add_argument(
        "--env-file",
        default="archive/temp-backups/release-parity-20260422-150732/env/hml.env",
        help="Arquivo com DATABASE_URL do HML.",
    )
    parser.add_argument(
        "--output-dir",
        default="ops/artifacts/financeiro-hml-governance-promotion",
        help="Diretorio dos artefatos before/after.",
    )
    parser.add_argument("--apply", action="store_true", help="Aplica promocao de classificacao.")
    parser.add_argument("--actor-user-id", type=int, default=1, help="Usuario para trilha em auditoria_eventos.")
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

    rows_before = _read_rows(cur)
    used_before = _read_used_ids(cur)
    classified_before = classificar_parametros(rows_before, used_parameter_ids=set(used_before))
    matrix_before = validar_matriz_canonica_completa(rows_before)
    plan = construir_plano_promocao_hml_release_candidate(rows_before)
    summary_before = _summary(rows_before, used_before, classified_before, plan)

    preview_file = output_dir / f"hml-governance-promotion-preview-{stamp}.json"
    preview_file.write_text(
        json.dumps(
            {
                "database": {"name": meta["db"], "user": meta["user"]},
                "matrix_validation": matrix_before,
                "summary_before": summary_before,
                "plan": plan,
                "rows_before": classified_before,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"PREVIEW_FILE={preview_file}")
    print(f"SUMMARY_BEFORE={json.dumps(summary_before, ensure_ascii=False)}")

    if not args.apply:
        conn.rollback()
        conn.close()
        return 0

    wrapper = DbWrapper(conn)
    applied = aplicar_plano_promocao_classificacao(
        wrapper,
        plano=plan,
        actor_user_id=int(args.actor_user_id),
        now_iso=datetime.utcnow().replace(microsecond=0).isoformat(),
        audit_observacao="governanca_hml_parametros_promocao_release_candidate",
    )
    wrapper.commit()

    cur_after = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows_after = _read_rows(cur_after)
    used_after = _read_used_ids(cur_after)
    classified_after = classificar_parametros(rows_after, used_parameter_ids=set(used_after))
    matrix_after = validar_matriz_canonica_completa(rows_after)
    summary_after = _summary(rows_after, used_after, classified_after, plan=[])

    apply_file = output_dir / f"hml-governance-promotion-apply-{stamp}.json"
    apply_file.write_text(
        json.dumps(
            {
                "database": {"name": meta["db"], "user": meta["user"]},
                "matrix_validation_before": matrix_before,
                "matrix_validation_after": matrix_after,
                "applied_count": len(applied),
                "applied": applied,
                "summary_before": summary_before,
                "summary_after": summary_after,
                "rows_after": classified_after,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"APPLY_FILE={apply_file}")
    print(f"SUMMARY_AFTER={json.dumps(summary_after, ensure_ascii=False)}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
