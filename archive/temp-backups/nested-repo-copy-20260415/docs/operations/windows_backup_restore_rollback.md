# Backup, Restore e Rollback no Windows

## Escopo
- Banco PostgreSQL local
- Arquivos de upload
- Configurações operacionais (`env`, `caddy`, `tasks`)
- Cópia externa opcional
- Drill de restore de banco e arquivos

## O que entra no backup
- Banco: artefato `db_backup_YYYYMMDD_HHMMSS.dump`
- Arquivos: artefato `assets_backup_YYYYMMDD_HHMMSS.tar.gz`
- Configurações: artefato `config_backup_YYYYMMDD_HHMMSS.tar.gz`
- Manifesto: `backup_manifest_YYYYMMDD_HHMMSS.json`

## Configuração mínima
Em `prod.env` e `hml.env`:

```env
BACKUP_DIR=C:\backups\controle-treinamentos\prod
BACKUP_RETENTION_DAYS=30
BACKUP_INCLUDE_PATHS=C:\srv-data\controle-treinamentos\prod\uploads
BACKUP_CONFIG_PATHS=C:\srv\controle-treinamentos\env,C:\srv\controle-treinamentos\caddy,C:\srv\controle-treinamentos\tasks
BACKUP_ALLOW_LOGICAL_FALLBACK=0
BACKUP_EXTERNAL_MIRROR_DIR=\\servidor-backup\controle-treinamentos\prod
BACKUP_EXTERNAL_MIRROR_REQUIRED=0
```

## Execução manual de backup
Produção:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\srv\controle-treinamentos\tasks\backup-prod.ps1"
```

Homologação:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\srv\controle-treinamentos\tasks\backup-hml.ps1"
```

## Onde validar
- Produção: `C:\backups\controle-treinamentos\prod`
- Homologação: `C:\backups\controle-treinamentos\hml`

Validação mínima:
- existe `.dump`
- existe `assets_backup_*.tar.gz`
- existe `config_backup_*.tar.gz`
- existe `backup_manifest_*.json`

## Drill de restore
Com URL administrativa de restore:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\apps\controle-treinamentos\scripts\windows\Invoke-BackupRestoreDrill.ps1" -EnvironmentName prod -EnvFile "C:\srv\controle-treinamentos\env\prod.env" -RestoreUrl "postgresql://USUARIO_ADMIN:SENHA@127.0.0.1:5432/postgres" -ExtractArchives
```

O drill valida:
- dump por `pg_restore --list`
- restore completo em banco temporário
- integridade dos `.tar.gz`
- extração de arquivos/configurações em diretório temporário

## Restore manual do banco
1. Criar banco vazio de destino.
2. Rodar:

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges --dbname "postgresql://USUARIO_ADMIN:SENHA@127.0.0.1:5432/NOME_DO_BANCO" "C:\backups\controle-treinamentos\prod\db_backup_YYYYMMDD_HHMMSS.dump"
```

3. Validar:
- `SELECT COUNT(*)` nas tabelas principais
- login administrativo
- telas críticas

## Restore manual de arquivos/config
Arquivos:

```powershell
tar -xzf "C:\backups\controle-treinamentos\prod\assets_backup_YYYYMMDD_HHMMSS.tar.gz" -C "C:\restore-temp\assets"
```

Configurações:

```powershell
tar -xzf "C:\backups\controle-treinamentos\prod\config_backup_YYYYMMDD_HHMMSS.tar.gz" -C "C:\restore-temp\config"
```

Depois comparar com o manifesto `backup_manifest_*.json`.

## Rollback operacional
### Código
1. Voltar para a release anterior.
2. Reiniciar `CT-App-Prod`.
3. Validar `/healthz`, login e fluxos críticos.

### Ambiente (`env`)
1. Restaurar `prod.env` ou `hml.env` da cópia em `config_backup`.
2. Reiniciar a app correspondente.
3. Validar conexão com banco e sessão.

### Banco
1. Restaurar o dump anterior em banco temporário.
2. Validar contagens e login.
3. Promover o banco restaurado para produção na janela de manutenção.

## Política mínima
- Backup do banco: diário
- Backup de arquivos/config: diário
- Cópia externa: diária
- Retenção:
  - 7 diários
  - 4 semanais
  - 3 mensais
- Drill de restore: semanal em homolog ou ambiente isolado
- Backup antes de qualquer deploy relevante

## Critério de pronto
- backup manual executa sem erro
- arquivos e configs entram no artefato
- existe cópia externa configurada
- drill de restore do banco passa
- drill de restore de arquivos passa
- rollback está documentado e testável
