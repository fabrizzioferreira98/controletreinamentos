# Tripulante File

## Papel

Registra a aba File legada de tripulante, ainda viva por rota HTML e jornada E2E.

## Local atual

- `backend/src/controle_treinamentos/blueprints/cadastros/routes_file.py`
- `backend/src/controle_treinamentos/templates/tripulantes_file.html`
- `backend/src/controle_treinamentos/contracts/tripulantes.py`

## Consumidor ou fluxo real

- Rotas `/tripulantes/:id/file`, upload, download, substituicao e exclusao.
- Link `files_legacy` exposto no contrato de tripulantes.
- Jornada E2E de File.

## Motivo de permanencia

O fluxo HTML ainda e suportado e testado. Arquivar agora quebraria compatibilidade operacional.

## Pre-condicao de saida

- Consumidores migrados para `/api/v1/tripulantes/:id/files`.
- Link `files_legacy` removido do contrato.
- Testes E2E migrados para a API/caminho canonico.
