# Legacy

## Papel

Esta area existe porque ha legado vivo no produto: fluxos ainda usados ou testados, mas que nao sao a fonte canonica futura.

## Regra

- Nao mover codigo para ca sem confirmar imports, testes, jobs, workflows e runbooks.
- Legacy pode receber correcao critica ou de seguranca, mas nao feature nova.
- Se o item apenas delega para o caminho canonico, ele e compat, nao legacy.
- Se o item nao tem uso real, ele deve ir para archive ou exclusao futura, nao para legacy.
- Cada item movido para ca deve ter consumidor conhecido, motivo de permanencia e criterio de saida.

## Estado atual

Nenhum codigo executavel foi movido para `legacy/` nesta etapa. Os legados vivos identificados ainda estao acoplados ao pacote Flask, templates, rotas, dados historicos ou contratos testados; mover agora quebraria compatibilidade.

## Estrutura

- `LIVE_LEGACY.md` - indice dos legados vivos e suas condicoes de saida.
- `domains/` - fluxos de produto ainda vivos, mas fora do desenho canonico futuro.
- `data-compat/` - compatibilidade com dados antigos que ainda precisam ser lidos.

A politica geral para decidir entre compat, legacy, archive e remocao fica em `docs/governance/legacy-policy.md`.
