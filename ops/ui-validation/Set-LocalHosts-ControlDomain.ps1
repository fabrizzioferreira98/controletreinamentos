param(
    [string]$HostName = "controle.brasilvida.app.br",
    [string]$TargetIp = "192.168.25.33"
)

$ErrorActionPreference = "Stop"

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidencePath = Join-Path $PSScriptRoot "local-hosts-control-domain-$stamp.json"
$backupPath = Join-Path $PSScriptRoot "hosts-backup-$stamp.txt"

$before = @(Get-Content -LiteralPath $hostsPath -ErrorAction Stop)
Set-Content -LiteralPath $backupPath -Value $before -Encoding ASCII

$escapedHost = [regex]::Escape($HostName)
$updated = $false
$after = @(
    $before | ForEach-Object {
        if ($_ -match "^\s*#") {
            $_
        } elseif ($_ -match "(?i)(^|\s)$escapedHost(\s|$)") {
            $script:updated = $true
            "$TargetIp`t$HostName"
        } else {
            $_
        }
    }
)

if (-not $updated) {
    $after += "$TargetIp`t$HostName"
}

Set-Content -LiteralPath $hostsPath -Value $after -Encoding ASCII
Clear-DnsClientCache

$resolution = Resolve-DnsName $HostName -Type A -ErrorAction Stop |
    Select-Object Name, Type, IPAddress, TTL, Section

$evidence = [ordered]@{
    schema = "local_hosts_control_domain_v1"
    executed_at = (Get-Date).ToString("o")
    hosts_file = $hostsPath
    backup = $backupPath
    host_name = $HostName
    target_ip = $TargetIp
    existing_entry_updated = $updated
    resolved_after = @($resolution)
}

$evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidencePath -Encoding UTF8
Write-Host "Hosts atualizado: $HostName -> $TargetIp"
Write-Host "Backup: $backupPath"
Write-Host "Evidencia: $evidencePath"
