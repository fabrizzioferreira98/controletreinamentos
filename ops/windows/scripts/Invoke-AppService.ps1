[CmdletBinding()]
param(
    [ValidateSet("prod", "hml")]
    [string]$EnvironmentName,
    [string]$EnvFile,
    [string]$PythonExe,
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")

$resolvedRepoRoot = Get-ControleRepoRoot -RepoRoot $RepoRoot
$resolvedEnvFile = if ($EnvFile) { $EnvFile } else { Get-ControleDefaultEnvFile -RepoRoot $resolvedRepoRoot -EnvironmentName $EnvironmentName }
$resolvedPythonExe = Get-ControlePythonExe -RepoRoot $resolvedRepoRoot -PythonExe $PythonExe

Import-ControleEnvFile -EnvFile $resolvedEnvFile
[System.Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1")

$runnerPath = Join-Path $resolvedRepoRoot "ops\windows\scripts\run_waitress_server.py"
if (-not (Test-Path $runnerPath)) {
    throw "Runner do Waitress nao encontrado: $runnerPath"
}

Push-Location $resolvedRepoRoot
try {
    & $resolvedPythonExe $runnerPath
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
