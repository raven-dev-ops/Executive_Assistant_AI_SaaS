[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Instance,

    [Parameter(Mandatory = $true)]
    [string]$Database,

    [Parameter(Mandatory = $true)]
    [string]$Bucket,

    [string]$ProjectId,

    [string]$Prefix = "cloudsql",

    [switch]$Offload,

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

$startedAtUtc = (Get-Date).ToUniversalTime()
$timestamp = $startedAtUtc.ToString("yyyyMMdd-HHmmss'Z'")
$fileName = "$Instance-$Database-$timestamp.sql.gz"
$uri = "gs://$Bucket/$Prefix/$Instance/$Database/$fileName"

$exportArgs = @(
    "sql", "export", "sql", $Instance, $uri,
    "--database=$Database",
    "--async"
)
if ($Offload) {
    $exportArgs += "--offload"
}

Write-Host "Exporting Cloud SQL database to: $uri"
$startResult = Invoke-GcloudJson -Arguments $exportArgs

if ($DryRun) {
    return
}

$operationId = $null
if ($startResult -and $startResult.name) {
    $operationId = "$($startResult.name)"
}
elseif ($startResult -and $startResult.operation) {
    $operationId = "$($startResult.operation)"
}
elseif ($startResult -and $startResult.id) {
    $operationId = "$($startResult.id)"
}
if (-not $operationId) {
    throw "Could not determine Cloud SQL operation id from export output."
}

Write-Host "Waiting for operation: $operationId"
$deadline = (Get-Date).ToUniversalTime().AddSeconds($TimeoutSeconds)
while ($true) {
    $op = Invoke-GcloudJson -Arguments @(
        "sql", "operations", "describe", $operationId,
        "--instance=$Instance"
    )
    if ($op -and $op.status -eq "DONE") {
        if ($op.error -and $op.error.errors) {
            $errs = ($op.error.errors | ConvertTo-Json -Depth 10)
            throw "Cloud SQL export failed: $errs"
        }
        $finishedAtUtc = (Get-Date).ToUniversalTime()
        $elapsedMinutes = [Math]::Round(($finishedAtUtc - $startedAtUtc).TotalMinutes, 1)
        Write-Host "Export completed at $($finishedAtUtc.ToString('o'))"
        Write-Host "Elapsed (minutes) = $elapsedMinutes"
        $finalOp = $op
        break
    }
    if ((Get-Date).ToUniversalTime() -gt $deadline) {
        throw "Timed out waiting for operation $operationId"
    }
    Start-Sleep -Seconds 10
}

$evidence = [ordered]@{
    action        = "cloudsql_export_sql"
    instance      = $Instance
    database      = $Database
    bucket        = $Bucket
    uri           = $uri
    started_at_utc = $startedAtUtc.ToString("o")
    offload       = [bool]$Offload
    timeout_seconds = $TimeoutSeconds
    operation_id  = $operationId
    operation_result = $finalOp
}

if ($OutputJson) {
    ($evidence | ConvertTo-Json -Depth 10) | Out-File -FilePath $OutputJson -Encoding utf8
    Write-Host "Wrote evidence JSON: $OutputJson"
}
