# Compat

## Papel

Este pacote preserva imports e entrypoints antigos que ainda precisam coexistir com a estrutura atual.

## Regra

- Codigo novo nao deve nascer aqui.
- Compat deve delegar para o caminho canonico ou adaptar interface antiga.
- Cada permanencia deve ter consumidor ou motivo de transicao.
- Quando o consumidor historico sair, o compat deve ser aposentado em etapa propria.
