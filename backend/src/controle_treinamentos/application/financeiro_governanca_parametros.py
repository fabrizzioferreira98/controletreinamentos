from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..core.domain_errors import DomainValidationError
from .financeiro_categorias import CANONICAL_CATEGORY_A, CANONICAL_CATEGORY_B, CANONICAL_CATEGORY_TURBOHELICE_PALMAS

EXPECTED_UNITS = {
    "duracao_hora_noturna_minutos": "minutos",
    "periodo_diurno_inicio": "minutos_do_dia",
    "periodo_diurno_fim": "minutos_do_dia",
    "adicional_noturno": "valor",
    "domingo_feriado_diurno": "valor",
    "domingo_feriado_noturno": "valor",
    "icao_sdea": "valor",
    "instrutor": "valor",
    "checador": "valor",
    "missao_categoria_a": "valor",
    "missao_categoria_b": "valor",
    "cobertura_base": "valor",
    "pernoite_comum_sem_cobertura": "valor",
    "garantia_minima": "valor",
    "excecao_palmas_turbohelice": "valor",
}

GOV_CLASS_QA_SMOKE = "qa-smoke"
GOV_CLASS_HML_RELEASE_CANDIDATE = "hml-release-candidate"
GOV_CLASS_PRODUCTION_APPROVED = "production-approved"
GOV_CLASS_LEGACY = "legacy"
GOV_CLASS_DEPRECATED = "deprecated"

GOVERNANCE_CLASSES = (
    GOV_CLASS_QA_SMOKE,
    GOV_CLASS_HML_RELEASE_CANDIDATE,
    GOV_CLASS_PRODUCTION_APPROVED,
    GOV_CLASS_LEGACY,
    GOV_CLASS_DEPRECATED,
)

ELIGIBLE_CLASSES_BY_ENV = {
    "hml": {GOV_CLASS_HML_RELEASE_CANDIDATE, GOV_CLASS_PRODUCTION_APPROVED},
    "production": {GOV_CLASS_PRODUCTION_APPROVED},
}

