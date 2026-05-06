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

& $delegatePath @PSBoundParameters
exit $LASTEXITCODE
