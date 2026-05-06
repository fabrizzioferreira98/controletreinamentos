from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from flask import Response, current_app, g, has_app_context
from flask_login import current_user

from .domain_errors import DomainForbiddenError, DomainUnexpectedError
from .metrics import record_file_access_response

FileAccessAction = Literal["preview", "download"]
PermissionSpec = str | tuple[str, ...]


@dataclass(frozen=True)
class FileAccessPolicy:
    key: str
    subject: str
    view_permission: PermissionSpec
    download_permission: PermissionSpec
    replace_permission: PermissionSpec | None
    delete_permission: PermissionSpec | None
    cache_control: str = "private, no-store"
    link_policy: str = "authenticated-session"
    link_expires_after: str = "session"
    audit_channel: str = "application-log"
    stream_chunk_size: int = 64 * 1024
    preview_disposition: str = "inline"
    download_disposition: str = "attachment"
    include_content_disposition: bool = True
    sensitive: bool = True


TRIPULANTE_FILE_ACCESS_POLICY = FileAccessPolicy(
    key="tripulante_file",
    subject="documento de tripulante",
    view_permission="tripulantes_file:view",
    download_permission="tripulantes_file:view",
    replace_permission="tripulantes_file:replace",
    delete_permission="tripulantes_file:delete",
)

TRIPULANTE_FILE_CONSOLIDATED_ACCESS_POLICY = FileAccessPolicy(
    key="tripulante_file_consolidated",
    subject="documento consolidado da aba File",
    view_permission="tripulantes_file:view",
    download_permission="tripulantes_file:view",
    replace_permission=None,
    delete_permission=None,
)

TRAINING_ATTACHMENT_ACCESS_POLICY = FileAccessPolicy(
    key="training_attachment",
    subject="anexo de treinamento",
    view_permission="treinamentos_anexos:view",
    download_permission="treinamentos_anexos:view",
    replace_permission=None,
    delete_permission="treinamentos_anexos:delete",
)

TRIPULANTE_PHOTO_ACCESS_POLICY = FileAccessPolicy(
    key="tripulante_photo",
    subject="foto de tripulante",
    view_permission=("tripulantes:view", "relatorio_individual:view"),
    download_permission=("tripulantes:view", "relatorio_individual:view"),
    replace_permission="tripulantes:edit",
    delete_permission="tripulantes:edit",
    include_content_disposition=False,
)


def _permission_options(permission: PermissionSpec | None) -> tuple[str, ...]:
    if permission is None:
        return ()
    if isinstance(permission, str):
        return (permission,)
    return tuple(str(item) for item in permission if str(item).strip())


def _serialize_permission(permission: PermissionSpec | None):
    options = _permission_options(permission)
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    return list(options)


def file_access_policy_contract(policy: FileAccessPolicy) -> dict:
    return {
        "preview_permission": _serialize_permission(policy.view_permission),
        "download_permission": _serialize_permission(policy.download_permission),
        "replace_permission": _serialize_permission(policy.replace_permission),
        "delete_permission": _serialize_permission(policy.delete_permission),
        "link_policy": policy.link_policy,
        "link_expires_after": policy.link_expires_after,
        "cache_control": policy.cache_control,
        "audit_channel": policy.audit_channel,
    }


def resolve_file_access_action(query_args) -> FileAccessAction:
    raw_value = ""
    if query_args is not None:
        raw_value = str(query_args.get("download", "") or "").strip().lower()
    return "download" if raw_value in {"1", "true", "yes", "sim"} else "preview"


def required_permission_for_action(policy: FileAccessPolicy, action: FileAccessAction) -> PermissionSpec:
    if action == "download":
        return policy.download_permission
    return policy.view_permission


def user_has_any_permission(user, permission: PermissionSpec | None) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if not hasattr(user, "has_permission"):
        return False
    return any(user.has_permission(option) for option in _permission_options(permission))


def assert_file_access_allowed(policy: FileAccessPolicy, action: FileAccessAction, *, user=None) -> None:
    actor = current_user if user is None else user
    required_permission = required_permission_for_action(policy, action)
    if user_has_any_permission(actor, required_permission):
        return
    raise DomainForbiddenError(
        f"Sem permissao para {action} {policy.subject}.",
        code=f"{policy.key}_{action}_forbidden",
    )


def _coerce_binary_payload(payload_bytes, *, policy: FileAccessPolicy) -> bytes:
    if isinstance(payload_bytes, bytes):
        data = payload_bytes
    elif isinstance(payload_bytes, bytearray):
        data = bytes(payload_bytes)
    elif isinstance(payload_bytes, memoryview):
        data = payload_bytes.tobytes()
    else:
        raise DomainUnexpectedError(
            "Blob binario indisponivel para resposta.",
            code=f"{policy.key}_invalid_binary_payload",
        )
    if not data:
        raise DomainUnexpectedError(
            "Blob binario vazio para resposta.",
            code=f"{policy.key}_empty_binary_payload",
        )
    return data


def _iter_payload_chunks(payload_bytes: bytes, *, chunk_size: int) -> Iterable[bytes]:
    for offset in range(0, len(payload_bytes), chunk_size):
        yield payload_bytes[offset : offset + chunk_size]


def _safe_header_filename(filename: str | None) -> str:
    value = str(filename or "arquivo.bin").replace("\r", "").replace("\n", "").replace('"', "").strip()
    return value or "arquivo.bin"


def audit_file_access(
    policy: FileAccessPolicy,
    *,
    action: FileAccessAction,
    entity_id: int | str | None,
    subject_id: int | str | None = None,
    source: str = "route",
    result: str = "allowed",
) -> None:
    if not has_app_context():
        return
    current_app.logger.info(
        "file_access policy=%s action=%s result=%s entity_id=%s subject_id=%s user_id=%s request_id=%s "
        "source=%s link_policy=%s link_expires_after=%s",
        policy.key,
        action,
        result,
        entity_id,
        subject_id,
        getattr(current_user, "id", None),
        getattr(g, "request_id", None),
        source,
        policy.link_policy,
        policy.link_expires_after,
    )


def build_file_access_response(
    *,
    policy: FileAccessPolicy,
    action: FileAccessAction,
    payload_bytes,
    mime_type: str,
    filename: str | None = None,
    entity_id: int | str | None = None,
    subject_id: int | str | None = None,
    source: str = "route",
    user=None,
) -> Response:
    started = time.monotonic()
    try:
        assert_file_access_allowed(policy, action, user=user)
        data = _coerce_binary_payload(payload_bytes, policy=policy)
        audit_file_access(policy, action=action, entity_id=entity_id, subject_id=subject_id, source=source)

        response = Response(
            _iter_payload_chunks(data, chunk_size=policy.stream_chunk_size),
            mimetype=mime_type or "application/octet-stream",
            direct_passthrough=False,
        )
        response.content_length = len(data)
        if policy.include_content_disposition:
            disposition = policy.download_disposition if action == "download" else policy.preview_disposition
            response.headers["Content-Disposition"] = f"{disposition}; filename={_safe_header_filename(filename)}"
        response.headers["Cache-Control"] = policy.cache_control
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-File-Access-Action"] = action
        response.headers["X-File-Link-Policy"] = policy.link_policy
        response.headers["X-File-Link-Expires"] = policy.link_expires_after
        record_file_access_response(
            policy=policy.key,
            action=action,
            source=source,
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
            size_bytes=len(data),
        )
        return response
    except DomainForbiddenError:
        record_file_access_response(
            policy=policy.key,
            action=action,
            source=source,
            status="forbidden",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    except Exception:
        record_file_access_response(
            policy=policy.key,
            action=action,
            source=source,
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise
