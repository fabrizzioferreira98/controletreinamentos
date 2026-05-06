## Checklist de PR

- [ ] Contrato HTTP preservado para rotas alteradas.
- [ ] Se houver rota programática nova/alterada:
  - [ ] Endpoint catalogado em `backend/src/controle_treinamentos/core/http_contract.py`.
  - [ ] View marcada com `@programmatic_json`.
  - [ ] Testes de descoberta/contrato atualizados (`tests/contract/test_http_contract_discovery.py`, `tests/contract/test_http_error_contract.py`).
- [ ] Não há resposta HTML/redirect indevida em chamadas programáticas sem sessão.
- [ ] `pytest -q` executado.

