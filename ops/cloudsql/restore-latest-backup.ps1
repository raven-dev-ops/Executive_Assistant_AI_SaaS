[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupInstance,

    [Parameter(Mandatory = $true)]
    [string]$RestoreInstance,

    [string]$ProjectId,

    [string]$BackupProject,

    [string]$BackupId,

    [int]$PollSeconds = 10,

    [int]$TimeoutSeconds = 3600,

    [string]$OutputJson,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-GcloudJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $fullArgs = @()
    if ($ProjectId) {
        $fullArgs += "--project=$ProjectId"
    }
    $fullArgs += $Arguments
    $fullArgs += "--format=json"

    $cmd = "gcloud " + ($fullArgs -join " ")
    if ($DryRun) {
        Write-Host $cmd
        return $null
    }

    $out = (& gcloud @fullArgs 2>&1) | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed: $out"
    }
    if (-not $out.Trim()) {
        return $null
    }
    return $out | ConvertFrom-Json
}

function Get-BackupTimestampUtc {
    param($Backup)
    $ts = $null
    if ($Backup.endTime) {
        $ts = $Backup.endTime
    }
    elseif ($Backup.startTime) {
        $ts = $Backup.startTime
    }
    if (-not $ts) {
        return $null
    }
    return [DateTime]::Parse($ts).ToUniversalTime()
}

function Wait-CloudSqlOperation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OperationId
    )

    $deadline = (Get-Date).ToUniversalTime().AddSeconds($TimeoutSeconds)
    while ($true) {
        $op = Invoke-GcloudJson -Arguments @(
            "sql", "operations", "describe", $OperationId,
            "--instance=$RestoreInstance"
        )

        if ($op -and $op.status -eq "DONE") {
            if ($op.error -and $op.error.errors) {
                $errs = ($op.error.errors | ConvertTo-Json -Depth 10)
                throw "Cloud SQL operation failed: $errs"
            }
            return $op
        }

        if ((Get-Date).ToUniversalTime() -gt $deadline) {
            throw "Timed out waiting for operation $OperationId"
        }
        Start-Sleep -Seconds $PollSeconds
    }
}

if ($DryRun) {
    Write-Host "DryRun: printing gcloud commands only (no API calls)."
    Write-Host ""
    Write-Host "List backups:"
    Invoke-GcloudJson -Arguments @(
        "sql", "backups", "list",
        "--instance=$BackupInstance",
        "--filter=status=SUCCESS"
    ) | Out-Null

    if (-not $BackupId) {
        Write-Host ""
        Write-Host "Re-run with -BackupId <id> to print the restore command, or run without -DryRun to auto-select the latest backup."
        return
    }

    Write-Host ""
    Write-Host "Restore backup:"
    $restoreArgsDry = @(
        "sql", "backups", "restore", $BackupId,
        "--restore-instance=$RestoreInstance",
        "--backup-instance=$BackupInstance",
        "--timeout=$TimeoutSeconds",
        "--async"
    )
    if ($BackupProject) {
        $restoreArgsDry += "--backup-project=$BackupProject"
    }
    Invoke-GcloudJson -Arguments $restoreArgsDry | Out-Null
    return
}

$backups = Invoke-GcloudJson -Arguments @(
    "sql", "backups", "list",
    "--instance=$BackupInstance",
    "--filter=status=SUCCESS"
)
if (-not $backups) {
    throw "No backups found for instance '$BackupInstance' (filter status=SUCCESS)."
}

$selectedBackup = $null
if ($BackupId) {
    $selectedBackup = $backups | Where-Object { "$($_.id)" -eq "$BackupId" } | Select-Object -First 1
    if (-not $selectedBackup) {
        throw "BackupId '$BackupId' not found in backups list for '$BackupInstance'."
    }
}
else {
    $selectedBackup = $backups |
        Sort-Object { (Get-BackupTimestampUtc $_) } -Descending |
        Select-Object -First 1
}

$selectedBackupId = "$($selectedBackup.id)"
$backupTimestampUtc = Get-BackupTimestampUtc $selectedBackup

Write-Host "Selected backup:"
Write-Host "  backup_instance = $BackupInstance"
Write-Host "  backup_id       = $selectedBackupId"
Write-Host "  backup_time_utc  = $($backupTimestampUtc.ToString('o'))"
Write-Host "  restore_instance = $RestoreInstance"

$nowUtc = (Get-Date).ToUniversalTime()
$rpoMinutes = $null
if ($backupTimestampUtc) {
    $rpoMinutes = [Math]::Round(($nowUtc - $backupTimestampUtc).TotalMinutes, 1)
    Write-Host "Estimated RPO (minutes) = $rpoMinutes"
}

$restoreArgs = @(
    "sql", "backups", "restore", $selectedBackupId,
    "--restore-instance=$RestoreInstance",
    "--backup-instance=$BackupInstance",
    "--timeout=$TimeoutSeconds",
    "--async"
)
if ($BackupProject) {
    $restoreArgs += "--backup-project=$BackupProject"
}

$startedAtUtc = (Get-Date).ToUniversalTime()
Write-Host "Starting restore at $($startedAtUtc.ToString('o')) ..."
$restoreStart = Invoke-GcloudJson -Arguments $restoreArgs

$operationId = $null
if ($restoreStart -and $restoreStart.name) {
    $operationId = "$($restoreStart.name)"
}
elseif ($restoreStart -and $restoreStart.operation) {
    $operationId = "$($restoreStart.operation)"
}
elseif ($restoreStart -and $restoreStart.id) {
    $operationId = "$($restoreStart.id)"
}

if (-not $operationId) {
    throw "Could not determine Cloud SQL operation id from restore output."
}

Write-Host "Waiting for operation: $operationId"
$finalOp = Wait-CloudSqlOperation -OperationId $operationId
$finishedAtUtc = (Get-Date).ToUniversalTime()

$rtoMinutes = [Math]::Round(($finishedAtUtc - $startedAtUtc).TotalMinutes, 1)
Write-Host "Restore completed at $($finishedAtUtc.ToString('o'))"
Write-Host "Measured RTO (minutes) = $rtoMinutes"

$evidence = [ordered]@{
    action           = "cloudsql_restore_latest_backup"
    backup_instance  = $BackupInstance
    restore_instance = $RestoreInstance
    backup_project   = $BackupProject
    backup_id        = $selectedBackupId
    backup_time_utc  = if ($backupTimestampUtc) { $backupTimestampUtc.ToString("o") } else { $null }
    rpo_minutes      = $rpoMinutes
    started_at_utc   = $startedAtUtc.ToString("o")
    finished_at_utc  = $finishedAtUtc.ToString("o")
    rto_minutes      = $rtoMinutes
    operation_id     = $operationId
    operation_result = $finalOp
}

if ($OutputJson) {
    ($evidence | ConvertTo-Json -Depth 10) | Out-File -FilePath $OutputJson -Encoding utf8
    Write-Host "Wrote evidence JSON: $OutputJson"
}
