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
. (Join-Path $PSScriptRoot "Common.ps1")

if (-not $TargetScript) {
    throw "Informe -TargetScript com o script Python a ser executado."
}

$resolvedRepoRoot = Get-ControleRepoRoot -RepoRoot $RepoRoot
$resolvedEnvFile = if ($EnvFile) { $EnvFile } else { Get-ControleDefaultEnvFile -RepoRoot $resolvedRepoRoot -EnvironmentName $EnvironmentName }
$resolvedPythonExe = Get-ControlePythonExe -RepoRoot $resolvedRepoRoot -PythonExe $PythonExe
$resolvedScript = Join-Path $resolvedRepoRoot $TargetScript

if (-not (Test-Path $resolvedScript)) {
    throw "Script Python nao encontrado: $resolvedScript"
}

Import-ControleEnvFile -EnvFile $resolvedEnvFile
[System.Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1")

Push-Location $resolvedRepoRoot
try {
    & $resolvedPythonExe $resolvedScript @ScriptArgument
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
