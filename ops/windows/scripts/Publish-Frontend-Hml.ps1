[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoRoot,
    [string]$BackupRoot = "C:\srv\controle-treinamentos\frontend-backup",
    [string]$BuildDir = "",
    [switch]$SkipBuild,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$mainScript = Join-Path $PSScriptRoot "Publish-Frontend.ps1"
if (-not (Test-Path -LiteralPath $mainScript -PathType Leaf)) {
    throw "Publicador principal nao encontrado: $mainScript"
}

$arguments = @("-Environment", "hml", "-BackupRoot", $BackupRoot)
if ($RepoRoot) {
    $arguments += @("-RepoRoot", $RepoRoot)
}
if ($BuildDir) {
    $arguments += @("-BuildDir", $BuildDir)
}
if ($SkipBuild) {
    $arguments += "-SkipBuild"
}
if ($ValidateOnly) {
    $arguments += "-ValidateOnly"
}

& $mainScript @arguments
