from backend.src.controle_treinamentos.blueprints.admin.routes import _notification_payload_cache_key


def test_notification_payload_cache_key_separates_preview_modes():
    assert _notification_payload_cache_key(preview_enabled=False) != _notification_payload_cache_key(
        preview_enabled=True
    )
