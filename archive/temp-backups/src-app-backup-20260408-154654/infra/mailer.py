from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from flask import current_app

from ..db import get_db
from ..services import business_today, calculate_training_status, parse_date


@dataclass
class NotificationResult:
    sent: bool
    reason: str
    error: str | None = None


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        return max(minimum, value)
    return value


def _set_control_value(db, key: str, value: str) -> None:
    db.execute(
        """
        INSERT INTO sistema_controle (chave, valor)
        VALUES (%s, %s)
        ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
        """,
        (key, value),
    )


def _smtp_missing_fields(config: dict) -> list[str]:
    missing: list[str] = []
    if not (config.get("host") or "").strip():
        missing.append("SMTP_HOST")
    if not (config.get("user") or "").strip():
        missing.append("SMTP_USER")
    if not (config.get("password") or "").strip():
        missing.append("SMTP_PASSWORD")
    return missing


def get_active_recipients():
    db = get_db()
    return [
        row["email_destinatario"]
        for row in db.execute(
            "SELECT email_destinatario FROM notificacoes_email WHERE ativo = 1 ORDER BY email_destinatario"
        ).fetchall()
    ]


def validate_notification_dispatch_readiness() -> dict:
    recipients = get_active_recipients()
    provider = get_email_provider()
    smtp_config = get_smtp_config()
    resend_config = get_resend_config()
    email_ready = False
    if provider == "resend":
        email_ready = bool(resend_config["api_key"] and resend_config["sender"])
    else:
        email_ready = bool(smtp_config["host"] and smtp_config["user"] and smtp_config["password"])
    missing_config_fields: list[str] = []
    if provider == "resend":
        if not resend_config["api_key"]:
            missing_config_fields.append("RESEND_API_KEY")
        if not resend_config["sender"]:
            missing_config_fields.append("RESEND_FROM")
    else:
        missing_config_fields.extend(_smtp_missing_fields(smtp_config))
    return {
        "recipients_count": len(recipients),
        "provider": provider,
        "email_ready": email_ready,
        "missing_config_fields": missing_config_fields,
    }


def fetch_notification_training_rows(*, include_details: bool = True):
    db = get_db()
    lookahead_days = _env_int("NOTIFICATION_LOOKAHEAD_DAYS", 90, minimum=30)
    horizon = business_today() + timedelta(days=lookahead_days)
    select_cols = """
        t.id AS treinamento_id,
        t.data_vencimento
    """
    joins = ""
    if include_details:
        select_cols = """
            t.id AS treinamento_id,
            t.data_vencimento,
            c.nome AS tripulante_nome,
            c.email AS tripulante_email,
            e.nome AS equipamento_nome,
            tt.nome AS tipo_treinamento_nome
        """
        joins = """
            JOIN tripulantes c ON c.id = t.tripulante_id
            LEFT JOIN equipamentos e ON e.id = t.equipamento_id
            JOIN tipos_treinamento tt ON tt.id = t.tipo_treinamento_id
        """
    return db.execute(
        f"""
        SELECT {select_cols}
        FROM treinamentos t
        {joins}
        WHERE t.data_vencimento IS NOT NULL
          AND t.data_vencimento <= %s
        ORDER BY t.data_vencimento
        """,
        (horizon,),
    ).fetchall()


def fetch_sent_notification_map(training_ids):
    if not training_ids:
        return {}
    db = get_db()
    today = business_today()
    rows = db.execute(
        """
        SELECT treinamento_id, gatilho
        FROM notificacoes_treinamento
        WHERE treinamento_id = ANY(%s)
          AND CAST(enviado_em AS DATE) = %s
        """,
        (training_ids, today),
    ).fetchall()
    sent = {}
    for row in rows:
        sent.setdefault(row["treinamento_id"], set()).add(row["gatilho"])
    return sent


def build_notification_blocks(rows, *, include_already_sent: bool = False, sent_map=None):
    blocks = {"vencidos": [], "em_30_dias": [], "em_60_dias": [], "em_90_dias": []}
    today = business_today()
    if sent_map is None:
        sent_map = fetch_sent_notification_map([row["treinamento_id"] for row in rows])

    for row in rows:
        due_date = parse_date(row["data_vencimento"])
        if due_date is None:
            continue

        days = (due_date - today).days
        status = calculate_training_status(row["data_vencimento"], today)
        trigger = None
        if due_date < today:
            trigger = "vencido"
            block_key = "vencidos"
        elif days <= 30:
            trigger = "30"
            block_key = "em_30_dias"
        elif days <= 60:
            trigger = "60"
            block_key = "em_60_dias"
        elif days <= 90:
            trigger = "90"
            block_key = "em_90_dias"
        else:
            continue

        if (not include_already_sent) and trigger in sent_map.get(row["treinamento_id"], set()):
            continue

        item = {
            "treinamento_id": row["treinamento_id"],
            "tripulante": row.get("tripulante_nome") or "-",
            "tripulante_email": row.get("tripulante_email") or "",
            "equipamento": row.get("equipamento_nome") or "-",
            "tipo": row.get("tipo_treinamento_nome") or "-",
            "data_vencimento": row["data_vencimento"],
            "status": status,
            "gatilho": trigger,
            "dias_para_vencer": days,
        }
        blocks[block_key].append(item)

    return blocks


