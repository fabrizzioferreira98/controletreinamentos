[CmdletBinding()]
param(
    [ValidateSet("prod", "hml")]
    [string]$EnvironmentName,
    [string]$EnvFile,
    [string]$PythonExe,
    [string]$RepoRoot,
    [string]$RestoreUrl,
    [string]$RestoreSchema = "public",
    [switch]$ExtractArchives
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")

$resolvedRepoRoot = Get-ControleRepoRoot -RepoRoot $RepoRoot
$resolvedEnvFile = if ($EnvFile) { $EnvFile } else { Get-ControleDefaultEnvFile -RepoRoot $resolvedRepoRoot -EnvironmentName $EnvironmentName }
$resolvedPythonExe = Get-ControlePythonExe -RepoRoot $resolvedRepoRoot -PythonExe $PythonExe

Import-ControleEnvFile -EnvFile $resolvedEnvFile
[System.Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1")

$scriptArgs = @("ops\\scripts\\backup\\backup_restore_drill.py")
if ($RestoreUrl) {
    $scriptArgs += @("--restore-url", $RestoreUrl)
}
if ($RestoreSchema) {
    $scriptArgs += @("--restore-schema", $RestoreSchema)
}
if ($ExtractArchives) {
    $scriptArgs += "--extract-archives"
}

Push-Location $resolvedRepoRoot
try {
    & $resolvedPythonExe @scriptArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