CANONICAL_MATRIX = (
    {"tipo": "duracao_hora_noturna_minutos", "funcao": None, "categoria": None, "valor": "52.5", "unidade": "minutos"},
    {"tipo": "periodo_diurno_inicio", "funcao": None, "categoria": None, "valor": "360", "unidade": "minutos_do_dia"},
    {"tipo": "periodo_diurno_fim", "funcao": None, "categoria": None, "valor": "1080", "unidade": "minutos_do_dia"},
    {"tipo": "adicional_noturno", "funcao": "comandante", "categoria": None, "valor": "92.18", "unidade": "valor"},
    {"tipo": "domingo_feriado_diurno", "funcao": "comandante", "categoria": None, "valor": "92.18", "unidade": "valor"},
    {"tipo": "domingo_feriado_noturno", "funcao": "comandante", "categoria": None, "valor": "184.36", "unidade": "valor"},
    {"tipo": "adicional_noturno", "funcao": "copiloto", "categoria": None, "valor": "46.18", "unidade": "valor"},
    {"tipo": "domingo_feriado_diurno", "funcao": "copiloto", "categoria": None, "valor": "46.18", "unidade": "valor"},
    {"tipo": "domingo_feriado_noturno", "funcao": "copiloto", "categoria": None, "valor": "92.36", "unidade": "valor"},
    {"tipo": "icao_sdea", "funcao": "comandante", "categoria": None, "valor": "300.00", "unidade": "valor"},
    {"tipo": "icao_sdea", "funcao": "copiloto", "categoria": None, "valor": "150.00", "unidade": "valor"},
    {"tipo": "instrutor", "funcao": None, "categoria": None, "valor": "300.00", "unidade": "valor"},
    {"tipo": "checador", "funcao": None, "categoria": None, "valor": "300.00", "unidade": "valor"},
    {
        "tipo": "missao_categoria_a",
        "funcao": "comandante",
        "categoria": CANONICAL_CATEGORY_A,
        "valor": "300.00",
        "unidade": "valor",
    },
    {
        "tipo": "missao_categoria_a",
        "funcao": "copiloto",
        "categoria": CANONICAL_CATEGORY_A,
        "valor": "150.00",
        "unidade": "valor",
    },
    {
        "tipo": "missao_categoria_b",
        "funcao": "comandante",
        "categoria": CANONICAL_CATEGORY_B,
        "valor": "600.00",
        "unidade": "valor",
    },
    {
        "tipo": "missao_categoria_b",
        "funcao": "copiloto",
        "categoria": CANONICAL_CATEGORY_B,
        "valor": "300.00",
        "unidade": "valor",
    },
    {"tipo": "cobertura_base", "funcao": "comandante", "categoria": None, "valor": "200.00", "unidade": "valor"},
    {"tipo": "cobertura_base", "funcao": "copiloto", "categoria": None, "valor": "100.00", "unidade": "valor"},
    {
        "tipo": "garantia_minima",
        "funcao": "comandante",
        "categoria": CANONICAL_CATEGORY_A,
        "valor": "3000.00",
        "unidade": "valor",
    },
    {
        "tipo": "garantia_minima",
        "funcao": "copiloto",
        "categoria": CANONICAL_CATEGORY_A,
        "valor": "1500.00",
        "unidade": "valor",
    },
    {
        "tipo": "garantia_minima",
        "funcao": "comandante",
        "categoria": CANONICAL_CATEGORY_B,
        "valor": "6000.00",
        "unidade": "valor",
    },
    {
        "tipo": "garantia_minima",
        "funcao": "copiloto",
        "categoria": CANONICAL_CATEGORY_B,
        "valor": "3000.00",
        "unidade": "valor",
    },
    {
        "tipo": "excecao_palmas_turbohelice",
        "funcao": "comandante",
        "categoria": CANONICAL_CATEGORY_TURBOHELICE_PALMAS,
        "valor": "5000.00",
        "unidade": "valor",
    },
    {
        "tipo": "excecao_palmas_turbohelice",
        "funcao": "copiloto",
        "categoria": CANONICAL_CATEGORY_TURBOHELICE_PALMAS,
        "valor": "2500.00",
        "unidade": "valor",
    },
)

_QA_SMOKE_RE = re.compile(r"(qa|smoke|teste|test|dummy|hml)", re.IGNORECASE)
_GOV_CLASS_RE = re.compile(r"(?:^|;)\s*GOV_CLASS\s*=\s*([a-z0-9-]+)\s*(?=;|$)", re.IGNORECASE)
_GOV_CLASS_ANY_RE = re.compile(r"(?:^|;)\s*GOV_CLASS\s*=\s*[a-z0-9-]+\s*(?=;|$)", re.IGNORECASE)


class GovernancaParametrosErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "finance_parameter_governance_error"):
        super().__init__(message, status=409, code=code)


class MatrizCanonicaInvalidaErro(DomainValidationError):
    def __init__(self, message: str, *, code: str = "finance_parameter_canonical_matrix_invalid"):
        super().__init__(message, status=409, code=code)


def _clean_text(value) -> str:
    return str(value or "").strip()


def _optional_text(value) -> str | None:
    text = _clean_text(value)
    return text or None


def _to_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _to_decimal(value) -> Decimal:
    return Decimal(str(value or "0").replace(",", "."))


def _to_decimal_text(value) -> str:
    return format(_to_decimal(value), "f")


def _is_active(row: dict[str, Any]) -> bool:
    return _clean_text(row.get("status")).lower() == "ativo"


def _is_brl(row: dict[str, Any]) -> bool:
    return _clean_text(row.get("unidade")).upper() == "BRL"


