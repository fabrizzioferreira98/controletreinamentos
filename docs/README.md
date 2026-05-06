# Documentacao

## Visao geral

Este indice e a porta de entrada para a documentacao do repositorio. Ele aponta para fontes vivas e para areas historicas sem transformar material arquivado em guia oficial.

O `README.md` da raiz resume o produto e os comandos principais. Este arquivo organiza onde procurar cada assunto dentro de `docs/`.

## Areas principais

| area | papel |
| --- | --- |
| `architecture/` | Arquitetura vigente, storage e decisoes tecnicas vivas. |
| `operations/` | Comandos, runbooks, release, smoke, backup, observabilidade e operacao Windows/self-hosted. |
| `product/` | Manual operacional vivo de produto e entrada para usuario. |
| `governance/` | Topologia do repo, politicas de raiz, docs, legacy, archive e classificacoes estruturais. |
| `migration/retired-platforms/` | Plataformas e modelos retirados; nao e guia de deploy atual. |
| `archive/` | Historico, auditorias encerradas, manuais antigos e relatorios arquivados. |

## Docs oficiais por assunto

| assunto | fonte oficial |
| --- | --- |
| Topologia da raiz e excecoes locais explicitas | `docs/governance/repo-topology.md` |
| Governanca formal do repositorio | `docs/governance/repository-governance.md` |
| Entrada de novos itens na raiz | `docs/governance/root-entry-policy.md` |
| Governanca de documentacao | `docs/governance/documentation-governance.md` |
| Convencoes tecnicas do repositorio | `docs/governance/technical-conventions.md` |
| Compat, legacy, archive e remocao | `docs/governance/legacy-policy.md` |
| Backlog de remocao futura | `docs/governance/removal-backlog.md` |
| Classificacao da antiga `.tmp` | `docs/governance/tmp-classification.md` |
| Classificacao da copia aninhada | `docs/governance/nested-repo-classification.md` |
| Arquitetura do sistema | `docs/architecture/ARCHITECTURE.md` |
| Arquitetura e convencoes do frontend | `docs/architecture/FRONTEND_ARCHITECTURE.md` |
| Camada documental: storage, arquivos e PDFs | `docs/architecture/DOCUMENT_LAYER_POLICY.md` |
| Storage documental historico/especifico | `docs/architecture/DOCUMENT_STORAGE_POLICY.md` |
| Persistencia de blobs/metadata | `docs/architecture/FILE_PERSISTENCE_POLICY.md` |
| Acesso binario, preview e download | `docs/architecture/FILE_ACCESS_POLICY.md` |
| Politica de upload | `docs/architecture/UPLOAD_POLICY.md` |
| Politica de PDFs/documentos | `docs/architecture/PDF_DOCUMENT_POLICY.md` |
| Riscos classicos de arquivos e PDFs | `docs/architecture/FILE_CLASSIC_RISKS.md` |
| Nomeacao de storage | `docs/architecture/STORAGE_NAMING_POLICY.md` |
| Comandos oficiais | `docs/operations/canonical-commands.md` |
| Bootstrap local real | `docs/operations/LOCAL_RUNTIME.md` |
| Paridade minima entre ambientes | `docs/operations/ENVIRONMENT_PARITY.md` |
| Pipeline minima de CI/release | `docs/operations/CI_RELEASE_PIPELINE.md` |
| Evolucao de banco e classificacao de mudancas | `docs/operations/DATABASE_EVOLUTION.md` |
| Release management e fluxo oficial | `docs/operations/RELEASE_MANAGEMENT.md` |
| Checklist operacional de release | `docs/operations/RELEASE_EXECUTION_CHECKLIST.md` |
| Checklist operacional de rollback | `docs/operations/ROLLBACK_CHECKLIST.md` |
| Validacao pos-release | `docs/operations/POST_RELEASE_VALIDATION.md` |
| Mapa docs/execucao operacional | `docs/operations/README.md` |
| Mapa da camada operacional | `ops/README.md` |
| Runbook operacional | `docs/operations/RUNBOOK.md` |
| Servidor Windows/self-hosted | `docs/operations/WINDOWS_SELF_HOSTED_SERVER.md` |
| Backup, restore e rollback | `docs/operations/windows_backup_restore_rollback.md` |
| Gates de release | `docs/operations/RELEASE_GATES.md` |
| Checklist de regressao | `docs/operations/REGRESSION_AUDIT_CHECKLIST.md` |
| Evidencias de release | `docs/operations/RELEASE_EVIDENCE_TEMPLATE.json` |
| Observabilidade e SLOs | `docs/operations/OBSERVABILITY.md` e `docs/operations/SLOS.md` |
| Estrategia de protecao de testes | `docs/operations/TEST_PROTECTION_STRATEGY.md` |
| Frente 26 de seguranca ainda vigente | `docs/operations/SECURITY_FRONT_26.md` |
| Usuarios de teste | `docs/operations/AUTH_TEST_USERS.md` |
| Manual de produto | `docs/product/manual_usuario_operacional.md` |
| Plataformas retiradas | `docs/migration/retired-platforms/README.md` |
| Documentacao historica | `docs/archive/README.md` |

## Regra de uso

- Use este indice para encontrar a fonte viva; nao use docs arquivadas como instrucao operacional.
- Se um assunto tiver duas fontes vivas concorrentes, consolide antes de criar outra doc.
- Docs novas devem entrar na area correta e respeitar `docs/governance/documentation-governance.md`.
