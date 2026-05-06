.PHONY: test cov lint dev clean release-gate-strict

test:
	pytest -q

cov:
	pytest --cov=backend/src/controle_treinamentos --cov-report=html --cov-report=term-missing

lint:
	ruff check backend/ ops/ tests/

dev:
	flask run --debug

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage

release-gate-strict:
	.venv/bin/python ops/scripts/release/run_release_strict.py \
		--base-url "$$BASE_URL" \
		--evidence-manifest "$$EVIDENCE_MANIFEST" \
		--regression-checklist "$$REGRESSION_CHECKLIST" \
		--evidence-max-age-hours "$${EVIDENCE_MAX_AGE_HOURS:-24}"
