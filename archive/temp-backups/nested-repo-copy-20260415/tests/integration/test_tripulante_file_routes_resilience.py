from backend.src.controle_treinamentos.blueprints.cadastros import routes_file


def test_detects_training_schema_error_by_table_name():
    exc = RuntimeError('relation "treinamento_anexos_pdf" does not exist')
    assert routes_file._is_training_source_schema_error(exc) is True


def test_detects_training_schema_error_by_missing_column():
    exc = RuntimeError('column tpdf.status does not exist')
    assert routes_file._is_training_source_schema_error(exc) is True


def test_ignores_non_training_schema_error():
    exc = RuntimeError('relation "tripulantes" does not exist')
    assert routes_file._is_training_source_schema_error(exc) is False


def test_training_schema_failure_detector_accepts_runtime_schema_error():
    exc = RuntimeError('column tpdf.status does not exist')
    assert routes_file._is_training_source_schema_failure(exc) is True


def test_training_schema_failure_detector_rejects_runtime_non_schema_error():
    exc = RuntimeError('connection reset by peer while querying banco')
    assert routes_file._is_training_source_schema_failure(exc) is False
