# Arquivado: copia aninhada do repositorio

Esta copia foi movida para `archive/temp-backups/nested-repo-copy-20260415/` na etapa 7.3 para deixar de competir com a raiz viva.

Nao use este diretorio para operacao, build, teste, desenvolvimento ou documentacao vigente.

Esta pasta nao e a raiz oficial do produto. A raiz oficial e `C:\apps\controle-treinamentos`.

A decisao de classificacao e destino esta registrada em `docs/governance/nested-repo-classification.md` na raiz oficial. Nao adicione novos fluxos, correcoes funcionais ou documentacao operacional aqui.

## Conteudo historico preservado abaixo

# Controle de Treinamentos

Aplicacao web interna para controle de tripulantes, treinamentos, vencimentos, produtividade e operacao de bases.

## Modelo atual de hospedagem

O projeto opera no modelo servidor local / self-hosted Windows:

- Flask + Waitress para a aplicacao
- Caddy como proxy reverso e terminacao TLS
- PostgreSQL nativo no host local
- storage de fotos, PDFs e anexos em filesystem local
- jobs, backups e rotinas operacionais executados no proprio servidor

Os antigos fluxos de deploy cloud/serverless foram descontinuados e nao fazem mais parte da operacao oficial.

## Desenvolvimento local

Requisitos:

- Python 3.11+
- PostgreSQL acessivel localmente ou por rede interna

Instalacao:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Execucao local:

```powershell
.venv\Scripts\python.exe backend\tools\runtime\run.py
```

A aplicacao sobe por padrao em [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Ambiente e configuracao

Arquivos de referencia:

- ambiente base de desenvolvimento: [C:\apps\controle-treinamentos\.env.example](C:\apps\controle-treinamentos\.env.example)
- producao self-hosted Windows: [C:\apps\controle-treinamentos\ops\windows\env\prod.env.example](C:\apps\controle-treinamentos\ops\windows\env\prod.env.example)
- homologacao self-hosted Windows: [C:\apps\controle-treinamentos\ops\windows\env\hml.env.example](C:\apps\controle-treinamentos\ops\windows\env\hml.env.example)

Variaveis centrais:

- `APP_ENV`
- `SECRET_KEY`
- `DATABASE_URL`
- `ALLOW_LOCAL_DATABASE_IN_SECURE_ENV`
- `FRONTEND_PUBLIC_ORIGIN`
- `FRONTEND_LOCAL_ORIGIN`
- `FRONTEND_ALLOWED_ORIGINS`
- `CRON_SECRET`
- `SMTP_*`
- `BACKUP_*`
- `MONITORING_*`

## Operacao local / self-hosted

Guia operacional principal:

- [C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md](C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md)

Entradas tipicas:

- producao local: `http://192.168.25.33`
- homologacao local: `http://192.168.25.33:8082`
- producao externa: `https://controle.brasilvida.app.br`
- homologacao externa: `https://teste.brasilvida.app.br`

## Banco, consistencia e seed

Validar estrutura e dados criticos:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_db_consistency.py
```

Executar reparo antes da validacao:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_db_consistency.py --repair
```

## Jobs, backups e rotinas operacionais

Worker de jobs:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_jobs_worker.py
```

Backup:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_backups.py
```

Disparo de notificacoes:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_notifications.py
```

## Release e validacao

Gate padrao:

```powershell
.venv\Scripts\python.exe ops\scripts\release\release_gate.py
```

Gate endurecido:

```powershell
.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url https://seu-ambiente --evidence-manifest C:\srv-data\controle-treinamentos\prod\evidence\release_manifest.json --regression-checklist docs/operations/REGRESSION_AUDIT_CHECKLIST.md --evidence-max-age-hours 24
```

Smoke pos-deploy:

```powershell
.venv\Scripts\python.exe ops\scripts\smoke\post_deploy_smoke.py --base-url https://seu-ambiente
```