def build_notification_blocks_pair(rows, *, sent_map=None):
    blocks = {"vencidos": [], "em_30_dias": [], "em_60_dias": [], "em_90_dias": []}
    blocks_all = {"vencidos": [], "em_30_dias": [], "em_60_dias": [], "em_90_dias": []}
    today = business_today()
    if sent_map is None:
        sent_map = fetch_sent_notification_map([row["treinamento_id"] for row in rows])

    for row in rows:
        due_date = parse_date(row["data_vencimento"])
        if due_date is None:
            continue

        days = (due_date - today).days
        status = calculate_training_status(row["data_vencimento"], today)
        trigger = None
        if due_date < today:
            trigger = "vencido"
            block_key = "vencidos"
        elif days <= 30:
            trigger = "30"
            block_key = "em_30_dias"
        elif days <= 60:
            trigger = "60"
            block_key = "em_60_dias"
        elif days <= 90:
            trigger = "90"
            block_key = "em_90_dias"
        else:
            continue

        item = {
            "treinamento_id": row["treinamento_id"],
            "tripulante": row.get("tripulante_nome") or "-",
            "tripulante_email": row.get("tripulante_email") or "",
            "equipamento": row.get("equipamento_nome") or "-",
            "tipo": row.get("tipo_treinamento_nome") or "-",
            "data_vencimento": row["data_vencimento"],
            "status": status,
            "gatilho": trigger,
            "dias_para_vencer": days,
        }
        blocks_all[block_key].append(item)
        if trigger not in sent_map.get(row["treinamento_id"], set()):
            blocks[block_key].append(item)

    return blocks, blocks_all


def render_email_body(blocks):
    sections = [
        ("1. Vencidos", blocks["vencidos"]),
        ("2. Vencendo em até 30 dias", blocks["em_30_dias"]),
        ("3. Vencendo entre 31 e 60 dias", blocks["em_60_dias"]),
        ("4. Vencendo entre 61 e 90 dias", blocks["em_90_dias"]),
    ]

    lines = ["Relatório diário de vencimentos de treinamentos", ""]
    for title, items in sections:
        lines.append(title)
        if not items:
            lines.append("Sem registros.")
            lines.append("")
            continue
        for item in items:
            lines.append(
                f"- {item['tripulante']} | {item['equipamento']} | {item['tipo']} | "
                f"{item['data_vencimento']} | {item['status']}"
            )
        lines.append("")
    return "\n".join(lines)


def get_smtp_config():
    smtp_user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS") or "").strip()
    smtp_host = (os.getenv("SMTP_HOST") or os.getenv("MAIL_SERVER") or "").strip()
    smtp_port = _env_int("SMTP_PORT", 587, minimum=1)
    default_use_ssl = smtp_port == 465
    use_ssl = env_flag("SMTP_USE_SSL", default=default_use_ssl)
    use_tls = env_flag("SMTP_USE_TLS", default=not use_ssl)
    return {
        "host": smtp_host,
        "port": smtp_port,
        "user": smtp_user,
        "password": smtp_password,
        "sender": (
            os.getenv("SMTP_SENDER")
            or os.getenv("MAIL_DEFAULT_SENDER")
            or smtp_user
            or "no-reply@interno.local"
        ),
        "use_ssl": bool(use_ssl),
        "use_tls": bool(use_tls),
    }


def get_email_provider():
    return (os.getenv("EMAIL_PROVIDER") or "smtp").strip().lower()


def get_resend_config():
    return {
        "api_key": os.getenv("RESEND_API_KEY", "").strip(),
        "sender": os.getenv("RESEND_FROM", "").strip(),
    }


