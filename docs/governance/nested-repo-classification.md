# Classificacao da pasta controle-treinamentos

## Objetivo

Este documento registra a natureza da pasta `controle-treinamentos/` que estava localizada dentro da raiz do repositorio. Ela nao e raiz oficial, nao e produto principal e nao pode competir semanticamente com a topologia canonica.

Status 7.3: a ocorrencia que estava na raiz foi movida para `archive/temp-backups/nested-repo-copy-20260415/`. A raiz nao deve voltar a conter uma pasta `controle-treinamentos/` aninhada.

## Investigacao

| evidencia | resultado | conclusao |
| --- | --- | --- |
| Estrutura interna | Continha `.github`, `.tmp`, `.venv`, `.vscode`, `backend`, `docs`, `frontend`, `ops`, `scripts`, `tests` e arquivos de raiz | Reproduz uma arvore de repositorio, nao um componente do produto |
| Controle de versao | Nao contem `.git` nem `.gitmodules` | Nao e submodulo, checkout independente ou espelho Git formal |
| Comparacao de arquivos | Excluindo caches, `.tmp`, `.venv` e builds, a raiz atual tem 390 arquivos comparaveis; a pasta aninhada tem 350; todos os 350 existem na raiz atual | A pasta aninhada e subconjunto/copiar antiga, sem superficie propria |
| Divergencia | 75 arquivos comuns tem conteudo diferente e 40 existem apenas na raiz atual | Nao e espelho sincronizado; esta atrasada em relacao ao produto vivo |
| Referencias operacionais | Nao ha referencia oficial para executar ou importar a pasta aninhada | Sem dependencia operacional real |

## Classificacao

`controle-treinamentos/` era uma copia legada aninhada do repositorio.

Nao e:

- export oficial;
- wrapper;
- espelho operacional;
- build;
- raiz alternativa.

## Decisao

Destino aplicado na etapa 7.3: `archive/temp-backups/nested-repo-copy-20260415/`.

Motivo: a pasta duplica o produto principal, inclui ambiente local e residuos historicos, nao possui dependencia operacional real e nao tem arquivos exclusivos que justifiquem virar nova fonte canonica.

Enquanto existir fisicamente no archive, deve permanecer marcada como backup historico e nao deve receber novos fluxos, correcoes funcionais ou documentacao operacional.

## Trilha de remocao

1. Confirmar que nenhuma automacao local externa apontava para `C:\apps\controle-treinamentos\controle-treinamentos`.
2. Se nao houver necessidade de auditoria, remover `archive/temp-backups/nested-repo-copy-20260415/` em etapa propria.
3. Se houver necessidade de auditoria, substituir a copia completa por manifest ou diff seletivo.

## Regra operacional

Qualquer comando, doc, teste, build ou correcao deve usar a raiz real `C:\apps\controle-treinamentos`, nunca uma copia aninhada ou arquivada.
