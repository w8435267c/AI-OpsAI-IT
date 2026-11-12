[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.-]*$')]
    [string]$SourceContainer,

    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]*$')]
    [string]$Database,

    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]*$')]
    [string]$DatabaseUser,

    [Parameter(Mandatory)]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed (exit $LASTEXITCODE): docker $($Arguments -join ' ')"
    }
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
if ($resolvedOutput.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to write a backup inside the repository. Use a controlled external directory.'
}

Invoke-Docker container inspect $SourceContainer | Out-Null
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$startedAt = [DateTime]::UtcNow
$stamp = $startedAt.ToString('yyyyMMddTHHmmssZ')
$dumpName = "opsai-postgresql-$stamp.dump"
$manifestName = "opsai-postgresql-$stamp.manifest.json"
$containerTemp = "/tmp/$dumpName"
$dumpPath = Join-Path $resolvedOutput $dumpName
$manifestPath = Join-Path $resolvedOutput $manifestName
$cleanupNeeded = $false

try {
    # Write inside the database container to avoid PowerShell text redirection corrupting a binary dump.
    Invoke-Docker exec $SourceContainer pg_dump "--format=custom" "--file=$containerTemp" "--username=$DatabaseUser" "--dbname=$Database"
    $cleanupNeeded = $true
    Invoke-Docker cp "${SourceContainer}:$containerTemp" $dumpPath

    if (-not (Test-Path -LiteralPath $dumpPath) -or (Get-Item -LiteralPath $dumpPath).Length -le 0) {
        throw 'pg_dump did not create a valid non-empty backup file.'
    }

    $hash = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash.ToUpperInvariant()
    $databaseVersion = (& docker exec $SourceContainer psql --tuples-only --no-align --username=$DatabaseUser --dbname=$Database --command 'SHOW server_version;' | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Unable to read PostgreSQL server version (exit $LASTEXITCODE)." }
    $dumpVersion = (& docker exec $SourceContainer pg_dump --version | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Unable to read pg_dump version (exit $LASTEXITCODE)." }

    $completedAt = [DateTime]::UtcNow
    $manifest = [ordered]@{
        schema = 'opsai.postgresql-backup-manifest/v1'
        format = 'pg_dump custom'
        database = $Database
        source_container = $SourceContainer
        started_at_utc = $startedAt.ToString('o')
        completed_at_utc = $completedAt.ToString('o')
        duration_seconds = [Math]::Round(($completedAt - $startedAt).TotalSeconds, 3)
        command_exit_code = 0
        database_server_version = $databaseVersion
        pg_dump_version = $dumpVersion
        file = [ordered]@{
            name = $dumpName
            bytes = (Get-Item -LiteralPath $dumpPath).Length
            sha256 = $hash
        }
    }
    $manifestJson = $manifest | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText(
        $manifestPath,
        $manifestJson,
        (New-Object System.Text.UTF8Encoding($false))
    )
    [pscustomobject]@{ dump = $dumpPath; manifest = $manifestPath; sha256 = $hash; bytes = $manifest.file.bytes; exit_code = 0 } | ConvertTo-Json -Compress
}
finally {
    if ($cleanupNeeded) {
        & docker exec $SourceContainer rm -f $containerTemp | Out-Null
    }
}
