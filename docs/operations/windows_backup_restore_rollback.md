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

## Restore canônico
Restore canônico de continuidade exige, no mínimo:
- dump
- assets
- config
- manifest
- validação pós-restore

Classificação operacional:
- dump isolado = restore parcial
- assets isolados = restore auxiliar
- fallback lógico parcial (`.json.gz` / `.sqlite3.gz`) = recuperação auxiliar, não restore canônico
- restore canônico = artefatos da mesma janela + banco restaurado + storage restaurado + validação pós-restore sem inconsistência crítica

Banco e storage não podem ser promovidos separadamente como se fossem superfícies independentes:
- `tripulantes.foto_storage_ref` depende do blob correspondente em uploads
- `tripulante_arquivos_pdf.storage_ref` depende do blob correspondente em uploads
- `treinamento_anexos_pdf.storage_ref` depende do blob correspondente em uploads
- metadata sem blob, blob órfão ou referência quebrada significam restore incompleto

## Contrato mínimo do manifesto
- o manifesto precisa pertencer à mesma janela dos artefatos restaurados
- o manifesto precisa referenciar dump, assets e config daquela mesma janela
- assets restaurados fora da janela do manifesto não contam como restore canônico
- config restaurada fora da janela do manifesto não conta como restore canônico

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
- os quatro artefatos pertencem à mesma janela `YYYYMMDD_HHMMSS`
- o manifesto lista dump, assets e config daquela janela

## Drill de restore
Com URL administrativa de restore:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\apps\controle-treinamentos\ops\windows\scripts\Invoke-BackupRestoreDrill.ps1" -EnvironmentName prod -EnvFile "C:\srv\controle-treinamentos\env\prod.env" -RestoreUrl "postgresql://USUARIO_ADMIN:SENHA@127.0.0.1:5432/postgres" -ExtractArchives
```

O drill valida:
- pacote mínimo de restore canônico (`dump` + `assets` + `config` + `manifest`)
- dump por `pg_restore --list`
- restore completo em banco temporário
- integridade dos `.tar.gz`
- extração de arquivos/configurações em diretório temporário

O drill sozinho ainda não conclui restore canônico de continuidade quando falta a validação pós-restore no ambiente restaurado.

## Passo operacional canônico
1. Pré-condições
- janela de manutenção aprovada
- artefatos da mesma janela disponíveis: dump, assets, config e manifest
- destino de restore isolado ou ambiente em manutenção
- `MEDIA_STORAGE_ROOT` do ambiente restaurado definido para os assets restaurados

2. Restaurar config
- restaurar `config_backup_*.tar.gz` antes de subir a aplicação
- conferir `env`, `caddy` e `tasks`
- cuidado principal: não misturar config de janela diferente do manifesto

3. Restaurar assets
- extrair `assets_backup_*.tar.gz` no diretório que será o `MEDIA_STORAGE_ROOT`
- cuidado principal: uploads precisam vir da mesma janela do dump e do manifesto

4. Restaurar banco
- criar banco vazio de destino
- rodar:

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges --dbname "postgresql://USUARIO_ADMIN:SENHA@127.0.0.1:5432/NOME_DO_BANCO" "C:\backups\controle-treinamentos\prod\db_backup_YYYYMMDD_HHMMSS.dump"
```

5. Validar metadata/blob após restore
- rodar o post-check canônico:

```powershell
python "C:\apps\controle-treinamentos\backend\tools\maintenance\run_restore_postcheck.py" --json --media-root "C:\restore-temp\assets\uploads" --artifact "C:\backups\controle-treinamentos\prod\db_backup_YYYYMMDD_HHMMSS.dump" --artifact "C:\backups\controle-treinamentos\prod\assets_backup_YYYYMMDD_HHMMSS.tar.gz" --artifact "C:\backups\controle-treinamentos\prod\config_backup_YYYYMMDD_HHMMSS.tar.gz" --artifact "C:\backups\controle-treinamentos\prod\backup_manifest_YYYYMMDD_HHMMSS.json"
```

Checagens mínimas obrigatórias:
- foto com `foto_storage_ref` precisa resolver blob em uploads
- documento/anexo com `storage_ref` precisa resolver blob em uploads
- `foto_base64` e `db:bytea` podem aparecer só como compat residual visível
- `metadata_without_blob` = falha crítica
- `metadata_without_reference` = falha crítica
- `metadata_with_unsupported_reference` = falha crítica
- `orphan_blobs` = aviso operacional e reconciliação manual antes de promover limpeza
- assets fora da janela do manifesto = restore inválido

6. Smoke final
- `SELECT COUNT(*)` nas tabelas principais
- login administrativo
- telas críticas
- healthcheck da aplicação

## Restore auxiliar de arquivos/config
Arquivos:

```powershell
tar -xzf "C:\backups\controle-treinamentos\prod\assets_backup_YYYYMMDD_HHMMSS.tar.gz" -C "C:\restore-temp\assets"
```

Configurações:

```powershell
tar -xzf "C:\backups\controle-treinamentos\prod\config_backup_YYYYMMDD_HHMMSS.tar.gz" -C "C:\restore-temp\config"
```

Uso permitido:
- inspeção
- comparação com manifesto
- recuperação auxiliar isolada

Uso proibido:
- declarar continuidade restaurada sem banco restaurado
- promover dump sem assets/config validados em conjunto

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
- restore canônico tem contrato explícito: dump + assets + config + manifest + pós-validação
- pós-validação metadata/blob zera inconsistência crítica
- banco e storage são restaurados na mesma janela operacional
- rollback está documentado e testável
