# Guardrails de Contrato HTTP

## Objetivo
Garantir que rotas programáticas nunca regressem para HTML/redirect e mantenham contrato JSON estável.

## Regra de engenharia (obrigatória em PR)
Quando adicionar/alterar rota consumida por front programático (Ajax/fetch) ou integração:
1. Registrar endpoint em `backend/src/controle_treinamentos/core/http_contract.py` (`PROGRAMMATIC_JSON_ENDPOINTS`).
2. Marcar a view com `@programmatic_json`.
3. Atualizar/cobrir testes:
   - `tests/test_http_contract_discovery.py`
   - `tests/test_http_error_contract.py`

Sem esses itens, PR deve ser bloqueado.

## Contrato mínimo obrigatório para rotas programáticas
- resposta sempre JSON (inclusive 401/403/400/409/422/404/500/CSRF).
- nunca redirect HTML em sessão expirada/autenticação ausente/permissão negada.
- payload mínimo:
  - `success` (bool)
  - `status` (int)
  - `message` (str)
  - `code` (str, quando aplicável)
  - `request_id` (str | null)

## Mecanismo anti-drift
- catálogo central: `backend/src/controle_treinamentos/core/http_contract.py`
- validação de descoberta: `tests/test_http_contract_discovery.py`
- validação funcional de erro/autenticação: `tests/test_http_error_contract.py`
