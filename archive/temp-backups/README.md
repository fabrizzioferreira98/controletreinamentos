# Temp Backups

## Papel

Preserva backups temporarios de arvore ou estrutura que ja foram classificados como historicos.

## Regra

- Nao e trilha de restore oficial.
- Nao e fonte para operacao, build ou desenvolvimento.
- Nao receber snapshots de frontend; esses pertencem a `archive/repo-snapshots`.
- Wrappers antigos sem papel oficial pertencem a `archive/old-wrappers`.
- Quando um backup contiver uma arvore inteira, a classificacao vale para o container, nao para transformar seus subdiretorios em areas vivas.

## Conteudo classificado

- `nested-repo-copy-20260415/`: copia legada aninhada movida da raiz na etapa 7.3. Nao e raiz alternativa, backup de restore ou fonte viva; o conteudo misto interno permanece encapsulado como backup temporario.
- `root-wrapper-docs-backup-20260408-1635/`: backup temporario de wrappers/docs de raiz. Nao e trilha operacional.
- `src-app-backup-20260408-154654/`: backup temporario de arvore de app. Nao e codigo vivo.
- `src-app-__init__-backup-20260408-1610.py`: backup temporario de arquivo de inicializacao. Nao e compat nem wrapper oficial.
