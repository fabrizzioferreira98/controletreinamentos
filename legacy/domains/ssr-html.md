# SSR HTML

## Papel

Registra rotas e templates server-side ainda vivos no Flask. O desenho futuro e API/frontend desacoplado, mas estas rotas ainda participam de comportamento testado.

## Local atual

- `backend/src/controle_treinamentos/blueprints`
- `backend/src/controle_treinamentos/templates`
- `backend/src/controle_treinamentos/contracts/operacoes.py`

## Consumidor ou fluxo real

- Rotas HTML de dominios como missoes e pernoites.
- Testes de contrato que confirmam endpoints `ssr_compat`.
- Templates usados por `render_template`.

## Motivo de permanencia

Ainda nao ha consumidor API real registrado para todos os fluxos cobertos. Remover ou arquivar agora quebraria rotas HTML e contratos.

## Pre-condicao de saida

- API/frontend substituto publicado para o fluxo.
- Rotas HTML deixam de ser boundary corrente.
- Imports e handlers atualizados.
- Testes de rota e contrato migrados para o caminho canonico.
