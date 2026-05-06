from backend.src.controle_treinamentos.audit import normalize_audit_payload


def test_normalize_audit_payload_redacts_sensitive_fields():
    payload = {
        "nome": "Ana Silva",
        "cpf": "123.456.789-01",
        "email": "ana.silva@empresa.com",
        "telefone": "+55 (11) 99999-2222",
        "senha_hash": "pbkdf2:hash-super-secreto",
        "meta": {
            "token_acesso": "token-abc-123",
            "observacao": "x" * 900,
        },
        "foto_base64": "base64:conteudo-foto",
    }

    normalized = normalize_audit_payload(payload)

    assert normalized["nome"] == "Ana Silva"
    assert normalized["cpf"] == "***.456.***-**"
    assert normalized["email"] == "a***@empresa.com"
    assert normalized["telefone"] == "***2222"
    assert normalized["senha_hash"] == "<redacted>"
    assert normalized["meta"]["token_acesso"] == "<redacted>"
    assert normalized["meta"]["observacao"].endswith("[truncated]")
    assert normalized["foto_base64"] == "<redacted>"


def test_normalize_audit_payload_handles_binary_payloads():
    payload = {
        "arquivo_bruto": b"\x00\x01\x02\x03",
        "descricao": "ok",
    }

    normalized = normalize_audit_payload(payload)

    assert normalized["arquivo_bruto"] == "<redacted>"
    assert normalized["descricao"] == "ok"
