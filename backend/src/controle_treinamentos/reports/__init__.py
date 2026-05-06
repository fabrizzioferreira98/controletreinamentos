"""Reports package — split from monolithic reports.py.

Re-exports all public functions for backward compatibility.
Internal implementation lives in _reports_impl.py.
"""
import time
from typing import Callable, TypeVar

from ..core.metrics import record_pdf_generation
from . import _reports_impl

_T = TypeVar("_T")


def _timed_pdf_generation(renderer: str, callback: Callable[..., _T], *args, **kwargs) -> _T:
    started = time.monotonic()
    try:
        result = callback(*args, **kwargs)
    except Exception:
        record_pdf_generation(renderer, "failed", int((time.monotonic() - started) * 1000))
        raise
    size_bytes = len(result) if isinstance(result, (bytes, bytearray, memoryview)) else None
    record_pdf_generation(renderer, "success", int((time.monotonic() - started) * 1000), size_bytes=size_bytes)
    return result


def build_auditoria_pdf(*args, **kwargs):
    return _timed_pdf_generation("build_auditoria_pdf", _reports_impl.build_auditoria_pdf, *args, **kwargs)


def build_habilitacoes_consolidado_pdf(*args, **kwargs):
    return _timed_pdf_generation(
        "build_habilitacoes_consolidado_pdf",
        _reports_impl.build_habilitacoes_consolidado_pdf,
        *args,
        **kwargs,
    )


def build_tripulante_treinamentos_pdf(*args, **kwargs):
    return _timed_pdf_generation(
        "build_tripulante_treinamentos_pdf",
        _reports_impl.build_tripulante_treinamentos_pdf,
        *args,
        **kwargs,
    )


def build_user_guide_pdf(*args, **kwargs):
    return _timed_pdf_generation("build_user_guide_pdf", _reports_impl.build_user_guide_pdf, *args, **kwargs)

__all__ = [
    "build_auditoria_pdf",
    "build_habilitacoes_consolidado_pdf",
    "build_tripulante_treinamentos_pdf",
    "build_user_guide_pdf",
]
