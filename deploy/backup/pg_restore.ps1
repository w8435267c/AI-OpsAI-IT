[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$DumpPath,
    [Parameter(Mandatory)] [string]$ManifestPath,
    [Parameter(Mandatory)] [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.-]*$')] [string]$TargetContainer,
    [Parameter(Mandatory)] [ValidatePattern('^opsai_backup_restore_[a-z0-9_]+$')] [string]$TargetDatabase,
    [Parameter(Mandatory)] [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]*$')] [string]$DatabaseUser
)

$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE): docker $($Arguments -join ' ')" }
}

if (-not (Test-Path -LiteralPath $DumpPath) -or -not (Test-Path -LiteralPath $ManifestPath)) {
    throw 'The backup file or manifest file does not exist.'
}
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifest.schema -ne 'opsai.postgresql-backup-manifest/v1' -or $manifest.format -ne 'pg_dump custom') {
    throw 'Unsupported backup manifest format.'
}
$actualHash = (Get-FileHash -LiteralPath $DumpPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $manifest.file.sha256.ToUpperInvariant()) {
    throw 'Refusing restore: backup SHA-256 does not match the manifest.'
}

Invoke-Docker container inspect $TargetContainer | Out-Null
$existingOutput = & docker exec $TargetContainer psql --tuples-only --no-align --username=$DatabaseUser --dbname=postgres --command "SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase';"
$existing = (@($existingOutput) -join '').Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect target database (exit $LASTEXITCODE)." }
if ($existing) { throw "Refusing restore: target database $TargetDatabase already exists; this script never overwrites databases." }

$containerDump = "/tmp/$([System.IO.Path]::GetFileName($DumpPath))"
$startedAt = [DateTime]::UtcNow
try {
    Invoke-Docker cp $DumpPath "${TargetContainer}:$containerDump"
    Invoke-Docker exec $TargetContainer createdb --username=$DatabaseUser $TargetDatabase
    Invoke-Docker exec $TargetContainer pg_restore --exit-on-error --no-owner --no-privileges "--username=$DatabaseUser" "--dbname=$TargetDatabase" $containerDump
    $completedAt = [DateTime]::UtcNow
    [pscustomobject]@{
        target_container = $TargetContainer
        target_database = $TargetDatabase
        restored_sha256 = $actualHash
        started_at_utc = $startedAt.ToString('o')
        completed_at_utc = $completedAt.ToString('o')
        duration_seconds = [Math]::Round(($completedAt - $startedAt).TotalSeconds, 3)
        exit_code = 0
    } | ConvertTo-Json -Compress
}
finally {
    & docker exec $TargetContainer rm -f $containerDump | Out-Null
}
