from datetime import date

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
