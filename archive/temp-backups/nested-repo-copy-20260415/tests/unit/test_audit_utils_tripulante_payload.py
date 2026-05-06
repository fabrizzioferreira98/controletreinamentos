from backend.src.controle_treinamentos.core.audit_utils import tripulante_audit_payload


def test_tripulante_audit_payload_removes_internal_submitted_photo_marker():
    payload = tripulante_audit_payload(
        {
            "nome": "Tripulante QA",
            "submitted_photo": object(),
            "foto_base64": "",
            "foto_storage_ref": "",
        }
    )

    assert "submitted_photo" not in payload


def test_tripulante_audit_payload_converts_photo_state_to_boolean():
    payload = tripulante_audit_payload(
        {
            "foto_base64": "",
            "foto_storage_ref": "fs:tripulantes/1/foto.jpg",
        }
    )

    assert payload["foto_base64"] is True

