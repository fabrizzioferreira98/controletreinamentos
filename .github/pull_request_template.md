## Checklist de PR

- [ ] A mudanca respeita `docs/governance/repository-governance.md`.
- [ ] Nenhum caminho novo parece entrada principal sem estar em `docs/operations/canonical-commands.md`.
- [ ] Se houve compat/legacy: owner, sinalizacao, destino canonico e condicao de saida foram registrados.
- [ ] Se houve breaking estrutural: o PR declara `BREAKING STRUCTURE`, inclui caminho antigo/novo, plano de compat ou prova de ausencia de consumidor, rollback e aceite dos owners.
- [ ] Contrato HTTP preservado para rotas alteradas.
- [ ] Se houver rota programática nova/alterada:
  - [ ] Endpoint catalogado em `backend/src/controle_treinamentos/core/http_contract.py`.
  - [ ] View marcada com `@programmatic_json`.
  - [ ] Testes de descoberta/contrato atualizados (`tests/contract/test_http_contract_discovery.py`, `tests/contract/test_http_error_contract.py`).
- [ ] Não há resposta HTML/redirect indevida em chamadas programáticas sem sessão.
- [ ] `pytest -q` executado.
