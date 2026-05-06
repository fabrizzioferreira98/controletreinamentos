from datetime import date

from flask import Flask

from backend.src.controle_treinamentos.infra import mailer


def test_build_notification_blocks_does_not_require_tripulante_email(monkeypatch):
    monkeypatch.setattr(mailer, "business_today", lambda: date(2026, 3, 23))
    monkeypatch.setattr(mailer, "fetch_sent_notification_map", lambda _ids: {})

    rows = [
        {
            "treinamento_id": 1,
            "data_vencimento": "2026-03-31",
            "tripulante_nome": "Tripulante Sem Email",
            "tripulante_email": "",
            "equipamento_nome": "B200",
            "tipo_treinamento_nome": "CQ IFR",
        }
    ]

    blocks = mailer.build_notification_blocks(rows)
    assert len(blocks["em_30_dias"]) == 1
    assert blocks["em_30_dias"][0]["treinamento_id"] == 1


def test_build_notification_blocks_skips_already_notified_trigger(monkeypatch):
    monkeypatch.setattr(mailer, "business_today", lambda: date(2026, 3, 23))
    monkeypatch.setattr(mailer, "fetch_sent_notification_map", lambda _ids: {1: {"30"}})

    rows = [
        {
            "treinamento_id": 1,
            "data_vencimento": "2026-03-31",
            "tripulante_nome": "Tripulante",
            "tripulante_email": "x@x.com",
            "equipamento_nome": "B200",
            "tipo_treinamento_nome": "CQ IFR",
        }
    ]

    blocks = mailer.build_notification_blocks(rows)
    assert len(blocks["em_30_dias"]) == 0


def test_build_notification_blocks_can_include_already_sent(monkeypatch):
    monkeypatch.setattr(mailer, "business_today", lambda: date(2026, 3, 23))
    monkeypatch.setattr(mailer, "fetch_sent_notification_map", lambda _ids: {1: {"30"}})

    rows = [
        {
            "treinamento_id": 1,
            "data_vencimento": "2026-03-31",
            "tripulante_nome": "Tripulante",
            "tripulante_email": "x@x.com",
            "equipamento_nome": "B200",
            "tipo_treinamento_nome": "CQ IFR",
        }
    ]

    blocks = mailer.build_notification_blocks(rows, include_already_sent=True)
    assert len(blocks["em_30_dias"]) == 1


def test_get_smtp_config_uses_safe_port_fallback(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "porta-invalida")
    config = mailer.get_smtp_config()
    assert config["port"] == 587

    monkeypatch.setenv("SMTP_PORT", "0")
    config = mailer.get_smtp_config()
    assert config["port"] == 1


def test_get_smtp_config_supports_aliases_and_ssl_defaults(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_SENDER", raising=False)
    monkeypatch.delenv("SMTP_USE_SSL", raising=False)
    monkeypatch.delenv("SMTP_USE_TLS", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "alias-user@example.com")
    monkeypatch.setenv("SMTP_PASS", "alias-secret")
    monkeypatch.setenv("MAIL_SERVER", "smtp.alias.example.com")
    monkeypatch.setenv("MAIL_DEFAULT_SENDER", "noreply@example.com")
    monkeypatch.setenv("SMTP_PORT", "465")

    config = mailer.get_smtp_config()

    assert config["host"] == "smtp.alias.example.com"
    assert config["user"] == "alias-user@example.com"
    assert config["password"] == "alias-secret"
    assert config["sender"] == "noreply@example.com"
    assert config["use_ssl"] is True
    assert config["use_tls"] is False


def test_validate_notification_dispatch_readiness_for_smtp(monkeypatch):
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com"])
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    payload = mailer.validate_notification_dispatch_readiness()
    assert payload["recipients_count"] == 1
    assert payload["provider"] == "smtp"
    assert payload["email_ready"] is True


def test_validate_notification_dispatch_readiness_reports_missing_smtp_fields(monkeypatch):
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com"])
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    payload = mailer.validate_notification_dispatch_readiness()

    assert payload["email_ready"] is False
    assert sorted(payload["missing_config_fields"]) == ["SMTP_HOST", "SMTP_PASSWORD", "SMTP_USER"]


def test_validate_notification_dispatch_readiness_for_resend(monkeypatch):
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com", "qa@example.com"])
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM", "noreply@example.com")

    payload = mailer.validate_notification_dispatch_readiness()
    assert payload["recipients_count"] == 2
    assert payload["provider"] == "resend"
    assert payload["email_ready"] is True


def test_validate_notification_dispatch_readiness_reports_missing_resend_fields(monkeypatch):
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com"])
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)

    payload = mailer.validate_notification_dispatch_readiness()

    assert payload["email_ready"] is False
    assert sorted(payload["missing_config_fields"]) == ["RESEND_API_KEY", "RESEND_FROM"]


def test_send_test_email_returns_no_recipients(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: [])

    result = mailer.send_test_email(app, requested_by="QA")

    assert result.sent is False
    assert result.reason == "no_recipients"


