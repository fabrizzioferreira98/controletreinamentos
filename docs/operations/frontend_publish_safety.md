# Publicacao Segura Do Frontend

Este procedimento existe para impedir publicacao acidental em producao durante validacoes de HML.

## HML

Use o wrapper dedicado:

```powershell
.\ops\windows\scripts\Publish-Frontend-Hml.ps1
```

Ou o publicador principal com ambiente explicito:

```powershell
.\ops\windows\scripts\Publish-Frontend.ps1 -Environment hml
```

O modo HML usa somente:

- destino: `C:\srv\controle-treinamentos\frontend\hml`
- env: `C:\srv\controle-treinamentos\env\hml.env`

Qualquer destino de producao ou `prod.env` deve ser recusado.

## Producao

Producao nunca e default. Para publicar producao, use confirmacao literal:

```powershell
.\ops\windows\scripts\Publish-Frontend.ps1 -Environment prod -ConfirmProdPublish "publish-prod"
```

O modo producao usa somente:

- destino: `C:\srv\controle-treinamentos\frontend\prod`
- env: `C:\srv\controle-treinamentos\env\prod.env`

Sem `-ConfirmProdPublish "publish-prod"`, o script deve abortar.

## Validacao Sem Publicar

Para validar parametros sem build, copia ou swap:

```powershell
.\ops\windows\scripts\Publish-Frontend.ps1 -Environment hml -ValidateOnly
.\ops\windows\scripts\Publish-Frontend.ps1 -Environment prod -ConfirmProdPublish "publish-prod" -ValidateOnly
```

## Rollback

Antes de restaurar um backup, crie uma copia de seguranca do estado atual.

```powershell
$src = "C:\srv\controle-treinamentos\frontend-backup\<backup-aprovado>"
$dst = "C:\srv\controle-treinamentos\frontend\prod"
$safety = "C:\srv\controle-treinamentos\frontend-backup\prod-current-before-rollback-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

if (-not (Test-Path "$src\asset-manifest.json")) { throw "Backup sem asset-manifest.json" }
if ($dst -ne "C:\srv\controle-treinamentos\frontend\prod") { throw "Destino inesperado" }

robocopy $dst $safety /MIR /R:2 /W:1
if ($LASTEXITCODE -gt 7) { throw "Falha ao criar backup de seguranca" }

robocopy $src $dst /MIR /R:2 /W:1
if ($LASTEXITCODE -gt 7) { throw "Falha no rollback" }
```
