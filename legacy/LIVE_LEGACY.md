# Inventario de Legado Vivo

## Objetivo

Registrar legados vivos que justificam a existencia de `legacy/`, sem mover codigo prematuramente.

## Legado vivo identificado

| item | local atual | motivo de permanencia | criterio para mover/remover |
| --- | --- | --- | --- |
| Rotas e templates SSR | `legacy/domains/ssr-html.md` | Ainda existem rotas HTML com `render_template` e contratos/testes de compatibilidade SSR | Extrair apenas quando houver API/frontend substituto, ajustes de imports e testes de rota atualizados |
| Operacoes SSR compat | `legacy/domains/ssr-html.md` | Contratos marcam rotas de missoes/pernoites como `ssr_compat` e testes garantem esse estado | Migrar quando houver consumidor API real para operacoes e as rotas HTML deixarem de ser boundary corrente |
| Aba File legada de tripulante | `legacy/domains/tripulante-file.md` | Rotas HTML `/tripulantes/:id/file` ainda sao suportadas e testadas em jornada E2E | Remover apos consumidores migrarem para `/api/v1/tripulantes/:id/files` |
| Compatibilidade de midia/status de tripulante | `legacy/data-compat/tripulante-media-status.md` | Fotos `foto_base64`, storage refs antigos e status `Ferias` ainda precisam ser lidos/normalizados | Remover apenas apos migracao de dados e testes cobrindo somente formatos canonicos |

## Ratificacao 31.6.1

Esta ratificacao fecha o bloco P1 `31.6.1-legacy-vivo` da Frente 31 sem mover codigo e sem remover fluxo vivo. O objetivo e tornar auditavel o estado atual de cada legado, bloquear feature nova e impedir que `legacy/` seja tratado como backlog removivel generico.

| item | decisao 31.6.1 | evidencia viva | bloqueio explicito | condicao objetiva de saida |
| --- | --- | --- | --- | --- |
| Rotas e templates SSR | manter como legado vivo | `legacy/domains/ssr-html.md`; uso de `render_template`; testes de arquitetura ainda detectam SSR em boundary vivo | feature nova nao nasce em SSR legado; apenas correcao critica, seguranca ou manutencao de compat | API/frontend substituto publicado, rotas HTML fora do boundary corrente, imports/handlers migrados e testes de rota/contrato atualizados |
| Operacoes SSR compat | manter como legado vivo | `legacy/domains/ssr-html.md`; `backend/src/controle_treinamentos/contracts/operacoes.py` marca endpoints como `ssr_compat`; `tests/contract/test_operacoes_contract.py` valida esse estado | nao ampliar superficie SSR de operacoes; novo comportamento nasce em caminho canonico | consumidor API real para operacoes registrado, rotas HTML deixam de ser fronteira corrente e contratos deixam de exigir `ssr_compat` |
| Aba File legada de tripulante | manter como legado vivo | `legacy/domains/tripulante-file.md`; rota `/tripulantes/:id/file`; link `files_legacy`; `tests/e2e/test_critical_journeys.py` exercita File legado | nao criar nova feature na aba File legada; apenas preservar compat ate migracao | consumidores migrados para `/api/v1/tripulantes/:id/files`, link `files_legacy` removido e E2E migrado para caminho canonico |
| Compatibilidade de midia/status de tripulante | manter como compat de dados vivo | `legacy/data-compat/tripulante-media-status.md`; `foto_base64`, `foto_storage_ref`, `db:bytea` e status historico ainda aparecem em codigo/testes de compat | nao criar novo formato legado nem nova escrita em dado historico | migracao de dados comprovada, suite cobrindo apenas formatos canonicos e plano de rollback para dado legado remanescente |

Status do bloco: fechado como ratificacao de permanencia e bloqueio de expansao. Nenhum item acima fica liberado para remocao pela Frente 31 sem etapa propria, evidencia material e teste da camada afetada.

## Fora de legacy estrutural

| item | classificacao correta | motivo |
| --- | --- | --- |
| `scripts/` | compat | Wrappers finos de CLI; nao contem fluxo funcional proprio. |
| `backend/src/controle_treinamentos/compat` | compat | Preserva imports e entrypoints antigos, delegando/adaptando interface. |
| `backend/src/controle_treinamentos/service_layers/domain_validation.py` | compat transitora | Superficie antiga de import; producao ja nao deve depender dela. |
| `backend/src/controle_treinamentos/ui/form_renderers.py` | historico arquivavel ou remocao futura | Placeholder sem API exportada; nao e fluxo vivo. |
| `archive/old-wrappers` | archive | Wrappers mortos ou historicos, sem consumidor vivo. |
| `.tmp` | remocao/archive | Residuos e excecoes temporarias, nao legado vivo. |

## O que nao entra aqui

- `scripts/`: compat de CLI/wrappers historicos, nao legacy.
- `backend/src/controle_treinamentos/compat`: compat explicito de imports/entrypoints, nao legacy.
- `archive/old-wrappers`: wrappers mortos ou historicos, nao legacy vivo.
- `.tmp`: residuos e excecoes temporarias, nao legacy.

## Regra de extracao

Mover codigo para `legacy/` so e permitido quando:

- o import path ou rota publica puder ser preservado por shim;
- testes cobrirem o comportamento antes e depois;
- houver criterio de saida registrado;
- a mudanca nao transformar `legacy/` em segunda raiz do produto.
