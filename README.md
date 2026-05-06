# Controle de Treinamentos

Aplicacao web interna para controle de tripulantes, treinamentos, vencimentos e operacao de bases.

## Modelo oficial

O produto opera em servidor local / self-hosted Windows:

- backend Flask executado por Waitress
- frontend estatico separado servido por Caddy
- PostgreSQL nativo no host local
- storage de fotos, PDFs e anexos em filesystem local
- jobs, backups e rotinas operacionais no proprio servidor

Fluxos cloud/serverless antigos nao fazem parte da operacao oficial.

## Entrada oficial

| area | entrada oficial | quando usar |
| --- | --- | --- |
| backend local | `.venv\Scripts\python.exe backend\tools\runtime\run.py` | desenvolvimento local hibrido/compat na mesma origem |
| app Windows/self-hosted | `powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-AppService.ps1 -EnvironmentName <env> -EnvFile <env-file>` | operacao real com Waitress |
| frontend build | `.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example` | gerar `frontend\dist`; nao sobe servidor estatico |
| worker | `.venv\Scripts\python.exe backend\tools\maintenance\run_jobs_worker.py` | processar fila de jobs |
| rotinas Windows | `ops\windows\scripts\Invoke-OperationalPython.ps1` via Task Scheduler | worker, backup e consistencia recorrentes no host |

Wrappers em `scripts\` e chamadas diretas em `ops\scripts\...` nao sao entrada principal. Quando existirem, sao compatibilidade ou implementacao chamada pela trilha canonica.

## Bootstrap local curto

Esta e a rota minima para subir o sistema em desenvolvimento sem improvisar caminhos principais. O detalhamento completo fica em [docs/operations/LOCAL_RUNTIME.md](docs/operations/LOCAL_RUNTIME.md).

1. Criar ambiente Python e instalar dependencias:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

2. Criar `.env` a partir de `.env.example` e configurar pelo menos `SECRET_KEY`, `DATABASE_URL`, `APP_ENV` e `PORT`.
3. Garantir PostgreSQL real acessivel pelo `DATABASE_URL`; o repo nao provisiona o servidor de banco.
4. Definir storage gravavel com `MEDIA_STORAGE_ROOT` ou `APP_INSTANCE_PATH`. Para backup real local, definir tambem `WORKSPACE_LOCAL_BACKUPS_ROOT` ou `BACKUP_DIR`.
5. Aplicar schema e indices:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\bootstrap_db_schema.py
```

6. Aplicar massa minima/defaults:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\bootstrap_seed_data.py
```

7. Criar usuario admin se `BOOTSTRAP_ADMIN_*` nao foi usado:

```powershell
.venv\Scripts\python.exe ops\scripts\admin\ensure_admin_user.py --login admin_local --password <senha-forte> --email admin@local
```

8. Subir backend local:

```powershell
.venv\Scripts\python.exe backend\tools\runtime\run.py
```

9. Em outro terminal, subir o worker:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_jobs_worker.py
```

10. Scheduler local: nao existe daemon local canonico. Para simular rotinas, execute manualmente os comandos de notificacao, backup e consistencia. Em Windows/self-hosted, o scheduler oficial e o Task Scheduler chamando `ops\windows\scripts\Invoke-OperationalPython.ps1`.

11. Frontend separado: por padrao local, mantenha `FRONTEND_*` vazio e use a trilha backend hibrida. Para validar o frontend estatico separado, rode o build e sirva `frontend\dist` por servidor HTTP externo:

```powershell
.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example
```

## Topologia oficial

| entrada | papel |
| --- | --- |
| `.github/` | CI, release e governanca automatizada |
| `backend/` | backend Flask, runtime local e ferramentas de manutencao |
| `frontend/` | frontend oficial separado, fontes e build |
| `ops/` | operacao oficial, Windows self-hosted, release, smoke e drills |
| `tests/` | suites oficiais de validacao |
| `docs/` | documentacao viva, migracao e archive governados |
| `scripts/` | aliases historicos de compatibilidade; nao receber novos fluxos |
| `archive/` | artefatos historicos fora da operacao viva |
| `legacy/` | area de legado vivo real, fora do nucleo canonico |

