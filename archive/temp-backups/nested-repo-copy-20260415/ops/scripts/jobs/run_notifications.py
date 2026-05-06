from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.mailer import generate_notification_payload, send_daily_notifications


def main() -> int:
    try:
        app = create_app()
        with app.app_context():
            payload = generate_notification_payload()

            if not payload["recipients"]:
                print("No active email recipients configured.")
                return 1

            if payload["total_items"] == 0:
                print("No due trainings to notify today.")
                return 0

            if not payload.get("email_ready"):
                provider = (payload.get("provider") or "").strip().lower()
                missing = payload.get("missing_config_fields") or []
                missing_hint = f" Missing: {', '.join(missing)}." if missing else ""
                if provider == "resend":
                    print(f"Resend configuration is incomplete.{missing_hint}")
                else:
                    print(f"SMTP configuration is incomplete.{missing_hint}")
                return 1

        result = send_daily_notifications(app)
        if result.sent:
            print("Daily notifications sent successfully.")
            return 0

        if result.error:
            print(f"Daily notifications were not sent. Reason: {result.reason}. Error: {result.error}")
        else:
            print(f"Daily notifications were not sent. Reason: {result.reason}")
        return 0 if result.reason == "no_due_items" else 1
    except RuntimeError as exc:
        print(f"Unable to run notifications job: {exc}")
        return 1
    except Exception as exc:
        print(f"Unexpected notifications runner failure: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
