# COMPAT: wrapper historico para execucao operacional Python no Windows.
# Comando oficial: ops\windows\scripts\Invoke-OperationalPython.ps1.
# Manter fino: este arquivo existe apenas para consumidores antigos.

[CmdletBinding()]
param(
    [ValidateSet("prod", "hml")]
    [string]$EnvironmentName,
    [string]$TargetScript,
    [string[]]$ScriptArgument = @(),
    [string]$EnvFile,
    [string]$PythonExe,
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"
$delegatePath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..\ops\windows\scripts")).Path "Invoke-OperationalPython.ps1"

if (-not (Test-Path $delegatePath)) {
    throw "Compat delegate nao encontrado: $delegatePath"
}

Write-Warning "Compatibilidade: scripts\windows\Invoke-OperationalPython.ps1 e alias historico; use ops\windows\scripts\Invoke-OperationalPython.ps1."
& $delegatePath @PSBoundParameters
exit $LASTEXITCODE