Fonte completa: [docs/governance/repo-topology.md](docs/governance/repo-topology.md). Governanca formal: [docs/governance/repository-governance.md](docs/governance/repository-governance.md). Politica de entrada na raiz: [docs/governance/root-entry-policy.md](docs/governance/root-entry-policy.md).

## Comandos oficiais

Use [docs/operations/canonical-commands.md](docs/operations/canonical-commands.md) como fonte curta de comandos por tarefa critica.

| tarefa | entrada curta |
| --- | --- |
| subir backend local | `backend\tools\runtime\run.py` |
| subir app Windows/self-hosted | `ops\windows\scripts\Invoke-AppService.ps1` |
| build frontend | `frontend\scripts\build_frontend.py` |
| bootstrap estrutural de banco | `backend\tools\maintenance\bootstrap_db_schema.py` |
| seed minima | `backend\tools\maintenance\bootstrap_seed_data.py` |
| worker | `backend\tools\maintenance\run_jobs_worker.py` |
| backup | `backend\tools\maintenance\run_backups.py` |
| notificacoes manuais | `backend\tools\maintenance\run_notifications.py` |
| scheduler Windows/self-hosted | `ops\windows\scripts\Install-WindowsScheduledTasks.ps1` |
| consistencia de banco | `backend\tools\maintenance\run_db_consistency.py` |
| smoke pos-deploy | `ops\scripts\smoke\post_deploy_smoke.py` |
| release gate | `ops\scripts\release\run_release_strict.py` |

Bootstrap estrutural e consistencia/reparo nao sao a mesma trilha: o primeiro sobe apenas schema e indices, enquanto `--repair` fica restrito a reparo manual.

## Documentacao viva

Indice mestre da documentacao: [docs/README.md](docs/README.md).