def _is_qa_smoke(row: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            _clean_text(row.get("motivo")),
            _clean_text(row.get("tipo")),
            _clean_text(row.get("categoria")),
            _clean_text(row.get("funcao")),
        ]
    )
    return bool(_QA_SMOKE_RE.search(haystack))


def _vigencia_valida(row: dict[str, Any]) -> bool:
    start = _to_date(row.get("vigencia_inicio"))
    end = _to_date(row.get("vigencia_fim"))
    if not start:
        return False
    if end and end < start:
        return False
    return True


def _norm_env(environment: str) -> str:
    raw = _clean_text(environment).lower()
    if raw in {"hml", "homolog", "homologacao"}:
        return "hml"
    if raw in {"prod", "production", "producao", "produção"}:
        return "production"
    raise GovernancaParametrosErro(
        f"Ambiente de elegibilidade invalido: {environment}.",
        code="finance_parameter_environment_invalid",
    )


def extrair_classe_governanca(row_or_reason: dict[str, Any] | str | None) -> str | None:
    reason = row_or_reason if isinstance(row_or_reason, str) else _clean_text((row_or_reason or {}).get("motivo"))
    if not reason:
        return None
    match = _GOV_CLASS_RE.search(reason)
    if not match:
        return None
    candidate = _clean_text(match.group(1)).lower()
    return candidate if candidate in GOVERNANCE_CLASSES else None


def atualizar_motivo_com_classe_governanca(motivo: str | None, classe: str) -> str:
    desired = _clean_text(classe).lower()
    if desired not in GOVERNANCE_CLASSES:
        raise GovernancaParametrosErro(
            f"Classe de governanca invalida: {classe}.",
            code="finance_parameter_governance_class_invalid",
        )
    current = _clean_text(motivo)
    without_marker = _GOV_CLASS_ANY_RE.sub("", current)
    parts = [part.strip() for part in without_marker.split(";") if part.strip()]
    parts.append(f"GOV_CLASS={desired}")
    return "; ".join(parts)


def classificacao_governanca_parametro(row: dict[str, Any]) -> str | None:
    explicit = extrair_classe_governanca(row)
    if explicit:
        return explicit
    if _is_brl(row):
        return GOV_CLASS_LEGACY
    if _is_qa_smoke(row):
        return GOV_CLASS_QA_SMOKE
    if not _is_active(row):
        return GOV_CLASS_DEPRECATED
    return None


def _key(row: dict[str, Any], *, include_unit: bool) -> tuple[str | None, ...]:
    base = (
        _optional_text(row.get("org_id")),
        _optional_text(row.get("tipo")),
        _optional_text(row.get("funcao")),
        _optional_text(row.get("categoria")),
    )
    if include_unit:
        return (*base, _optional_text(row.get("unidade")))
    return base


def _canonical_spec_key(spec: dict[str, Any]) -> tuple[str | None, ...]:
    return (
        _optional_text(spec.get("tipo")),
        _optional_text(spec.get("funcao")),
        _optional_text(spec.get("categoria")),
        _optional_text(spec.get("unidade")),
    )


def _active_canonical_key(row: dict[str, Any]) -> tuple[str | None, ...] | None:
    if not _is_active(row):
        return None
    tipo = _clean_text(row.get("tipo"))
    unidade = _clean_text(row.get("unidade"))
    expected = EXPECTED_UNITS.get(tipo)
    if not expected or unidade != expected or _is_brl(row):
        return None
    return (
        _optional_text(row.get("tipo")),
        _optional_text(row.get("funcao")),
        _optional_text(row.get("categoria")),
        _optional_text(row.get("unidade")),
    )


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_start = _to_date(a.get("vigencia_inicio"))
    b_start = _to_date(b.get("vigencia_inicio"))
    if not a_start or not b_start:
        return False
    a_end = _to_date(a.get("vigencia_fim")) or date(9999, 12, 31)
    b_end = _to_date(b.get("vigencia_fim")) or date(9999, 12, 31)
    return not (a_end < b_start or b_end < a_start)


