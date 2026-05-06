param(
    [string]$DnsServer = "DNS-BRVIDA.brasilvida.local",
    [string]$DnsServerIp = "192.168.25.112",
    [string]$ZoneName = "controle.brasilvida.app.br",
    [string]$TargetIp = "192.168.25.33",
    [switch]$PauseOnExit
)

$ErrorActionPreference = "Stop"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidencePath = Join-Path $PSScriptRoot "internal-dns-split-horizon-execution-$stamp.json"
$transcriptPath = Join-Path $PSScriptRoot "internal-dns-split-horizon-execution-$stamp.log"
$ttl = New-TimeSpan -Minutes 5

$evidence = [ordered]@{
    schema = "internal_dns_split_horizon_execution_v1"
    target = $ZoneName
    executed_at = (Get-Date).ToString("o")
    frontend_repository_touched = $false
    public_dns_touched = $false
    hosts_file_touched = $false
    dns_server = $DnsServer
    dns_server_ip = $DnsServerIp
    desired_record = [ordered]@{
        zone = $ZoneName
        name = "@"
        type = "A"
        value = $TargetIp
        ttl = "00:05:00"
    }
    precheck = @()
    remote_execution = @()
    validation = @()
    rollback = @(
        "Remove-DnsServerZone -Name `"$ZoneName`" -Force",
        "Clear-DnsServerCache -Force"
    )
    change_applied = $false
    closure = "not_evaluated"
    error = $null
}

function Add-EvidenceItem {
    param(
        [string]$Bucket,
        [hashtable]$Item
    )
    $evidence[$Bucket] += [pscustomobject]$Item
}

function Save-Evidence {
    $evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $evidencePath -Encoding UTF8
}

function Invoke-HttpProbe {
    param(
        [string]$Uri,
        [switch]$NoRedirect
    )
    try {
        $params = @{
            Uri = $Uri
            TimeoutSec = 20
            Headers = @{
                "Cache-Control" = "no-cache"
                "Pragma" = "no-cache"
            }
            ErrorAction = "Stop"
            UseBasicParsing = $true
        }
        if ($NoRedirect) {
            $params.MaximumRedirection = 0
        }
        $response = Invoke-WebRequest @params
        $content = [string]$response.Content
        return [ordered]@{
            uri = $Uri
            ok = $true
            status = [int]$response.StatusCode
            server = (($response.Headers["Server"]) -join ",")
            content_type = (($response.Headers["Content-Type"]) -join ",")
            location = (($response.Headers["Location"]) -join ",")
            title = ([regex]::Match($content, "<title>(.*?)</title>", "IgnoreCase")).Groups[1].Value
            contains_fw_login = $content.Contains("fw - Login")
            contains_gateway_csrf = $content.Contains("csrf-magic.js")
            length = $content.Length
        }
    } catch {
        $status = $null
        $server = $null
        $location = $null
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            $server = (($_.Exception.Response.Headers["Server"]) -join ",")
            $location = (($_.Exception.Response.Headers["Location"]) -join ",")
        }
        return [ordered]@{
            uri = $Uri
            ok = $false
            status = $status
            server = $server
            location = $location
            error = $_.Exception.Message
        }
    }
}

try {
    Start-Transcript -LiteralPath $transcriptPath | Out-Null

    Add-EvidenceItem -Bucket "precheck" -Item @{
        step = "local_identity"
        value = (whoami)
    }

    $currentAnswer = Resolve-DnsName $ZoneName -Server $DnsServerIp -Type A -ErrorAction Stop |
        Select-Object Name, Type, IPAddress, TTL, Section
    Add-EvidenceItem -Bucket "precheck" -Item @{
        step = "current_internal_answer"
        value = $currentAnswer
    }

    $currentSoa = Resolve-DnsName $ZoneName -Server $DnsServerIp -Type SOA -ErrorAction SilentlyContinue |
        Select-Object Name, Type, PrimaryServer, NameAdministrator, SerialNumber, TTL, Section
    Add-EvidenceItem -Bucket "precheck" -Item @{
        step = "current_authority"
        value = $currentSoa
    }

    Write-Host ""
    Write-Host "Credencial administrativa do DNS interno sera solicitada pelo Windows." -ForegroundColor Cyan
    Write-Host "Destino: $DnsServer"
    Write-Host "Mudanca: $ZoneName -> $TargetIp"
    Write-Host ""
    $credential = Get-Credential -Message "Credencial administrativa para $DnsServer"
    if ($null -eq $credential) {
        throw "Credencial administrativa nao informada. Nenhuma mudanca foi aplicada."
    }

    $remoteResult = Invoke-Command -ComputerName $DnsServer -Credential $credential -ArgumentList $ZoneName, $TargetIp, $ttl -ScriptBlock {
        param($RemoteZoneName, $RemoteTargetIp, $RemoteTtl)
        $ErrorActionPreference = "Stop"
        Import-Module DnsServer -ErrorAction Stop

        $result = [ordered]@{
            hostname = hostname
            identity = whoami
            zone_existed_before = $false
            existing_records_before = @()
            created_zone = $false
            created_record = $false
            records_after = @()
        }

        $existingZone = Get-DnsServerZone -Name $RemoteZoneName -ErrorAction SilentlyContinue
        if ($existingZone) {
            $result.zone_existed_before = $true
            $records = @(Get-DnsServerResourceRecord -ZoneName $RemoteZoneName -Name "@" -RRType A -ErrorAction SilentlyContinue)
            $result.existing_records_before = @($records | ForEach-Object {
                [ordered]@{
                    host_name = $_.HostName
                    record_type = $_.RecordType
                    ipv4 = $_.RecordData.IPv4Address.IPAddressToString
                    ttl = $_.TimeToLive.ToString()
                }
            })

            $matching = @($records | Where-Object { $_.RecordData.IPv4Address.IPAddressToString -eq $RemoteTargetIp })
            if ($matching.Count -gt 0 -and $records.Count -eq $matching.Count) {
                $result.created_zone = $false
                $result.created_record = $false
            } else {
                throw "Zona '$RemoteZoneName' ja existe com registro A divergente ou ambiguo. Abortado para nao tocar em registros existentes."
            }
        } else {
            Add-DnsServerPrimaryZone -Name $RemoteZoneName -ReplicationScope "Domain" -DynamicUpdate None
            $result.created_zone = $true
            Add-DnsServerResourceRecordA -ZoneName $RemoteZoneName -Name "@" -IPv4Address $RemoteTargetIp -TimeToLive $RemoteTtl
            $result.created_record = $true
        }

        Clear-DnsServerCache -Force

        $recordsAfter = @(Get-DnsServerResourceRecord -ZoneName $RemoteZoneName -Name "@" -RRType A -ErrorAction Stop)
        $result.records_after = @($recordsAfter | ForEach-Object {
            [ordered]@{
                host_name = $_.HostName
                record_type = $_.RecordType
                ipv4 = $_.RecordData.IPv4Address.IPAddressToString
                ttl = $_.TimeToLive.ToString()
            }
        })

        return [pscustomobject]$result
    }

    Add-EvidenceItem -Bucket "remote_execution" -Item @{
        step = "apply_split_dns"
        value = $remoteResult
    }

    $evidence.change_applied = [bool]($remoteResult.created_zone -or $remoteResult.created_record)

    Clear-DnsClientCache
    Start-Sleep -Seconds 2

    $serverAnswer = Resolve-DnsName $ZoneName -Server $DnsServerIp -Type A -ErrorAction Stop |
        Select-Object Name, Type, IPAddress, TTL, Section
    Add-EvidenceItem -Bucket "validation" -Item @{
        step = "resolve_via_internal_dns"
        value = $serverAnswer
    }

    $clientAnswer = Resolve-DnsName $ZoneName -Type A -ErrorAction Stop |
        Select-Object Name, Type, IPAddress, TTL, Section
    Add-EvidenceItem -Bucket "validation" -Item @{
        step = "resolve_via_client_dns"
        value = $clientAnswer
    }

    Add-EvidenceItem -Bucket "validation" -Item @{
        step = "http_no_redirect_root"
        value = (Invoke-HttpProbe -Uri "http://$ZoneName/" -NoRedirect)
    }
    Add-EvidenceItem -Bucket "validation" -Item @{
        step = "http_follow_root"
        value = (Invoke-HttpProbe -Uri "http://$ZoneName/")
    }
    Add-EvidenceItem -Bucket "validation" -Item @{
        step = "https_index"
        value = (Invoke-HttpProbe -Uri "https://$ZoneName/index.html")
    }
    Add-EvidenceItem -Bucket "validation" -Item @{
        step = "https_manifest"
        value = (Invoke-HttpProbe -Uri "https://$ZoneName/asset-manifest.json")
    }

    $serverIps = @($serverAnswer | ForEach-Object { $_.IPAddress })
    $clientIps = @($clientAnswer | ForEach-Object { $_.IPAddress })
    $httpEvidence = @($evidence.validation | Where-Object { $_.step -like "http_*" -or $_.step -like "https_*" } | ForEach-Object { $_.value })
    $caddySeen = @($httpEvidence | Where-Object { $_.server -match "Caddy" -or $_.server -match "controle-treinamentos" }).Count -gt 0
    $fwSeen = @($httpEvidence | Where-Object { $_.contains_fw_login -eq $true -or $_.contains_gateway_csrf -eq $true -or $_.server -match "nginx" }).Count -gt 0

    if (($serverIps -contains $TargetIp) -and ($clientIps -contains $TargetIp) -and $caddySeen -and -not $fwSeen) {
        $evidence.closure = "fechado"
    } else {
        $evidence.closure = "nao_fechado"
    }
} catch {
    $evidence.error = $_.Exception.Message
    $evidence.closure = "bloqueado"
    Write-Error $_
} finally {
    try {
        Stop-Transcript | Out-Null
    } catch {
    }
    Save-Evidence
    Write-Host ""
    Write-Host "Evidencia: $evidencePath" -ForegroundColor Cyan
    Write-Host "Transcript: $transcriptPath" -ForegroundColor Cyan
    Write-Host "Closure: $($evidence.closure)" -ForegroundColor Cyan
    if ($PauseOnExit) {
        Read-Host "Pressione ENTER para fechar esta janela"
    }
}
