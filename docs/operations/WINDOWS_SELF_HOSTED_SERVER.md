# Windows Self-Hosted Server

Guia operacional para rodar este sistema em um servidor Windows local com:

- PostgreSQL nativo
- Waitress para a aplicacao Flask
- Caddy como proxy reverso/TLS
- ambientes separados de `hml` e `prod`
- backups automatizados

Fonte canonica: a tabela oficial de tarefas, comandos e caminhos fica em `docs\operations\canonical-commands.md`. Este guia detalha a subida e a operacao Windows/self-hosted.

## 1. Premissas

- Windows dedicado para o sistema
- IP local fixo reservado no roteador
- no-break recomendado
- Caddy e PostgreSQL instalados no host
- PowerShell elevado para instalar servicos

## 2. Estrutura recomendada

```text
C:\srv\controle-treinamentos\
  caddy\Caddyfile
  env\prod.env
  env\hml.env
  logs\
  services\

D:\srv-data\controle-treinamentos\
  prod\uploads\
  prod\logs\
  hml\uploads\
  hml\logs\

E:\backups\controle-treinamentos\
  prod\
  hml\
```

Crie a estrutura base com:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\New-WindowsServerLayout.ps1
```

## 3. Arquivos de ambiente

Use os modelos:

- [prod.env.example](/C:/apps/controle-treinamentos/ops/windows/env/prod.env.example)
- [hml.env.example](/C:/apps/controle-treinamentos/ops/windows/env/hml.env.example)

Ajustes obrigatorios:

- `SECRET_KEY`
- `DATABASE_URL`
- `PG_BIN_DIR`
- `SMTP_*`
- `METRICS_TOKEN`
- `CRON_SECRET`
- `BACKUP_DIR`
- `BACKUP_INCLUDE_PATHS`

Para self-hosting com PostgreSQL no mesmo servidor, mantenha:

```text
ALLOW_LOCAL_DATABASE_IN_SECURE_ENV=1
DATABASE_URL=postgresql://usuario:senha@127.0.0.1:5432/ct_prod
```

## 4. Subida manual

Teste homolog manualmente:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-AppService.ps1 -EnvironmentName hml -EnvFile C:\srv\controle-treinamentos\env\hml.env
```

Teste producao manualmente:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-AppService.ps1 -EnvironmentName prod -EnvFile C:\srv\controle-treinamentos\env\prod.env
```

Health-check:

```powershell
Invoke-WebRequest http://127.0.0.1:8101/healthz
Invoke-WebRequest http://127.0.0.1:8102/healthz
```

## 5. Proxy reverso

Copie [Caddyfile.example](/C:/apps/controle-treinamentos/ops/windows/caddy/Caddyfile.example) para `C:\srv\controle-treinamentos\caddy\Caddyfile` e ajuste:

- `app.seudominio.com`
- `teste.seudominio.com`
- e-mail do ACME
- caminhos de log

## 6. Servicos Windows

O script abaixo gera os wrappers WinSW para:

- `CT-App-Prod`
- `CT-App-Hml`
- `CT-Caddy`

Exemplo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Install-WindowsServices.ps1 `
  -WinSWExePath C:\tools\winsw\WinSW-x64.exe `
  -CaddyExePath C:\tools\caddy\caddy.exe `
  -ProdEnvFile C:\srv\controle-treinamentos\env\prod.env `
  -HmlEnvFile C:\srv\controle-treinamentos\env\hml.env
```

Para instalar de fato no SCM, execute com `-Install` em um PowerShell elevado.

## 7. Rotinas operacionais

Worker manual:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-OperationalPython.ps1 `
  -EnvironmentName prod `
  -EnvFile C:\srv\controle-treinamentos\env\prod.env `
  -TargetScript backend\tools\maintenance\run_jobs_worker.py
```

Backup manual:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-OperationalPython.ps1 `
  -EnvironmentName prod `
  -EnvFile C:\srv\controle-treinamentos\env\prod.env `
  -TargetScript backend\tools\maintenance\run_backups.py
```

Consistency check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-OperationalPython.ps1 `
  -EnvironmentName prod `
  -EnvFile C:\srv\controle-treinamentos\env\prod.env `
  -TargetScript backend\tools\maintenance\run_db_consistency.py
```

Structural bootstrap:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-OperationalPython.ps1 `
  -EnvironmentName prod `
  -EnvFile C:\srv\controle-treinamentos\env\prod.env `
  -TargetScript backend\tools\maintenance\bootstrap_db_schema.py
```

Manual repair:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-OperationalPython.ps1 `
  -EnvironmentName prod `
  -EnvFile C:\srv\controle-treinamentos\env\prod.env `
  -TargetScript backend\tools\manual_unsafe\run_db_repair.py
```

`run_db_repair.py` e `cleanup_operational_data.py` sao trilha manual/perigosa. Nao agende essas rotinas como manutencao normal.

## 8. Agendamento recomendado

- Worker `prod`: a cada 5 minutos
- Worker `hml`: a cada 10 ou 15 minutos
- Backup `prod`: a cada 6 horas ou no minimo diario
- Backup `hml`: diario
- Consistency check `prod`: diario

No Windows, use o Task Scheduler para essas rotinas. Mantenha o banco fora da internet e exponha apenas `80/443`.

## 9. Firewall e rede

Abra somente:

- `80/tcp`
- `443/tcp`

Nao exponha:

- `5432/tcp`
- portas internas do Waitress
- compartilhamentos de backup

Se precisar de acesso remoto administrativo, prefira VPN em vez de expor `RDP` diretamente.
