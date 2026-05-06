# COMPAT: wrapper historico para subida Windows/self-hosted.
# Comando oficial: ops\windows\scripts\Invoke-AppService.ps1.
# Manter fino: este arquivo existe apenas para consumidores antigos.

[CmdletBinding()]
param(
    [ValidateSet("prod", "hml")]
    [string]$EnvironmentName,
    [string]$EnvFile,
    [string]$PythonExe,
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"
$delegatePath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..\ops\windows\scripts")).Path "Invoke-AppService.ps1"

if (-not (Test-Path $delegatePath)) {
    throw "Compat delegate nao encontrado: $delegatePath"
}

Write-Warning "Compatibilidade: scripts\windows\Invoke-AppService.ps1 e alias historico; use ops\windows\scripts\Invoke-AppService.ps1."
& $delegatePath @PSBoundParameters
exit $LASTEXITCODE
