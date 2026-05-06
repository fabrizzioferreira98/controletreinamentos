[CmdletBinding()]
param(
    [string]$NgrokExePath,
    [string]$NgrokConfigPath = "C:\srv\controle-treinamentos\ngrok\ngrok.yml",
    [switch]$Install,
    [switch]$Start
)

$ErrorActionPreference = "Stop"

function Resolve-NgrokExe {
    param(
        [string]$ExplicitPath
    )

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "Ngrok nao encontrado em: $ExplicitPath"
        }
        return (Resolve-Path $ExplicitPath).Path
    }

    $command = Get-Command ngrok.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Ngrok nao encontrado no PATH. Instale o ngrok ou informe -NgrokExePath."
}

$resolvedNgrokExe = Resolve-NgrokExe -ExplicitPath $NgrokExePath

if (-not (Test-Path $NgrokConfigPath)) {
    throw "Arquivo de configuracao do ngrok nao encontrado: $NgrokConfigPath"
}

& $resolvedNgrokExe config check --config $NgrokConfigPath
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao validar a configuracao do ngrok."
}

Write-Host "Configuracao do ngrok validada em $NgrokConfigPath"

if ($Install) {
    & $resolvedNgrokExe service install --config $NgrokConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar o servico do ngrok."
    }
    Write-Host "Servico do ngrok instalado."
}

if ($Start) {
    & $resolvedNgrokExe service start
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao iniciar o servico do ngrok."
    }
    Write-Host "Servico do ngrok iniciado."
}