Registro da correcao segura do preview PDF da aba Tripulantes: `docs\migration\37.tripulante-pdf-preview-seguro-honesto.md`.
Registro da correcao causal do upload de foto da aba Tripulantes: `docs\migration\38.tripulante-photo-upload-feedback-causal.md`.
Registro do hotfix de encoding/mojibake da aba Tripulantes: `docs\migration\39.tripulante-encoding-mojibake-hotfix.md`.
Registro do refino de microcopy operacional da aba Tripulantes: `docs\migration\40.tripulante-microcopy-operacional-refino.md`.
Registro do refinamento visual amplo da aba Tripulantes: `docs\migration\41.tripulante-refinamento-visual-amplo.md`.
Registro da auditoria ACL-constrained dos PDFs legados da aba Tripulantes: `docs\migration\42.tripulante-pdfs-legado-acl-forensics.md`.
Registro da tentativa de recuperacao LocalSystem dos PDFs legados da aba Tripulantes: `docs\migration\43.tripulante-pdfs-legado-recuperacao-system.md`.
Registro do hardening de publicacao espelhada do frontend SPA: `docs\migration\44.frontend-publish-mirror-guard.md`.
Registro do dry-run de limpeza total dos PDFs de tripulantes: `docs\migration\45.tripulante-pdf-cleanup-dry-run.md`.
Registro da limpeza total aplicada dos PDFs de tripulantes: `docs\migration\46.tripulante-pdf-cleanup-apply.md`.
Registro da remocao da coluna Evidencia no consolidado de habilitacoes: `docs\migration\47.habilitacoes-remove-evidencia-inline.md`.
Registro da remocao residual de Evidencia e cache dos assets no consolidado de habilitacoes: `docs\migration\48.habilitacoes-remove-evidencia-residual-cache.md`.
Registro da correcao focal de consistencia entre lancamento, calculo e exibicao da aba Jornadas: `docs\migration\49.jornadas-calculo-persistencia-consistencia.md`.
Registro da correcao local de UX e fluxo operacional da aba Jornadas: `docs\migration\50.jornadas-ux-fluxo-operacional.md`.
Registro da correcao focal de integridade de persistencia da aba Jornadas: `docs\migration\51.jornadas-integridade-persistencia.md`.
Registro da calibracao responsiva da aba Jornadas: `docs\migration\52.jornadas-responsividade-breakpoints.md`.
Registro da correcao do PDF operacional proprio da aba Jornadas: `docs\migration\53.jornadas-pdf-operacional-proprio.md`.
Registro do hardening estrutural de assets/publicacao frontend (fingerprint + swap atomico + cache split): `docs\migration\54.frontend-asset-fingerprint-atomic-publish-cache-contract.md`.
Registro do hardening de first paint da dashboard para sparkline SVG seguro sem dependencia de CSS tardio: `docs\migration\55.dashboard-first-paint-sparkline-svg-inline-safety.md`.
Registro do redesign visual local da aba Jornadas: `docs\migration\56.jornadas-redesign-visual-local.md`.
Registro do refino de Table UX da grade de lancamentos de Jornadas: `docs\migration\57.jornadas-grade-lancamentos-table-ux.md`.
Registro da calibracao responsiva pos-redesign da aba Jornadas e confirmacao do build vivo com assets fingerprintados: `docs\migration\58.jornadas-responsividade-pos-redesign.md`.
Registro do fechamento do grafo de assets frontend para cold load/publicacao atomica sem JS/CSS orfaos: `docs\migration\59.frontend-asset-graph-closed-publish-contract.md`.
Registro do hardening de navegacao para remover dashboard/home como fallback indevido da SPA: `docs\migration\77.frontend-navigation-dashboard-fallback-integrity.md`.
Registro da protecao de estado critico frontend contra perda de rascunho e edicao em andamento: `docs\migration\78.frontend-state-integrity-critical-drafts.md`.
Registro do hardening de write model operacional para centralizar a escrita entre Missoes SSR e Jornadas SPA/API: `docs\migration\79.operacoes-write-model-centralizado.md`.
Registro da migracao incremental da experiencia principal de Missoes com jornada e pernoite por tripulante: `docs\migration\80.missoes-fluxo-operacional-jornada-pernoite.md`.
Registro do rebaixamento de Jornadas para read model de auditoria operacional: `docs\migration\81.jornadas-read-model-auditoria.md`.
Registro do reapontamento de relatorios e PDFs para read models canonicos: `docs\migration\82.relatorios-pdfs-read-model-canonico.md`.
Registro do cutover controlado de Pernoites para compat operacional: `docs\migration\83.cutover-pernoites-navegacao-compat.md`.
Registro da remocao frontend de Painel TV e Produtividade: `docs\migration\84.frontend-remove-painel-tv-produtividade-superficies.md`.
Registro da remocao backend de Painel TV e Produtividade: `docs\migration\85.backend-remove-painel-tv-produtividade.md`.
Registro da limpeza de reporting, PDFs, exports, calculos, polling e lineage de Painel TV e Produtividade: `docs\migration\86.reporting-pdf-calculation-cleanup-painel-tv-produtividade.md`.
Registro da remocao governada de schema residual de Painel TV e Produtividade: `docs\migration\87.schema-removal-painel-tv-produtividade.md`.
Registro da canonicalizacao de superficies de navegacao SPA/SSR com hardening de links principais: `docs\migration\89.canonical-surface-navigation-hardening.md`.
Registro da consolidacao de contratos/rotas canonicas e compat residual: `docs\migration\90.contract-route-deduplication-governance.md`.
Registro da erradicacao de mocks e placeholders de negocio em runtime: `docs\migration\91.runtime-mock-data-eradication.md`.
Registro da canonicalizacao de reentrada em Treinamentos Raiz contra atalhos SSR residuais: `docs\migration\92.training-root-reentry-canonicalization.md`.
Registro do hardening de router, compat e restore de Treinamentos Raiz contra regressao: `docs\migration\93.training-root-router-state-hardening.md`.
Registro dos guardas arquiteturais contra links SSR casuais para superficies SPA canonicas: `docs\migration\94.ssr-template-canonical-link-guards.md`.
Registro da limpeza governada do residual fisico `pages-training-workspace.js`: `docs\migration\95.residual-training-workspace-cleanup.md`.
Registro do hotfix de redirect same-origin publico para `/tipos-treinamento`: `docs\migration\96.public-same-origin-training-root-redirect-hotfix.md`.
Registro da formalizacao da fronteira hibrida blindada do Relatorio Individual: `docs\migration\97.individual-report-boundary-hardening.md`.
Registro da abertura real do contrato de leitura API de Operacoes/Pernoites com escrita SSR preservada: `docs\migration\98.operacoes-pernoites-read-api-boundary.md`.
Registro do saneamento global de hygiene entre fonte viva, output local e historico operacional: `docs\migration\99.repository-hygiene-boundary-governance.md`.
Registro da publicacao do contrato backend do relatorio geral de horas totais voadas: `docs\migration\100.financeiro-horas-totais-voadas-backend-contract.md`.
Registro da exposicao frontend HML do relatorio geral de horas totais voadas: `docs\migration\101.financeiro-horas-totais-voadas-frontend-hml-exposure.md`.