def send_with_resend(*, subject: str, body: str, recipients: list[str]):
    config = get_resend_config()
    if not config["api_key"] or not config["sender"]:
        raise RuntimeError("resend_not_configured")

    payload = {
        "from": config["sender"],
        "to": recipients,
        "subject": subject,
        "text": body,
    }
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status >= 300:
                raise RuntimeError(f"resend_http_{response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"resend_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("resend_network_error") from exc


def generate_notification_payload(
    *,
    include_diagnostics: bool = True,
    include_preview_tables: bool = True,
    include_body: bool = True,
):
    recipients = get_active_recipients()
    rows = fetch_notification_training_rows(include_details=include_preview_tables)
    sent_map = fetch_sent_notification_map([row["treinamento_id"] for row in rows])
    blocks, blocks_all_pair = build_notification_blocks_pair(rows, sent_map=sent_map)
    blocks_all = blocks_all_pair if include_diagnostics else None
    total_items = sum(len(items) for items in blocks.values())
    total_items_all = sum(len(items) for items in blocks_all.values()) if blocks_all else total_items
    total_items_sent_today = max(0, total_items_all - total_items) if include_diagnostics else 0
    provider = get_email_provider()
    smtp_config = get_smtp_config()
    resend_config = get_resend_config()
    email_ready = False
    missing_config_fields: list[str] = []
    if provider == "resend":
        email_ready = bool(resend_config["api_key"] and resend_config["sender"])
        if not resend_config["api_key"]:
            missing_config_fields.append("RESEND_API_KEY")
        if not resend_config["sender"]:
            missing_config_fields.append("RESEND_FROM")
    else:
        email_ready = bool(smtp_config["host"] and smtp_config["user"] and smtp_config["password"])
        missing_config_fields.extend(_smtp_missing_fields(smtp_config))
    body = render_email_body(blocks) if include_body else ""
    return {
        "recipients": recipients,
        "blocks": blocks,
        "blocks_all": blocks_all or blocks,
        "body": body,
        "total_items": total_items,
        "total_items_all": total_items_all,
        "total_items_sent_today": total_items_sent_today,
        "provider": provider,
        "email_ready": email_ready,
        "missing_config_fields": missing_config_fields,
    }


def send_daily_notifications(app):
    with app.app_context():
        db = get_db()
        payload = generate_notification_payload(include_diagnostics=False)
        recipients = payload["recipients"]
        now_text = datetime.now().strftime("%d/%m/%Y %H:%M")

        _set_control_value(db, "notification_last_run", now_text)
        db.commit()

        if not recipients:
            _set_control_value(db, "notification_last_error", "Nenhum destinatário ativo configurado.")
            db.commit()
            return NotificationResult(False, "no_recipients")

        blocks = payload["blocks"]
        if not any(blocks.values()):
            _set_control_value(db, "notification_last_error", "")
            db.commit()
            return NotificationResult(False, "no_due_items")

        provider = get_email_provider()
        body = render_email_body(blocks)
        subject = "Controle diário de treinamentos"

        try:
            if provider == "resend":
                send_with_resend(subject=subject, body=body, recipients=recipients)
            else:
                smtp_config = get_smtp_config()
                missing = _smtp_missing_fields(smtp_config)
                if missing:
                    message = f"Configuração SMTP incompleta: {', '.join(missing)}"
                    _set_control_value(db, "notification_last_error", message)
                    db.commit()
                    return NotificationResult(False, "smtp_not_configured", message)
                message = MIMEText(body, "plain", "utf-8")
                message["Subject"] = subject
                message["From"] = smtp_config["sender"]
                message["To"] = ", ".join(recipients)
                smtp_factory = smtplib.SMTP_SSL if smtp_config["use_ssl"] else smtplib.SMTP
                with smtp_factory(smtp_config["host"], smtp_config["port"], timeout=30) as smtp:
                    if smtp_config["use_tls"] and not smtp_config["use_ssl"]:
                        smtp.starttls()
                    smtp.login(smtp_config["user"], smtp_config["password"])
                    smtp.sendmail(smtp_config["sender"], recipients, message.as_string())
        except (OSError, smtplib.SMTPException, RuntimeError) as exc:
            db.conn.rollback()
            error_text = str(exc)[:500] or "email_error"
            try:
                _set_control_value(db, "notification_last_error", error_text)
                db.commit()
            except Exception:
                db.conn.rollback()
            current_app.logger.exception("Failed to send daily notifications.")
            return NotificationResult(False, "email_error", error_text)

        delivered_items = [
            item
            for group in blocks.values()
            for item in group
        ]
        for item in delivered_items:
            db.execute(
                """
                INSERT INTO notificacoes_treinamento (treinamento_id, gatilho)
                VALUES (%s, %s)
                ON CONFLICT (treinamento_id, gatilho) DO NOTHING
                """,
                (item["treinamento_id"], item["gatilho"]),
            )
        _set_control_value(db, "notification_last_sent_at", now_text)
        _set_control_value(db, "notification_last_error", "")
        db.commit()
        return NotificationResult(True, "sent")
