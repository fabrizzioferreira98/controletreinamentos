from __future__ import annotations


class DomainError(Exception):
    """Erro de caso de uso com contrato interno previsivel."""

    status = 400
    code = "domain_error"

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = int(status if status is not None else self.status)
        self.code = code or self.code
        self.details = details or {}


class DomainValidationError(DomainError):
    status = 400
    code = "validation"


class DomainNotFoundError(DomainError):
    status = 404
    code = "not_found"


class DomainConflictError(DomainError):
    status = 409
    code = "conflict"


class DomainForbiddenError(DomainError):
    status = 403
    code = "forbidden"


class DomainUnavailableError(DomainError):
    status = 503
    code = "unavailable"


class DomainUnexpectedError(DomainError):
    status = 500
    code = "unexpected"