Leia primeiro, nesta ordem:

1. [docs/operations/LOCAL_RUNTIME.md](docs/operations/LOCAL_RUNTIME.md) para bootstrap local real.
2. [docs/operations/canonical-commands.md](docs/operations/canonical-commands.md) para comandos oficiais.
3. [docs/operations/WINDOWS_SELF_HOSTED_SERVER.md](docs/operations/WINDOWS_SELF_HOSTED_SERVER.md) para operacao self-hosted.
4. [docs/governance/repo-topology.md](docs/governance/repo-topology.md) para entender a estrutura do repo.
5. [docs/product/README.md](docs/product/README.md) para entrada de produto.

| area | fonte |
| --- | --- |
| arquitetura | [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) |
| operacao | [docs/operations/canonical-commands.md](docs/operations/canonical-commands.md), [docs/operations/RUNBOOK.md](docs/operations/RUNBOOK.md), [docs/operations/WINDOWS_SELF_HOSTED_SERVER.md](docs/operations/WINDOWS_SELF_HOSTED_SERVER.md) |
| governanca | [docs/governance/repository-governance.md](docs/governance/repository-governance.md), [docs/governance/repo-topology.md](docs/governance/repo-topology.md), [docs/governance/documentation-governance.md](docs/governance/documentation-governance.md) |
| produto | [docs/product/README.md](docs/product/README.md) |

