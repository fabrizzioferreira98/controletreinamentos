[CmdletBinding()]
param(
    [string]$ServiceName = "postgresql-x64-15",
    [string]$PgBinDir = "C:\Program Files\PostgreSQL\15\bin",
    [string]$PgDataDir = "C:\Program Files\PostgreSQL\15\data",
    [string]$ResultPath = "C:\apps\controle-treinamentos\ops\artifacts\admin\pg_reset_result.json"
)

$ErrorActionPreference = "Stop"

function Set-LocalPgHbaMode {
    param(
        [ValidateSet("trust", "scram-sha-256")]
        [string]$Mode,
        [string]$PgHbaPath
    )

    $content = Get-Content -LiteralPath $PgHbaPath
    $updated = foreach ($line in $content) {
        if ($line -match '^(\s*)local\s+all\s+all\s+') {
            "local   all             all                                     $Mode"
        }
        elseif ($line -match '^(\s*)host\s+all\s+all\s+127\.0\.0\.1/32\s+') {
            "host    all             all             127.0.0.1/32            $Mode"
        }
        elseif ($line -match '^(\s*)host\s+all\s+all\s+::1/128\s+') {
            "host    all             all             ::1/128                 $Mode"
        }
        else {
            $line
        }
    }
    Set-Content -LiteralPath $PgHbaPath -Value $updated -Encoding ascii
}

function Wait-PgReady {
    param(
        [string]$PgBinDirValue
    )

    for ($i = 0; $i -lt 30; $i++) {
        & (Join-Path $PgBinDirValue "pg_isready.exe") -h 127.0.0.1 -p 5432 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "PostgreSQL nao ficou pronto a tempo."
}

function New-SafeSecret {
    param(
        [int]$Length = 28
    )

    $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%*+-_=.:".ToCharArray()
    $bytes = New-Object byte[] ($Length)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return (-join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] }))
}

$pgHbaPath = Join-Path $PgDataDir "pg_hba.conf"
if (-not (Test-Path $pgHbaPath)) {
    throw "pg_hba.conf nao encontrado em $pgHbaPath"
}

$resultDir = Split-Path -Parent $ResultPath
New-Item -ItemType Directory -Force -Path $resultDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $PgDataDir ("pg_hba.conf.codex-backup-" + $timestamp + ".bak")
$sqlPath = Join-Path $env:TEMP ("ct_reset_" + $timestamp + ".sql")

$postgresPassword = New-SafeSecret
$prodPassword = New-SafeSecret
$hmlPassword = New-SafeSecret

$result = [ordered]@{
    success = $false
    backup_path = $backupPath
    validation = ""
    postgres_user = "postgres"
    postgres_password = $postgresPassword
    prod_db = "ct_prod"
    prod_user = "ct_prod_user"
    prod_password = $prodPassword
    hml_db = "ct_hml"
    hml_user = "ct_hml_user"
    hml_password = $hmlPassword
    error = ""
}

$sql = @'
ALTER USER postgres WITH PASSWORD '$postgresPassword';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ct_prod_user') THEN
        CREATE ROLE ct_prod_user LOGIN PASSWORD '$prodPassword';
    ELSE
        ALTER ROLE ct_prod_user WITH LOGIN PASSWORD '$prodPassword';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ct_hml_user') THEN
        CREATE ROLE ct_hml_user LOGIN PASSWORD '$hmlPassword';
    ELSE
        ALTER ROLE ct_hml_user WITH LOGIN PASSWORD '$hmlPassword';
    END IF;
END
$$;
SELECT 'CREATE DATABASE ct_prod OWNER ct_prod_user'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'ct_prod')\gexec
SELECT 'CREATE DATABASE ct_hml OWNER ct_hml_user'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'ct_hml')\gexec
ALTER DATABASE ct_prod OWNER TO ct_prod_user;
ALTER DATABASE ct_hml OWNER TO ct_hml_user;
GRANT ALL PRIVILEGES ON DATABASE ct_prod TO ct_prod_user;
GRANT ALL PRIVILEGES ON DATABASE ct_hml TO ct_hml_user;
'@
$sql = $sql.Replace('$postgresPassword', $postgresPassword).Replace('$prodPassword', $prodPassword).Replace('$hmlPassword', $hmlPassword)

Copy-Item -LiteralPath $pgHbaPath -Destination $backupPath -Force
Set-Content -LiteralPath $sqlPath -Value $sql -Encoding ascii

try {
    Set-LocalPgHbaMode -Mode "trust" -PgHbaPath $pgHbaPath
    Restart-Service -Name $ServiceName -Force
    Wait-PgReady -PgBinDirValue $PgBinDir

    & (Join-Path $PgBinDir "psql.exe") -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1 -f $sqlPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao executar SQL de reset no PostgreSQL. Codigo: $LASTEXITCODE"
    }

    Copy-Item -LiteralPath $backupPath -Destination $pgHbaPath -Force
    Restart-Service -Name $ServiceName -Force
    Wait-PgReady -PgBinDirValue $PgBinDir

    $env:PGPASSWORD = $postgresPassword
    $validation = & (Join-Path $PgBinDir "psql.exe") -h 127.0.0.1 -U postgres -d postgres -tAc "SELECT current_user || '|' || current_database();"
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

    $result.success = $true
    $result.validation = ($validation | Out-String).Trim()
}
catch {
    $result.error = $_.Exception.Message

    try {
        if (Test-Path $backupPath) {
            Copy-Item -LiteralPath $backupPath -Destination $pgHbaPath -Force
            Restart-Service -Name $ServiceName -Force
            Wait-PgReady -PgBinDirValue $PgBinDir
        }
    }
    catch {
        $result.error = $result.error + " | restore_error=" + $_.Exception.Message
    }
}
finally {
    Remove-Item -LiteralPath $sqlPath -Force -ErrorAction SilentlyContinue
    $result | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $ResultPath -Encoding ascii
}

Get-Content -LiteralPath $ResultPath
