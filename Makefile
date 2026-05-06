.PHONY: test cov lint dev clean release-gate-strict

PYTHON ?= .venv/Scripts/python.exe

# Convenience aliases only; official operational commands live in docs/operations/canonical-commands.md.

test:
	$(PYTHON) -m pytest -q

cov:
	$(PYTHON) -m pytest --cov=backend/src/controle_treinamentos --cov-report=html --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check backend/ ops/ tests/

dev:
	$(PYTHON) backend/tools/runtime/run.py

clean:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path . -Recurse -Force -Directory -ErrorAction SilentlyContinue | Where-Object { $$_.Name -in @('__pycache__','.pytest_cache','.ruff_cache','.mypy_cache') -and $$_.FullName -notlike '*\.venv\*' -and $$_.FullName -notlike '*\archive\*' } | Remove-Item -Recurse -Force; Remove-Item -Force -ErrorAction SilentlyContinue .coverage"

release-gate-strict:
	$(PYTHON) ops/scripts/release/run_release_strict.py \
		--base-url "$$BASE_URL" \
		--evidence-manifest "$$EVIDENCE_MANIFEST" \
		--regression-checklist "$$REGRESSION_CHECKLIST" \
		--evidence-max-age-hours "$${EVIDENCE_MAX_AGE_HOURS:-24}"