Docs de migracao e plataformas retiradas ficam em `docs\migration`; docs arquivadas ficam em `docs\archive`. Elas nao sao fonte operacional vigente.
Registro desta correcao de first load da home no frontend novo: `docs\migration\35.frontend-home-first-load-edge-cache-no-store.md`.
Registro desta correcao de banners indevidos em `Equipamentos`: `docs\migration\35.equipamentos-flash-404-probe-lifecycle.md`.
Registro desta correcao de feriado nacional movel automatico em Jornadas: `docs\migration\59.jornadas-feriado-nacional-movel-automatico.md`.
Registro deste hotfix UX da coluna Acoes na grade de Jornadas: `docs\migration\60.jornadas-acoes-grade-ux-hotfix.md`.
Registro deste hotfix de quebra monetaria nos KPIs de Jornadas: `docs\migration\61.jornadas-kpi-money-nowrap-hotfix.md`.
Registro deste hotfix de colunas visiveis na grade de Jornadas: `docs\migration\62.jornadas-grade-colunas-visiveis-hotfix.md`.
Registro deste hotfix de Status colapsavel na grade de Jornadas: `docs\migration\63.jornadas-status-colapsavel-hotfix.md`.
Registro historico da interpretacao intermediaria de sabado sem diurno em Jornadas: `docs\migration\64.jornadas-sabado-sem-diurno.md`.
Registro da regra final de sabado feriado com pagamento diurno em Jornadas: `docs\migration\65.jornadas-sabado-feriado-com-diurno.md`.
Registro da regra de noturno/adicional em feriado dobrado por taxa parametrizada em Jornadas: `docs\migration\66.jornadas-noturno-feriado-dobro-parametrizado.md`.
Registro da correcao das taxas oficiais de COMANDANTE em Jornadas: `docs\migration\67.jornadas-comandante-taxas-oficiais-9218-18436.md`.
Registro da correcao de jornadas que atravessam meia-noite com rateio de feriado em Jornadas: `docs\migration\68.jornadas-virada-feriado-rateio-calendario.md`.
Registro da melhoria do PDF de Jornadas com bases de horas e valores dos adicionais: `docs\migration\69.jornadas-pdf-horas-valores-bases-adicionais.md`.
Registro da correcao de apresentacao das duracoes de Jornadas em HH:MM: `docs\migration\70.jornadas-duracoes-hhmm-ui-pdf.md`.
Registro do fechamento final do PDF de Jornadas por tipo de dia e total a pagar: `docs\migration\71.jornadas-pdf-fechamento-tipo-dia.md`.
Registro da correcao de contraste dos cabecalhos escuros no PDF de Jornadas: `docs\migration\72.jornadas-pdf-contraste-cabecalhos.md`.
Registro do resumo tabular de horas e valores no final do PDF de Jornadas: `docs\migration\73.jornadas-pdf-resumo-horas-valores-tabular.md`.
Registro da limpeza textual do status no PDF de Jornadas: `docs\migration\74.jornadas-pdf-status-sem-ruido-tecnico.md`.
Registro da limpeza do status da grade de Jornadas removendo ruido tecnico de fallback de preview: `docs\migration\75.jornadas-grade-status-fallback-preview-sem-ruido.md`.
Registro da persistencia de snapshot de calculo em Jornadas: `docs\migration\76.jornadas-snapshot-calculo-persistido.md`.

## Compat, legacy e archive

A politica para decidir entre compatibilidade, legado vivo, arquivo historico e remocao fica em [docs/governance/legacy-policy.md](docs/governance/legacy-policy.md).

| area | regra curta |
| --- | --- |
| `scripts/` | wrappers historicos de compatibilidade; nao recebe novos fluxos. Fonte: [scripts/README.md](scripts/README.md). |
| `legacy/` | legado vivo com dependencia real; nao e nucleo canonico. Fonte: [legacy/README.md](legacy/README.md). |
| `archive/` | snapshots, backups e wrappers antigos fora da operacao viva. Fonte: [archive/README.md](archive/README.md). |
| `docs/archive/` | documentos historicos; nao sao fonte principal. Fonte: [docs/archive/README.md](docs/archive/README.md). |

## Ambiente local e higiene

- Python 3.11+ e PostgreSQL acessivel localmente ou por rede interna sao requisitos do bootstrap.
- `.venv`, `.ruff_cache` e `.vscode` sao artefatos locais; nao aparecem na topologia oficial acima.
- Se `.venv` ou `.vscode` estiverem visiveis na sua raiz local, leia como excecao de workspace, nao como estrutura do produto.
- `.env.example` e a referencia base de desenvolvimento.
- `ops\windows\env\prod.env.example` e `ops\windows\env\hml.env.example` sao referencias de ambientes Windows/self-hosted.

## O que nao e fonte viva

- `.tmp\`, quando presente, e arquivo morto local proibido na raiz; a ocorrencia conhecida foi removida conforme `docs\governance\tmp-classification.md`.
- `controle-treinamentos\`, quando presente dentro da raiz, e copia legada aninhada proibida; a ocorrencia conhecida foi movida para `archive\temp-backups\nested-repo-copy-20260415`.
- `docs\migration\retired-platforms\` preserva plataformas retiradas e nao e guia de deploy.
- Manuais unificados antigos e PDFs ambiguos nao devem concorrer com `docs\product`.