def test_send_test_email_reports_missing_smtp_config(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com"])
    monkeypatch.setattr(mailer, "get_email_provider", lambda: "smtp")
    monkeypatch.setattr(
        mailer,
        "get_smtp_config",
        lambda: {
            "host": "",
            "port": 587,
            "user": "",
            "password": "",
            "sender": "noreply@example.com",
            "use_ssl": False,
            "use_tls": True,
        },
    )

    result = mailer.send_test_email(app, requested_by="QA")

    assert result.sent is False
    assert result.reason == "smtp_not_configured"
    assert "SMTP_HOST" in (result.error or "")
    assert "SMTP_USER" in (result.error or "")
    assert "SMTP_PASSWORD" in (result.error or "")


def test_send_test_email_dispatches_via_smtp(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com"])
    monkeypatch.setattr(mailer, "get_email_provider", lambda: "smtp")
    monkeypatch.setattr(
        mailer,
        "get_smtp_config",
        lambda: {
            "host": "smtp.example.com",
            "port": 587,
            "user": "user@example.com",
            "password": "secret",
            "sender": "noreply@example.com",
            "use_ssl": False,
            "use_tls": True,
        },
    )
    smtp_events = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            smtp_events["host"] = host
            smtp_events["port"] = port
            smtp_events["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            smtp_events["starttls"] = True

        def login(self, user, password):
            smtp_events["login"] = (user, password)

        def sendmail(self, sender, recipients, message):
            smtp_events["sendmail"] = (sender, recipients, message)

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    result = mailer.send_test_email(app, requested_by="QA")

    assert result.sent is True
    assert result.reason == "sent"
    assert smtp_events["host"] == "smtp.example.com"
    assert smtp_events["port"] == 587
    assert smtp_events["starttls"] is True
    assert smtp_events["login"] == ("user@example.com", "secret")
    sender, recipients, message = smtp_events["sendmail"]
    assert sender == "noreply@example.com"
    assert recipients == ["ops@example.com"]
    assert "Teste de e-mail - Controle de Treinamentos" in message


def test_send_test_email_dispatches_via_resend(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(mailer, "get_active_recipients", lambda: ["ops@example.com"])
    monkeypatch.setattr(mailer, "get_email_provider", lambda: "resend")
    captured = {}

    def _fake_send_with_resend(*, subject, body, recipients):
        captured["subject"] = subject
        captured["body"] = body
        captured["recipients"] = recipients

    monkeypatch.setattr(mailer, "send_with_resend", _fake_send_with_resend)

    result = mailer.send_test_email(app, requested_by="QA")

    assert result.sent is True
    assert result.reason == "sent"
    assert captured["recipients"] == ["ops@example.com"]
    assert captured["subject"] == "Teste de e-mail - Controle de Treinamentos"


class _FakeCursor:
    def fetchall(self):
        return []

    def fetchone(self):
        return {}


class _FakeDb:
    def __init__(self):
        self.conn = self
        self.executed: list[tuple[str, tuple | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, query, params=None):
        self.executed.append((" ".join(query.split()), params))
        return _FakeCursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_send_daily_notifications_dispatches_and_records(monkeypatch):
    app = Flask(__name__)
    fake_db = _FakeDb()
    monkeypatch.setattr(mailer, "get_db", lambda: fake_db)
    monkeypatch.setattr(
        mailer,
        "generate_notification_payload",
        lambda include_diagnostics=False: {
            "recipients": ["ops@example.com"],
            "blocks": {
                "vencidos": [{"treinamento_id": 101, "gatilho": "vencido"}],
                "em_30_dias": [],
                "em_60_dias": [],
                "em_90_dias": [],
            },
        },
    )
    monkeypatch.setattr(mailer, "get_email_provider", lambda: "smtp")
    monkeypatch.setattr(mailer, "render_email_body", lambda blocks: "body")
    sent_payload = {}

    def _fake_send_with_smtp(*, subject, body, recipients):
        sent_payload["subject"] = subject
        sent_payload["body"] = body
        sent_payload["recipients"] = recipients

    monkeypatch.setattr(mailer, "_send_with_smtp", _fake_send_with_smtp)

    result = mailer.send_daily_notifications(app)

    assert result.sent is True
    assert result.reason == "sent"
    assert sent_payload["subject"] == "Controle diário de treinamentos"
    assert sent_payload["body"] == "body"
    assert sent_payload["recipients"] == ["ops@example.com"]
    assert any("INSERT INTO notificacoes_treinamento" in query for query, _params in fake_db.executed)
    assert fake_db.commits >= 2


def test_send_daily_notifications_returns_smtp_not_configured(monkeypatch):
    app = Flask(__name__)
    fake_db = _FakeDb()
    monkeypatch.setattr(mailer, "get_db", lambda: fake_db)
    monkeypatch.setattr(
        mailer,
        "generate_notification_payload",
        lambda include_diagnostics=False: {
            "recipients": ["ops@example.com"],
            "blocks": {
                "vencidos": [{"treinamento_id": 201, "gatilho": "vencido"}],
                "em_30_dias": [],
                "em_60_dias": [],
                "em_90_dias": [],
            },
        },
    )
    monkeypatch.setattr(mailer, "get_email_provider", lambda: "smtp")
    monkeypatch.setattr(mailer, "render_email_body", lambda blocks: "body")

    def _raise_smtp_not_configured(*, subject, body, recipients):
        raise RuntimeError("smtp_not_configured:SMTP_HOST,SMTP_USER,SMTP_PASSWORD")

    monkeypatch.setattr(mailer, "_send_with_smtp", _raise_smtp_not_configured)

    result = mailer.send_daily_notifications(app)

    assert result.sent is False
    assert result.reason == "smtp_not_configured"
    assert "Configuração SMTP incompleta" in (result.error or "")
    assert fake_db.rollbacks == 0
