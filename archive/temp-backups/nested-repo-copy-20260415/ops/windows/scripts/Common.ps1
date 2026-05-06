[CmdletBinding()]
param()

Set-StrictMode -Version Latest

function Get-ControleRepoRoot {
    param(
        [string]$RepoRoot
    )

    if ($RepoRoot) {
        return (Resolve-Path -Path $RepoRoot).Path
    }

    return (Resolve-Path -Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-ControlePythonExe {
    param(
        [string]$RepoRoot,
        [string]$PythonExe
    )

    if ($PythonExe) {
        return $PythonExe
    }

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Nenhum interpretador Python encontrado. Informe -PythonExe explicitamente."
}

function Get-ControleDefaultEnvFile {
    param(
        [string]$RepoRoot,
        [ValidateSet("prod", "hml")]
        [string]$EnvironmentName
    )

    return Join-Path $RepoRoot "ops\windows\env\$EnvironmentName.env.example"
}

function Import-ControleEnvFile {
    param(
        [string]$EnvFile
    )

    if (-not (Test-Path $EnvFile)) {
        throw "Arquivo de ambiente nao encontrado: $EnvFile"
    }

    foreach ($rawLine in Get-Content -Path $EnvFile) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        if (-not $name) {
            continue
        }

        $value = ""
        if ($parts.Count -gt 1) {
            $value = $parts[1]
        }

        [System.Environment]::SetEnvironmentVariable($name, $value)
    }
}
