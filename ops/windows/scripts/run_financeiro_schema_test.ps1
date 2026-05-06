[CmdletBinding()]
param(
    [string]$DatabaseUrl = "",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$Database = "",
    [string]$User = "",
    [string]$PgBinDir = "C:\Program Files\PostgreSQL\15\bin",
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [switch]$CreateDatabase,
    [switch]$Cleanup,
    [string]$ConfirmCleanup = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not [System.IO.Path]::IsPathRooted($PythonPath)) {
    $PythonPath = Join-Path $RepoRoot $PythonPath
}

function ConvertTo-MaskedDatabaseUrl {
    param([string]$Value)

    if (-not $Value) {
        return ""
    }

    try {
        $uri = [System.Uri]$Value
        $authority = $uri.Authority
        if ($authority -match "@") {
            $userInfo = $authority.Split("@")[0]
            $hostInfo = $authority.Substring($userInfo.Length + 1)
            $userName = $userInfo.Split(":")[0]
            $authority = "$userName`:***@$hostInfo"
        }
        return "$($uri.Scheme)://$authority$($uri.AbsolutePath)"
    }
    catch {
        return "<invalid-url>"
    }
}

function Get-DatabaseNameFromUrl {
    param([string]$Value)

    try {
        $uri = [System.Uri]$Value
        return $uri.AbsolutePath.Trim("/")
    }
    catch {
        throw "DATABASE_URL invalida."
    }
}

function Get-ConnectionPartsFromUrl {
    param([string]$Value)

    try {
        $uri = [System.Uri]$Value
        $userName = ""
        if ($uri.UserInfo) {
            $userName = [System.Uri]::UnescapeDataString($uri.UserInfo.Split(":")[0])
        }
        $portValue = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
        return @{
            HostName = $uri.Host
            Port = $portValue
            User = $userName
        }
    }
    catch {
        throw "DATABASE_URL invalida."
    }
}

function Assert-SafeTestDatabaseName {
    param([string]$DatabaseName)

    $normalized = ($DatabaseName -as [string]).Trim().ToLowerInvariant()
    if (-not $normalized) {
        throw "Nome do banco de teste ausente."
    }
    if ($normalized -notlike "*test*") {
        throw "Banco recusado: o nome precisa conter 'test'. Valor recebido: $DatabaseName"
    }
    if ($normalized -in @("ct_local", "ct_hml", "ct_prod", "postgres", "template0", "template1")) {
        throw "Banco recusado por politica operacional: $DatabaseName"
    }
}

function Assert-ToolExists {
    param([string]$PathValue, [string]$Label)

    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "$Label nao encontrado em $PathValue"
    }
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou com codigo ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

if (-not $DatabaseUrl) {
    if (-not $Database -or -not $User) {
        throw "Informe -DatabaseUrl ou os parametros -HostName, -Port, -Database e -User."
    }
    Assert-SafeTestDatabaseName -DatabaseName $Database
    $DatabaseUrl = "postgresql://$User@$HostName`:$Port/$Database"
}

$targetDatabase = Get-DatabaseNameFromUrl -Value $DatabaseUrl
Assert-SafeTestDatabaseName -DatabaseName $targetDatabase
$connectionParts = Get-ConnectionPartsFromUrl -Value $DatabaseUrl
$targetHost = if ($connectionParts.HostName) { $connectionParts.HostName } else { $HostName }
$targetPort = if ($connectionParts.Port) { [int]$connectionParts.Port } else { $Port }
$targetUser = if ($User) { $User } else { [string]$connectionParts.User }

$lowerUrl = $DatabaseUrl.ToLowerInvariant()
foreach ($forbidden in @("ct_local", "ct_hml", "ct_prod")) {
    if ($lowerUrl.Contains($forbidden)) {
        throw "DATABASE_URL recusada: contem alvo proibido '$forbidden'."
    }
}

$maskedUrl = ConvertTo-MaskedDatabaseUrl -Value $DatabaseUrl
Write-Host "Financeiro schema bootstrap test"
Write-Host "DATABASE_URL=$maskedUrl"

$createdbPath = Join-Path $PgBinDir "createdb.exe"
$dropdbPath = Join-Path $PgBinDir "dropdb.exe"
Assert-ToolExists -PathValue $PythonPath -Label "Python"

if ($CreateDatabase) {
    Assert-ToolExists -PathValue $createdbPath -Label "createdb.exe"
    if (-not $targetUser) {
        throw "-CreateDatabase exige -User."
    }
    Write-Host "Criando banco de teste: $targetDatabase"
    Invoke-NativeCommand -FilePath $createdbPath -Arguments @(
        "-h", $targetHost,
        "-p", [string]$targetPort,
        "-U", $targetUser,
        "--no-password",
        $targetDatabase
    )
}

$previousDatabaseUrl = $env:DATABASE_URL
try {
    $env:DATABASE_URL = $DatabaseUrl
    Push-Location $RepoRoot
    try {
        Invoke-NativeCommand -FilePath $PythonPath -Arguments @(
            "-m",
            "pytest",
            "tests\integration\test_financeiro_schema_bootstrap.py",
            "-q"
        )
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}

if ($Cleanup) {
    Assert-SafeTestDatabaseName -DatabaseName $targetDatabase
    if ($ConfirmCleanup -ne "drop:$targetDatabase") {
        throw "Cleanup recusado. Informe -ConfirmCleanup `"drop:$targetDatabase`"."
    }
    if (-not $targetUser) {
        throw "-Cleanup exige -User."
    }
    Assert-ToolExists -PathValue $dropdbPath -Label "dropdb.exe"
    Write-Host "Removendo banco de teste: $targetDatabase"
    Invoke-NativeCommand -FilePath $dropdbPath -Arguments @(
        "-h", $targetHost,
        "-p", [string]$targetPort,
        "-U", $targetUser,
        "--no-password",
        "--if-exists",
        $targetDatabase
    )
}
