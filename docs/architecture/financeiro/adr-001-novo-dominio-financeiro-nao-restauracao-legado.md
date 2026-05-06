# ADR 001 - Novo dominio Financeiro e nao restauracao de legado

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O repositorio ja teve superficies antigas de Missoes e Produtividade removidas, com testes protegendo contra retorno acidental. O futuro submenu "Missoes" do Financeiro usa a mesma palavra de negocio, mas representa um novo conceito financeiro/operacional, com contratos, endpoints, use cases, repositorios e telas proprios.

O sistema atual expoe a API viva em `/api/v1`, usa Flask no backend e SPA JavaScript puro no frontend. O Financeiro deve se encaixar nesse produto, sem restaurar codigo ou URLs legadas.

## Decisao

O Financeiro sera tratado como novo dominio. O submenu "Missoes" sera criado sob o namespace do Financeiro, com contratos novos, endpoints novos em `/api/v1/financeiro`, testes novos e telas novas em `frontend/src/features/financeiro`.

Nao sera restaurada nenhuma superficie legada de Missoes ou Produtividade. Nomes de arquivos, rotas, permissoes e testes futuros devem deixar explicito que se trata de Financeiro, nao do legado removido.

## Consequencias

- A implementacao futura tera mais trabalho inicial, porque nao podera reaproveitar atalhos legados.
- Os testes que protegem a remocao do legado continuam obrigatorios.
- O novo dominio pode usar conceitos de negocio semelhantes, mas deve nascer com contratos e semantica proprios.
- A palavra "missao" so deve aparecer no novo fluxo quando estiver claramente associada ao Financeiro.

## Regras praticas

- Rotas futuras devem usar `/api/v1/financeiro/...`.
- Contratos futuros devem ficar em `backend/src/controle_treinamentos/contracts/` com nomeacao financeira.
- Use cases futuros devem ficar em `backend/src/controle_treinamentos/application/` com fronteira financeira clara.
- Repositories SQL futuros devem ficar em `backend/src/controle_treinamentos/repositories/` com nomeacao financeira.
- Telas futuras devem ficar em `frontend/src/features/financeiro`.
- Navegacao futura deve ser registrada em `frontend/src/app/route-registry.js` e `frontend/src/shell/navigation.js`, sem reativar entradas legadas.

## O que viola esta decisao

- Recriar endpoints legados fora de `/api/v1/financeiro`.
- Reativar telas antigas de Missoes ou Produtividade.
- Relaxar ou remover testes que impedem retorno do legado.
- Copiar contratos antigos como se fossem contratos financeiros.
- Usar nomes ambiguos que escondam se o fluxo e legado ou Financeiro.
- Recriar tabelas, views ou comandos removidos apenas para acelerar a entrega.

## Impacto na proxima fase

A proxima fase deve comecar por contratos e testes do novo Financeiro. Qualquer proposta de endpoint, permissao, tela ou tabela deve provar que pertence ao namespace financeiro e que nao restaura o legado removido.
