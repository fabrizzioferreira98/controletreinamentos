from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True)
class IndexDebtItem:
    index_name: str
    table: str
    columns: tuple[str, ...]
    classification: str
    duplicate_of: str
    action: str
    precondition_to_drop: str


INDEX_DEBT_ITEMS: Final[tuple[IndexDebtItem, ...]] = (
    IndexDebtItem(
        index_name="idx_treinamentos_tripulante_vencimento",
        table="treinamentos",
        columns=("tripulante_id", "data_vencimento"),
        classification="duplicate_same_columns",
        duplicate_of="idx_treinamentos_tripulante_data_vencimento",
        action="candidate_drop_in_dedicated_index_cleanup",
        precondition_to_drop=(
            "capturar uso real via pg_stat_user_indexes em ambiente vivo, confirmar ausencia de plano "
            "dependente e remover em migracao pequena e reversivel"
        ),
    ),
    IndexDebtItem(
        index_name="idx_treinamentos_vencimento",
        table="treinamentos",
        columns=("data_vencimento",),
        classification="duplicate_same_columns",
        duplicate_of="idx_treinamentos_data_vencimento",
        action="candidate_drop_in_dedicated_index_cleanup",
        precondition_to_drop=(
            "capturar uso real via pg_stat_user_indexes em ambiente vivo, confirmar ausencia de plano "
            "dependente e remover em migracao pequena e reversivel"
        ),
    ),
    IndexDebtItem(
        index_name="idx_treinamentos_data_venc_tripulante",
        table="treinamentos",
        columns=("data_vencimento", "tripulante_id"),
        classification="overlap_reversed_columns",
        duplicate_of="idx_treinamentos_tripulante_data_vencimento",
        action="keep_under_measurement_until_workload_proves_unused",
        precondition_to_drop=(
            "comparar planos de filtros por vencimento e por tripulante, medir seletividade real e so "
            "remover se o indice reverso nao sustentar consulta quente"
        ),
    ),
    IndexDebtItem(
        index_name="idx_pilotos_status_base",
        table="pilotos",
        columns=("status", "base_id"),
        classification="overlap_different_leading_column",
        duplicate_of="idx_pilotos_base_status_nome",
        action="keep_under_measurement_until_workload_proves_unused",
        precondition_to_drop=(
            "confirmar se filtros liderados por status ainda existem; se nao existirem, consolidar "
            "em limpeza dedicada sem alterar owner de status/base"
        ),
    ),
)


def index_debt_items() -> tuple[dict, ...]:
    return tuple(asdict(item) for item in INDEX_DEBT_ITEMS)


def duplicate_index_debt_items() -> tuple[dict, ...]:
    return tuple(
        asdict(item)
        for item in INDEX_DEBT_ITEMS
        if item.classification == "duplicate_same_columns"
    )


def index_debt_by_name() -> dict[str, dict]:
    return {item.index_name: asdict(item) for item in INDEX_DEBT_ITEMS}