def detectar_sobreposicoes_ativas(
    parametros: list[dict[str, Any]],
    *,
    include_unit: bool,
) -> set[int]:
    active = [item for item in parametros if _is_active(item)]
    grouped: dict[tuple[str | None, ...], list[dict[str, Any]]] = {}
    for item in active:
        grouped.setdefault(_key(item, include_unit=include_unit), []).append(item)

    overlapping_ids: set[int] = set()
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        for idx in range(len(rows)):
            for jdx in range(idx + 1, len(rows)):
                if _overlap(rows[idx], rows[jdx]):
                    overlapping_ids.add(int(rows[idx]["id"]))
                    overlapping_ids.add(int(rows[jdx]["id"]))
    return overlapping_ids


def detectar_divergencias_ativas(
    parametros: list[dict[str, Any]],
    *,
    include_unit: bool,
) -> set[int]:
    active = [item for item in parametros if _is_active(item)]
    grouped: dict[tuple[str | None, ...], list[dict[str, Any]]] = {}
    for item in active:
        grouped.setdefault(_key(item, include_unit=include_unit), []).append(item)

    divergent_ids: set[int] = set()
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        for idx in range(len(rows)):
            for jdx in range(idx + 1, len(rows)):
                if not _overlap(rows[idx], rows[jdx]):
                    continue
                if _to_decimal_text(rows[idx].get("valor")) != _to_decimal_text(rows[jdx].get("valor")):
                    divergent_ids.add(int(rows[idx]["id"]))
                    divergent_ids.add(int(rows[jdx]["id"]))
    return divergent_ids


def parametro_elegivel_motor_vigente(
    row: dict[str, Any],
    *,
    excluir_qa_smoke: bool = True,
) -> bool:
    if not _is_active(row):
        return False
    if not _vigencia_valida(row):
        return False
    if _is_brl(row):
        return False
    tipo = _clean_text(row.get("tipo"))
    unidade = _clean_text(row.get("unidade"))
    expected = EXPECTED_UNITS.get(tipo)
    if not expected or unidade != expected:
        return False

    if excluir_qa_smoke:
        gov_class = classificacao_governanca_parametro(row)
        if gov_class == GOV_CLASS_QA_SMOKE:
            return False
        if gov_class is None and _is_qa_smoke(row):
            return False
    return True


def parametro_elegivel_fechamento_real(
    row: dict[str, Any],
    *,
    environment: str = "hml",
) -> bool:
    env = _norm_env(environment)
    if not parametro_elegivel_motor_vigente(row, excluir_qa_smoke=False):
        return False
    gov_class = classificacao_governanca_parametro(row)
    if not gov_class:
        return False
    return gov_class in ELIGIBLE_CLASSES_BY_ENV[env]


def contar_elegiveis_fechamento_real(
    parametros: list[dict[str, Any]],
    *,
    environment: str = "hml",
) -> int:
    return sum(1 for row in parametros if parametro_elegivel_fechamento_real(row, environment=environment))


