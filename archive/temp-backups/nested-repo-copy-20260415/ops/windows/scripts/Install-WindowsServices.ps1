[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$ServiceRoot = "C:\srv\controle-treinamentos\services",
    [string]$PythonExe,
    [string]$WinSWExePath,
    [string]$CaddyExePath,
    [string]$CaddyConfigPath = "C:\srv\controle-treinamentos\caddy\Caddyfile",
    [string]$ProdEnvFile = "C:\srv\controle-treinamentos\env\prod.env",
    [string]$HmlEnvFile = "C:\srv\controle-treinamentos\env\hml.env",
    [switch]$Install
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")

if (-not $WinSWExePath) {
    throw "Informe -WinSWExePath com o caminho do binario WinSW."
}
if (-not $CaddyExePath) {
    throw "Informe -CaddyExePath com o caminho do executavel do Caddy."
}

$resolvedRepoRoot = Get-ControleRepoRoot -RepoRoot $RepoRoot
$resolvedPythonExe = Get-ControlePythonExe -RepoRoot $resolvedRepoRoot -PythonExe $PythonExe

function New-WinSWServiceDefinition {
    param(
        [string]$ServiceId,
        [string]$DisplayName,
        [string]$Description,
        [string]$Executable,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogPath,
        [string[]]$Dependencies = @()
    )

    $serviceDir = Join-Path $ServiceRoot $ServiceId
    New-Item -ItemType Directory -Force -Path $serviceDir | Out-Null

    $wrapperExePath = Join-Path $serviceDir "$ServiceId.exe"
    $xmlPath = Join-Path $serviceDir "$ServiceId.xml"

    Copy-Item -Path $WinSWExePath -Destination $wrapperExePath -Force

    $dependXml = ""
    foreach ($dependency in $Dependencies) {
        $dependXml += "  <depend>$dependency</depend>`r`n"
    }

    $xml = @"
<service>
  <id>$ServiceId</id>
  <name>$DisplayName</name>
  <description>$Description</description>
  <executable>$Executable</executable>
  <arguments>$Arguments</arguments>
  <workingdirectory>$WorkingDirectory</workingdirectory>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
$dependXml  <logpath>$LogPath</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
  <stoptimeout>15000</stoptimeout>
  <onfailure action="restart" delay="10 sec" />
  <onfailure action="restart" delay="30 sec" />
</service>
"@

    Set-Content -Path $xmlPath -Value $xml -Encoding UTF8

    if ($Install) {
        & $wrapperExePath install
        & $wrapperExePath start
    }
}

New-WinSWServiceDefinition `
    -ServiceId "CT-App-Prod" `
    -DisplayName "Controle Treinamentos - App Prod" `
    -Description "Aplicacao Flask/Waitress de producao." `
    -Executable "powershell.exe" `
    -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$resolvedRepoRoot\ops\windows\scripts\Invoke-AppService.ps1`" -EnvironmentName prod -EnvFile `"$ProdEnvFile`" -PythonExe `"$resolvedPythonExe`" -RepoRoot `"$resolvedRepoRoot`"" `
    -WorkingDirectory $resolvedRepoRoot `
    -LogPath "C:\srv\controle-treinamentos\logs\services\prod"

New-WinSWServiceDefinition `
    -ServiceId "CT-App-Hml" `
    -DisplayName "Controle Treinamentos - App Hml" `
    -Description "Aplicacao Flask/Waitress de homologacao." `
    -Executable "powershell.exe" `
    -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$resolvedRepoRoot\ops\windows\scripts\Invoke-AppService.ps1`" -EnvironmentName hml -EnvFile `"$HmlEnvFile`" -PythonExe `"$resolvedPythonExe`" -RepoRoot `"$resolvedRepoRoot`"" `
    -WorkingDirectory $resolvedRepoRoot `
    -LogPath "C:\srv\controle-treinamentos\logs\services\hml"

New-WinSWServiceDefinition `
    -ServiceId "CT-Caddy" `
    -DisplayName "Controle Treinamentos - Caddy" `
    -Description "Proxy reverso e terminacao TLS." `
    -Executable $CaddyExePath `
    -Arguments "run --config `"$CaddyConfigPath`" --adapter caddyfile" `
    -WorkingDirectory (Split-Path -Parent $CaddyConfigPath) `
    -LogPath "C:\srv\controle-treinamentos\logs\services\caddy" `
    -Dependencies @("Tcpip")

Write-Host "Definicoes WinSW geradas em $ServiceRoot"
if (-not $Install) {
    Write-Host "Use -Install em um PowerShell elevado para instalar e iniciar os servicos."
}
