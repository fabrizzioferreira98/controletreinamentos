[CmdletBinding()]
param(
    [string]$RootDir = "C:\srv\controle-treinamentos",
    [string]$DataDir = "D:\srv-data\controle-treinamentos",
    [string]$BackupDir = "E:\backups\controle-treinamentos",
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")

$resolvedRepoRoot = Get-ControleRepoRoot -RepoRoot $RepoRoot

$directories = @(
    $RootDir,
    (Join-Path $RootDir "caddy"),
    (Join-Path $RootDir "env"),
    (Join-Path $RootDir "logs"),
    (Join-Path $RootDir "logs\caddy"),
    (Join-Path $RootDir "services"),
    $DataDir,
    (Join-Path $DataDir "prod"),
    (Join-Path $DataDir "prod\uploads"),
    (Join-Path $DataDir "prod\logs"),
    (Join-Path $DataDir "hml"),
    (Join-Path $DataDir "hml\uploads"),
    (Join-Path $DataDir "hml\logs"),
    $BackupDir,
    (Join-Path $BackupDir "prod"),
    (Join-Path $BackupDir "hml")
)

foreach ($directory in $directories) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$prodEnvSource = Join-Path $resolvedRepoRoot "ops\windows\env\prod.env.example"
$hmlEnvSource = Join-Path $resolvedRepoRoot "ops\windows\env\hml.env.example"
$caddySource = Join-Path $resolvedRepoRoot "ops\windows\caddy\Caddyfile.example"

$prodEnvTarget = Join-Path $RootDir "env\prod.env"
$hmlEnvTarget = Join-Path $RootDir "env\hml.env"
$caddyTarget = Join-Path $RootDir "caddy\Caddyfile"

if ((Test-Path $prodEnvSource) -and -not (Test-Path $prodEnvTarget)) {
    Copy-Item -Path $prodEnvSource -Destination $prodEnvTarget
}

if ((Test-Path $hmlEnvSource) -and -not (Test-Path $hmlEnvTarget)) {
    Copy-Item -Path $hmlEnvSource -Destination $hmlEnvTarget
}

if ((Test-Path $caddySource) -and -not (Test-Path $caddyTarget)) {
    Copy-Item -Path $caddySource -Destination $caddyTarget
}

Write-Host "Estrutura base criada."
Write-Host "RootDir  : $RootDir"
Write-Host "DataDir  : $DataDir"
Write-Host "BackupDir: $BackupDir"
