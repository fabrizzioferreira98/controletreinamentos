# Governanca minima da documentacao

## 1. Definicao de doc viva

Doc viva e documento que orienta decisao, operacao, arquitetura, produto ou governanca atual do repositorio.

Regras:

- Deve morar em `docs/architecture`, `docs/operations`, `docs/governance` ou `docs/product`.
- Deve apontar para caminhos, comandos e fluxos oficiais vigentes.
- Deve ser atualizada no mesmo PR/etapa que muda o comportamento documentado.
- Pode referenciar legado, mas nao pode apresentar legado como caminho oficial.

## 2. Definicao de doc de migracao

Doc de migracao e registro de transicao entre modelos, stacks, plataformas ou fases de extracao.

Regras:

- Deve morar em `docs/migration` enquanto a transicao ainda explica contexto necessario.
- Material de plataforma retirada deve morar em `docs/migration/retired-platforms`.
- Nao define operacao oficial, comando oficial ou arquitetura vigente.
- Deve apontar explicitamente para a doc viva correta quando houver risco de confusao.

## 3. Definicao de doc arquivada

Doc arquivada e material preservado por historico, auditoria ou contexto encerrado.

Regras:

- Deve morar em `docs/archive`.
- Nao recebe novas instrucoes operacionais.
- Nao pode ser linkada como fonte de verdade por README, runbook, CI ou release.
- Mudancas permitidas: aviso de arquivo, correcao de link para doc viva ou preservacao historica.

## 4. Regra contra duplicidade concorrente

Nao pode haver duas docs vivas para o mesmo assunto e o mesmo publico.

Regra pratica:

- Um assunto operacional deve ter uma fonte viva primaria em `docs/operations`.
- Um assunto arquitetural deve ter uma fonte viva primaria em `docs/architecture`.
- Um assunto de produto/usuario deve ter uma fonte viva primaria em `docs/product`.
- Um assunto de governanca deve ter uma fonte viva primaria em `docs/governance`.
- Manual antigo relevante deve virar `docs/archive` ou `docs/migration`; nao pode concorrer com manual vivo.
- Indice ou manual unificado so pode ser vivo se nao redefinir comandos, arquitetura ou regra ja definidos em fonte primaria.

## 5. Ownership / atualizacao

Ownership minimo por area:

- `docs/architecture`: dono da mudanca tecnica/arquitetural.
- `docs/operations`: dono da mudanca operacional, release, runbook ou comando.
- `docs/governance`: dono da decisao de estrutura, classificacao ou politica do repo.
- `docs/product`: dono da mudanca funcional visivel ao usuario.
- `docs/migration` e `docs/archive`: dono da etapa que preservou ou aposentou o material.

Regra de review:

- Mudou comando, script oficial, fluxo de deploy, gate, storage, API publica ou comportamento de produto: atualizar a doc viva correspondente.
- Criou ou alterou entrada na raiz: validar `docs/governance/root-entry-policy.md` e atualizar `docs/governance/repo-topology.md` se a topologia mudar.
- Criou doc nova: declarar se ela e viva, migracao ou arquivada pelo diretorio e pelo objetivo.
- Se uma doc nova cobre assunto ja documentado, ela deve substituir, arquivar ou apontar para a fonte primaria; nao pode virar segunda fonte viva.

## 6. Excecoes temporarias

Excecoes aceitas:

- `docs/README.md` e o indice mestre de navegacao. Ele aponta para fontes vivas, mas nao redefine comandos, arquitetura, produto ou governanca.
- `docs/product/README.md` e a entrada viva de produto; `docs/product/manual_usuario_operacional.md` e o manual operacional vivo.
- PDF antigo de produto deve permanecer em `docs/archive/product/`; nao e fonte viva primaria.
- `docs/archive/MANUAL_UNIFICADO.md` e `docs/archive/MANUAL_UNIFICADO_COMPLETO.md` sao indices/manuais antigos arquivados; nao podem concorrer com fontes vivas primarias.
- `docs/operations/REGRESSION_AUDIT_CHECKLIST.md` permanece como template vivo; checklist preenchido de release deve ficar fora do repo com as evidencias ou em `docs/archive/operations/` quando houver valor historico.
- `docs/operations/windows_backup_restore_rollback.md` permanece vivo como fonte de backup, restore e rollback Windows.

## 7. Validacao

Checklist minimo para review:

- A doc esta no diretorio correto para seu status.
- A doc viva nao contradiz `docs/operations/canonical-commands.md`, `docs/governance/repo-topology.md` ou `docs/architecture/ARCHITECTURE.md`.
- Nao ha dois manuais vivos para o mesmo assunto.
- Material historico ou de migracao esta marcado como tal e nao aparece como fonte oficial.
- README, runbooks, CI e release apontam apenas para docs vivas ou para templates operacionais explicitamente aceitos.
