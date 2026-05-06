[CmdletBinding()]
param(
    [string]$RootDir = "C:\srv\controle-treinamentos"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot

& (Join-Path $scriptDir "Install-WindowsScheduledTasks.ps1") -RootDir $RootDir
& (Join-Path $scriptDir "Configure-WindowsFirewall.ps1")
