[CmdletBinding()]
param(
    [string]$RulePrefix = "CT",
    [int]$HttpPort = 80,
    [int]$HttpsPort = 443,
    [int]$PostgresPort = 5432,
    [int]$ProdAppPort = 8101,
    [int]$HmlAppPort = 8102
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Netsh {
    param(
        [string[]]$Arguments
    )

    & netsh.exe @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $joined = $Arguments -join " "
        throw "netsh.exe falhou com codigo ${exitCode}: $joined"
    }
}

function Remove-RuleIfExists {
    param(
        [string]$RuleName
    )

    & netsh.exe advfirewall firewall delete rule "name=$RuleName" | Out-Null
}

function Add-InboundRule {
    param(
        [string]$RuleName,
        [string]$Action,
        [int]$LocalPort
    )

    Remove-RuleIfExists -RuleName $RuleName
    Invoke-Netsh -Arguments @(
        "advfirewall", "firewall", "add", "rule",
        "name=$RuleName",
        "dir=in",
        "action=$Action",
        "protocol=TCP",
        "localport=$LocalPort",
        "profile=any"
    )
}

if (-not (Test-IsAdministrator)) {
    throw "Execute este script em um PowerShell aberto como Administrador."
}

Add-InboundRule -RuleName "$RulePrefix HTTP $HttpPort" -Action "allow" -LocalPort $HttpPort
Add-InboundRule -RuleName "$RulePrefix HTTPS $HttpsPort" -Action "allow" -LocalPort $HttpsPort
Add-InboundRule -RuleName "$RulePrefix Block PostgreSQL $PostgresPort" -Action "block" -LocalPort $PostgresPort
Add-InboundRule -RuleName "$RulePrefix Block App Prod $ProdAppPort" -Action "block" -LocalPort $ProdAppPort
Add-InboundRule -RuleName "$RulePrefix Block App Hml $HmlAppPort" -Action "block" -LocalPort $HmlAppPort

foreach ($ruleName in @(
    "$RulePrefix HTTP $HttpPort",
    "$RulePrefix HTTPS $HttpsPort",
    "$RulePrefix Block PostgreSQL $PostgresPort",
    "$RulePrefix Block App Prod $ProdAppPort",
    "$RulePrefix Block App Hml $HmlAppPort"
)) {
    Invoke-Netsh -Arguments @("advfirewall", "firewall", "show", "rule", "name=$ruleName")
}