def _canonical_active_ids(parametros: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for row in parametros:
        if _active_canonical_key(row) is not None:
            ids.add(int(row["id"]))
    return ids


def validar_matriz_canonica_completa(parametros: list[dict[str, Any]]) -> dict[str, Any]:
    validar_sem_sobreposicao_ativa_por_chave_canonica(parametros)
    validar_sem_divergencia_ativa_por_chave_semantica(parametros)

    active = [row for row in parametros if _is_active(row)]
    by_key: dict[tuple[str | None, ...], list[dict[str, Any]]] = {}
    for row in active:
        key = _active_canonical_key(row)
        if key is None:
            continue
        by_key.setdefault(key, []).append(row)

    missing: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    matched_ids: list[int] = []

    for spec in CANONICAL_MATRIX:
        key = _canonical_spec_key(spec)
        matches = by_key.get(key, [])
        if not matches:
            missing.append(spec)
            continue

        expected_value = _to_decimal(spec.get("valor"))
        value_ok = None
        selected = matches[0]
        for row in matches:
            if _to_decimal(row.get("valor")) == expected_value:
                selected = row
                value_ok = row
                break
        if value_ok is None:
            mismatch.append(
                {
                    "expected": spec,
                    "found": [
                        {
                            "id": int(row["id"]),
                            "valor": _to_decimal_text(row.get("valor")),
                            "vigencia_inicio": row.get("vigencia_inicio"),
                            "vigencia_fim": row.get("vigencia_fim"),
                        }
                        for row in matches
                    ],
                }
            )
            continue
        matched_ids.append(int(selected["id"]))

    if missing or mismatch:
        details = {
            "missing": missing,
            "mismatch": mismatch,
        }
        raise MatrizCanonicaInvalidaErro(
            f"Matriz canonica incompleta ou divergente: {json.dumps(details, ensure_ascii=False)}",
            code="finance_parameter_canonical_matrix_invalid",
        )

    return {
        "expected_count": len(CANONICAL_MATRIX),
        "matched_count": len(matched_ids),
        "matched_ids": sorted(set(matched_ids)),
    }


def classificar_parametros(
    parametros: list[dict[str, Any]],
    *,
    used_parameter_ids: set[int] | list[int] | tuple[int, ...] | None = None,
) -> list[dict[str, Any]]:
    used_ids = set(int(item) for item in (used_parameter_ids or []))
    overlap_strict = detectar_sobreposicoes_ativas(parametros, include_unit=True)
    overlap_semantic = detectar_sobreposicoes_ativas(parametros, include_unit=False)
    divergent_strict = detectar_divergencias_ativas(parametros, include_unit=True)
    divergent_semantic = detectar_divergencias_ativas(parametros, include_unit=False)

    classified: list[dict[str, Any]] = []
    for item in parametros:
        row = dict(item)
        row_id = int(row["id"])
        tipo = _clean_text(row.get("tipo"))
        expected_unit = EXPECTED_UNITS.get(tipo)
        unit = _clean_text(row.get("unidade"))
        unit_ok = expected_unit == unit if expected_unit else None
        governance_class = classificacao_governanca_parametro(row)

        tags: list[str] = []
        if expected_unit and unit_ok and not _is_brl(row):
            tags.append("oficial")
        if _is_brl(row):
            tags.append("legado_brl")
        if _is_qa_smoke(row):
            tags.append("qa_smoke")
        if row_id in overlap_strict or row_id in overlap_semantic:
            tags.append("sobreposto")
        if row_id in divergent_strict or row_id in divergent_semantic:
            tags.append("divergente")
        if _is_active(row) and expected_unit and unit_ok and not _is_brl(row):
            tags.append("canonico_ativo")
        if row_id not in used_ids:
            tags.append("nao_usado")
        if governance_class:
            tags.append(f"class:{governance_class}")

        row["tags"] = tags
        row["expected_unit"] = expected_unit
        row["unit_ok"] = unit_ok
        row["governance_class"] = governance_class
        row["used_in_persisted_calc"] = row_id in used_ids
        row["eligible_for_real_closure"] = parametro_elegivel_fechamento_real(row, environment="hml")
        row["eligible_for_motor"] = parametro_elegivel_motor_vigente(row, excluir_qa_smoke=False)
        classified.append(row)
    return classified


def validar_sem_sobreposicao_ativa_por_chave_canonica(parametros: list[dict[str, Any]]) -> None:
    overlapping = detectar_sobreposicoes_ativas(parametros, include_unit=True)
    if overlapping:
        ids = ",".join(str(item) for item in sorted(overlapping))
        raise GovernancaParametrosErro(
            f"Sobreposicao ativa detectada na chave canonica de parametros: {ids}.",
            code="finance_parameter_active_overlap_detected",
        )


def validar_sem_sobreposicao_ativa_por_chave_semantica(parametros: list[dict[str, Any]]) -> None:
    overlapping = detectar_sobreposicoes_ativas(parametros, include_unit=False)
    if overlapping:
        ids = ",".join(str(item) for item in sorted(overlapping))
        raise GovernancaParametrosErro(
            f"Sobreposicao ativa semantica detectada para parametros: {ids}.",
            code="finance_parameter_active_semantic_overlap_detected",
        )


def validar_sem_divergencia_ativa_por_chave_semantica(parametros: list[dict[str, Any]]) -> None:
    divergent = detectar_divergencias_ativas(parametros, include_unit=False)
    if divergent:
        ids = ",".join(str(item) for item in sorted(divergent))
        raise GovernancaParametrosErro(
            f"Divergencia ativa semantica detectada para parametros: {ids}.",
            code="finance_parameter_active_semantic_divergence_detected",
        )


def filtrar_parametros_para_fechamento_real(
    parametros: list[dict[str, Any]],
    *,
    environment: str = "hml",
) -> list[dict[str, Any]]:
    return [item for item in parametros if parametro_elegivel_fechamento_real(item, environment=environment)]


def validar_matriz_canonica_para_fechamento_real(
    parametros: list[dict[str, Any]],
    *,
    environment: str = "hml",
) -> dict[str, Any]:
    matrix = validar_matriz_canonica_completa(parametros)
    by_id = {int(row["id"]): row for row in parametros}

    ineligible = [
        parameter_id
        for parameter_id in matrix["matched_ids"]
        if not parametro_elegivel_fechamento_real(by_id[parameter_id], environment=environment)
    ]
    if ineligible:
        raise GovernancaParametrosErro(
            f"Matriz canonica encontrada, mas parametros nao elegiveis para fechamento real: {','.join(str(i) for i in ineligible)}.",
            code="finance_parameter_real_closure_matrix_ineligible",
        )

    return {
        **matrix,
        "eligible_count": len(matrix["matched_ids"]),
        "eligible_ids": matrix["matched_ids"],
    }


def _classe_desejada_promocao_hml(
    row: dict[str, Any],
    *,
    canonical_active_ids: set[int],
) -> str:
    row_id = int(row["id"])
    if row_id in canonical_active_ids:
        return GOV_CLASS_HML_RELEASE_CANDIDATE
    if _is_brl(row):
        return GOV_CLASS_LEGACY
    if _is_qa_smoke(row):
        return GOV_CLASS_QA_SMOKE
    if not _is_active(row):
        return GOV_CLASS_DEPRECATED
    return GOV_CLASS_QA_SMOKE


def construir_plano_promocao_hml_release_candidate(
    parametros: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    validar_sem_sobreposicao_ativa_por_chave_semantica(parametros)
    validar_sem_divergencia_ativa_por_chave_semantica(parametros)
    matrix = validar_matriz_canonica_completa(parametros)
    canonical_active_ids = set(matrix["matched_ids"])

    plan: list[dict[str, Any]] = []
    for row in parametros:
        row_id = int(row["id"])
        explicit_class = extrair_classe_governanca(row)
        current_class = classificacao_governanca_parametro(row)
        desired_class = _classe_desejada_promocao_hml(row, canonical_active_ids=canonical_active_ids)
        if explicit_class == desired_class:
            continue
        before_motivo = _clean_text(row.get("motivo"))
        after_motivo = atualizar_motivo_com_classe_governanca(before_motivo, desired_class)
        plan.append(
            {
                "parameter_id": row_id,
                "action": "promover_classificacao_governanca",
                "before": {
                    "status": row.get("status"),
                    "motivo": before_motivo,
                    "governance_class": current_class,
                },
                "after": {
                    "motivo": after_motivo,
                    "governance_class": desired_class,
                },
            }
        )

    return sorted(plan, key=lambda item: int(item["parameter_id"]))


def construir_plano_saneamento_seguro(
    parametros: list[dict[str, Any]],
    *,
    reference_date: date,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for row in parametros:
        if not _is_active(row):
            continue
        row_id = int(row["id"])
        tipo = _clean_text(row.get("tipo"))
        unidade = _clean_text(row.get("unidade"))
        motivo = _clean_text(row.get("motivo"))

        if _is_brl(row):
            plan.append(
                {
                    "parameter_id": row_id,
                    "action": "inativar_legado_brl",
                    "set_status": "inativo",
                    "set_vigencia_fim": (_to_date(row.get("vigencia_fim")) or reference_date).isoformat(),
                    "append_motivo": "GOV-HML: legado BRL inativado para impedir elegibilidade no motor vigente.",
                    "before": {
                        "status": row.get("status"),
                        "vigencia_fim": row.get("vigencia_fim"),
                        "motivo": motivo,
                    },
                }
            )
            continue

        if tipo in {"periodo_diurno_inicio", "periodo_diurno_fim"} and unidade == "horario":
            plan.append(
                {
                    "parameter_id": row_id,
                    "action": "inativar_unidade_horario_legado",
                    "set_status": "inativo",
                    "set_vigencia_fim": (_to_date(row.get("vigencia_fim")) or reference_date).isoformat(),
                    "append_motivo": "GOV-HML: unidade horario legada inativada; minutos_do_dia e obrigatorio.",
                    "before": {
                        "status": row.get("status"),
                        "vigencia_fim": row.get("vigencia_fim"),
                        "motivo": motivo,
                    },
                }
            )

    return sorted(plan, key=lambda item: int(item["parameter_id"]))


def aplicar_plano_saneamento(
    db,
    *,
    plano: list[dict[str, Any]],
    actor_user_id: int,
    now_iso: str | None = None,
) -> list[dict[str, Any]]:
    timestamp = now_iso or datetime.utcnow().replace(microsecond=0).isoformat()
    applied: list[dict[str, Any]] = []
    for item in plano:
        parameter_id = int(item["parameter_id"])
        before = dict(item.get("before") or {})
        append_reason = _clean_text(item.get("append_motivo"))
        vigencia_fim = _optional_text(item.get("set_vigencia_fim"))

        current_row = db.execute(
            "SELECT id, status, vigencia_fim::text AS vigencia_fim, motivo FROM financeiro_parametros WHERE id = %s",
            (parameter_id,),
        ).fetchone()
        if not current_row:
            continue
        current = dict(current_row)
        combined_reason = "; ".join(part for part in [_clean_text(current.get("motivo")), append_reason] if part)

        update_sql = """
            UPDATE financeiro_parametros
            SET status = %s,
                vigencia_fim = COALESCE(vigencia_fim, %s::date),
                motivo = %s,
                updated_by = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, status, vigencia_fim::text AS vigencia_fim, motivo
        """
        assert_no_delete_statement(update_sql)

        updated_row = db.execute(
            update_sql,
            (
                _clean_text(item.get("set_status")) or "inativo",
                vigencia_fim,
                combined_reason,
                int(actor_user_id),
                parameter_id,
            ),
        ).fetchone()
        after = dict(updated_row) if updated_row else {}
        audit_payload_before = {"parameter_id": parameter_id, **before}
        audit_payload_after = {
            "parameter_id": parameter_id,
            "status": after.get("status"),
            "vigencia_fim": after.get("vigencia_fim"),
            "motivo": after.get("motivo"),
            "audit_metadata": {
                "event_name": "finance.parameter.updated",
                "actor_user_id": int(actor_user_id),
                "source": "governanca_parametros_hml",
                "executed_at": timestamp,
                "action": item.get("action"),
            },
        }
        db.execute(
            """
            INSERT INTO auditoria_eventos (
                entidade, entidade_id, acao, payload_anterior, payload_novo, realizado_por, observacao
            )
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """,
            (
                "finance_parameter",
                parameter_id,
                "finance.parameter.updated",
                json.dumps(audit_payload_before, ensure_ascii=False),
                json.dumps(audit_payload_after, ensure_ascii=False),
                int(actor_user_id),
                "governanca_hml_parametros_saneamento",
            ),
        )
        applied.append(
            {
                "parameter_id": parameter_id,
                "action": item.get("action"),
                "before": current,
                "after": after,
            }
        )
    return applied


def aplicar_plano_promocao_classificacao(
    db,
    *,
    plano: list[dict[str, Any]],
    actor_user_id: int,
    now_iso: str | None = None,
    audit_observacao: str = "governanca_hml_parametros_promocao",
) -> list[dict[str, Any]]:
    timestamp = now_iso or datetime.utcnow().replace(microsecond=0).isoformat()
    applied: list[dict[str, Any]] = []

    update_sql = """
        UPDATE financeiro_parametros
        SET motivo = %s,
            updated_by = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING id, status, vigencia_inicio::text AS vigencia_inicio, vigencia_fim::text AS vigencia_fim, motivo
    """
    assert_no_delete_statement(update_sql)

    for item in plano:
        parameter_id = int(item["parameter_id"])
        before = dict(item.get("before") or {})
        after_data = dict(item.get("after") or {})

        current_row = db.execute(
            """
            SELECT id, status, vigencia_inicio::text AS vigencia_inicio,
                   vigencia_fim::text AS vigencia_fim, motivo
            FROM financeiro_parametros
            WHERE id = %s
            """,
            (parameter_id,),
        ).fetchone()
        if not current_row:
            continue
        current = dict(current_row)

        new_reason = _clean_text(after_data.get("motivo"))
        updated_row = db.execute(
            update_sql,
            (
                new_reason,
                int(actor_user_id),
                parameter_id,
            ),
        ).fetchone()
        after = dict(updated_row) if updated_row else {}

        audit_payload_before = {
            "parameter_id": parameter_id,
            "status": current.get("status"),
            "vigencia_inicio": current.get("vigencia_inicio"),
            "vigencia_fim": current.get("vigencia_fim"),
            "motivo": current.get("motivo"),
            "governance_class": before.get("governance_class"),
        }
        audit_payload_after = {
            "parameter_id": parameter_id,
            "status": after.get("status"),
            "vigencia_inicio": after.get("vigencia_inicio"),
            "vigencia_fim": after.get("vigencia_fim"),
            "motivo": after.get("motivo"),
            "governance_class": after_data.get("governance_class"),
            "audit_metadata": {
                "event_name": "finance.parameter.classification.updated",
                "actor_user_id": int(actor_user_id),
                "source": "governanca_parametros_hml_promocao",
                "executed_at": timestamp,
                "action": item.get("action"),
            },
        }
        db.execute(
            """
            INSERT INTO auditoria_eventos (
                entidade, entidade_id, acao, payload_anterior, payload_novo, realizado_por, observacao
            )
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """,
            (
                "finance_parameter",
                parameter_id,
                "finance.parameter.classification.updated",
                json.dumps(audit_payload_before, ensure_ascii=False),
                json.dumps(audit_payload_after, ensure_ascii=False),
                int(actor_user_id),
                audit_observacao,
            ),
        )

        applied.append(
            {
                "parameter_id": parameter_id,
                "action": item.get("action"),
                "before": current,
                "after": after,
                "before_governance_class": before.get("governance_class"),
                "after_governance_class": after_data.get("governance_class"),
            }
        )

    return applied


def assert_no_delete_statement(sql: str) -> None:
    normalized = " ".join((sql or "").lower().split())
    if " delete " in f" {normalized} ":
        raise GovernancaParametrosErro(
            "Saneamento de governanca nao pode usar DELETE.",
            code="finance_parameter_governance_delete_forbidden",
        )

