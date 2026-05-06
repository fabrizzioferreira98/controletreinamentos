# Frontend/Backend Separation - Phase 6 (Interactive Reports)

Esta fase extrai os relatórios interativos para contratos `/api/v1`, deixando o frontend responsável por filtros, tabelas e estados de conferência.

## Endpoints entregues

- `GET /api/v1/relatorios/habilitacoes`
- `GET /api/v1/relatorios/produtividade`
- `POST /api/v1/relatorios/produtividade/conferencias`

## O que permanece no backend

- Exportações PDF
- Exportação CSV já existente
- Regras de negócio, auditoria e persistência

## Garantias desta fase

- O payload de habilitações não depende de `status_class`, template ou `url_for`.
- O payload de produtividade expõe filtros, opções e linhas em contrato explícito.
- A ação de conferência usa o usuário autenticado da sessão.
- O frontend novo monta tabelas e filtros sem depender de Jinja.
