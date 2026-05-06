from backend.src.controle_treinamentos.core.http_utils import safe_next_url


def test_safe_next_url_accepts_local_paths_with_query_string():
    assert safe_next_url("/dashboard?page=2", "/fallback") == "/dashboard?page=2"


def test_safe_next_url_rejects_external_or_ambiguous_redirect_targets():
    fallback = "/dashboard"

    assert safe_next_url("https://evil.example/login", fallback) == fallback
    assert safe_next_url("//evil.example/login", fallback) == fallback
    assert safe_next_url("/\\evil.example/login", fallback) == fallback
    assert safe_next_url("/%5Cevil.example/login", fallback) == fallback
    assert safe_next_url("/%2f%2fevil.example/login", fallback) == fallback
    assert safe_next_url("/dashboard%0d%0aLocation:%20https://evil.example", fallback) == fallback
