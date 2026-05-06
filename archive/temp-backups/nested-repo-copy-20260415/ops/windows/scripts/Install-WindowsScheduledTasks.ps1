[CmdletBinding()]
param(
    [string]$RootDir = "C:\srv\controle-treinamentos",
    [string]$RunAsUser = "SYSTEM",
    [int]$WorkerProdIntervalMinutes = 5,
    [int]$WorkerHmlIntervalMinutes = 15,
    [string]$WorkerProdStartTime = "00:00",
    [string]$WorkerHmlStartTime = "00:02",
    [int]$BackupProdIntervalHours = 6,
    [string]$BackupProdStartTime = "00:10",
    [string]$BackupHmlStartTime = "02:00",
    [string]$DbCheckProdStartTime = "03:00",
    [string]$DbCheckHmlStartTime = "03:15"
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Schtasks {
    param(
        [string[]]$Arguments,
        [switch]$IgnoreFailure,
        [switch]$Silent
    )

    if ($Silent) {
        & schtasks.exe @Arguments 2>$null | Out-Null
    }
    else {
        & schtasks.exe @Arguments
    }
    $exitCode = $LASTEXITCODE
    if (-not $IgnoreFailure -and $exitCode -ne 0) {
        $joined = $Arguments -join " "
        throw "schtasks.exe falhou com codigo ${exitCode}: $joined"
    }
}

function New-TaskCommand {
    param(
        [string]$ScriptPath
    )

    $powerShellExe = Join-Path $PSHOME "powershell.exe"
    return "`"$powerShellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
}

function Register-ManagedTask {
    param(
        [string]$TaskName,
        [string]$ScriptPath,
        [string[]]$ScheduleArguments
    )

    if (-not (Test-Path $ScriptPath)) {
        throw "Script da tarefa nao encontrado: $ScriptPath"
    }

    Invoke-Schtasks -Arguments @("/Delete", "/TN", $TaskName, "/F") -IgnoreFailure -Silent

    $taskCommand = New-TaskCommand -ScriptPath $ScriptPath
    $arguments = @("/Create", "/TN", $TaskName) + $ScheduleArguments + @("/TR", $taskCommand, "/RU", $RunAsUser, "/RL", "HIGHEST", "/F")
    Invoke-Schtasks -Arguments $arguments
}

$taskDefinitions = @(
    @{
        Name = "CT-Worker-Prod"
        Script = Join-Path $RootDir "tasks\worker-prod.ps1"
        Schedule = @("/SC", "MINUTE", "/MO", "$WorkerProdIntervalMinutes", "/ST", $WorkerProdStartTime)
    },
    @{
        Name = "CT-Worker-Hml"
        Script = Join-Path $RootDir "tasks\worker-hml.ps1"
        Schedule = @("/SC", "MINUTE", "/MO", "$WorkerHmlIntervalMinutes", "/ST", $WorkerHmlStartTime)
    },
    @{
        Name = "CT-Backup-Prod"
        Script = Join-Path $RootDir "tasks\backup-prod.ps1"
        Schedule = @("/SC", "HOURLY", "/MO", "$BackupProdIntervalHours", "/ST", $BackupProdStartTime)
    },
    @{
        Name = "CT-Backup-Hml"
        Script = Join-Path $RootDir "tasks\backup-hml.ps1"
        Schedule = @("/SC", "DAILY", "/ST", $BackupHmlStartTime)
    },
    @{
        Name = "CT-DbCheck-Prod"
        Script = Join-Path $RootDir "tasks\dbcheck-prod.ps1"
        Schedule = @("/SC", "DAILY", "/ST", $DbCheckProdStartTime)
    },
    @{
        Name = "CT-DbCheck-Hml"
        Script = Join-Path $RootDir "tasks\dbcheck-hml.ps1"
        Schedule = @("/SC", "DAILY", "/ST", $DbCheckHmlStartTime)
    }
)

if (-not (Test-IsAdministrator)) {
    throw "Execute este script em um PowerShell aberto como Administrador."
}

foreach ($task in $taskDefinitions) {
    Register-ManagedTask -TaskName $task.Name -ScriptPath $task.Script -ScheduleArguments $task.Schedule
}

foreach ($task in $taskDefinitions) {
    Invoke-Schtasks -Arguments @("/Query", "/FO", "LIST", "/TN", $task.Name)
}
