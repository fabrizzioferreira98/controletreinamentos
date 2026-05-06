"""Reports package — split from monolithic reports.py.

Re-exports all public functions for backward compatibility.
Internal implementation lives in _reports_impl.py.
"""
from ._reports_impl import (
    build_auditoria_pdf,
    build_habilitacoes_consolidado_pdf,
    build_produtividade_consolidado_pdf,
    build_produtividade_tripulante_pdf,
    build_tripulante_treinamentos_pdf,
    build_user_guide_pdf,
    decimal_to_currency,
)

__all__ = [
    "build_auditoria_pdf",
    "build_habilitacoes_consolidado_pdf",
    "build_produtividade_consolidado_pdf",
    "build_produtividade_tripulante_pdf",
    "build_tripulante_treinamentos_pdf",
    "build_user_guide_pdf",
    "decimal_to_currency",
]
