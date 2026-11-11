param(
    [string]$WriterUser = "recommendation_writer"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $repoRoot ".env"
$lines = [System.Collections.Generic.List[string]]::new()
$lines.AddRange([IO.File]::ReadAllLines($envPath))
$databaseLine = $lines | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if (-not $databaseLine) {
    throw "DATABASE_URL is missing from the project .env"
}

$databaseUrl = $databaseLine.Substring("DATABASE_URL=".Length)
$databaseUri = [Uri]$databaseUrl
$databaseName = [Uri]::UnescapeDataString($databaseUri.AbsolutePath.TrimStart('/'))
if ($databaseName -ne "movierecommend_test") {
    throw "DATABASE_URL must target movierecommend_test before configuring the recommendation writer"
}

$securePassword = Read-Host "Password for MySQL user $WriterUser (input is hidden)" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $encodedUser = [Uri]::EscapeDataString($WriterUser)
    $encodedPassword = [Uri]::EscapeDataString($plainPassword)
    $encodedHost = $databaseUri.Host
    $port = if ($databaseUri.IsDefaultPort) { 3306 } else { $databaseUri.Port }
    $writerUrl = "mysql://${encodedUser}:${encodedPassword}@${encodedHost}:${port}/movierecommend_test"
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    $plainPassword = $null
    $encodedPassword = $null
}

$result = [System.Collections.Generic.List[string]]::new()
$writerUrlWritten = $false
$gateWritten = $false
foreach ($line in $lines) {
    if ($line -match '^RECOMMENDATION_WRITE_URL=') {
        $result.Add("RECOMMENDATION_WRITE_URL=$writerUrl")
        $writerUrlWritten = $true
    } elseif ($line -match '^RECOMMENDATION_WRITE_ENABLED=') {
        $result.Add("RECOMMENDATION_WRITE_ENABLED=NO")
        $gateWritten = $true
    } else {
        $result.Add($line)
    }
}
if (-not $writerUrlWritten) {
    $result.Add("RECOMMENDATION_WRITE_URL=$writerUrl")
}
if (-not $gateWritten) {
    $result.Add("RECOMMENDATION_WRITE_ENABLED=NO")
}

[IO.File]::WriteAllLines($envPath, $result, [Text.UTF8Encoding]::new($false))
$writerUrl = $null
Write-Output "writer_url_saved=True"
Write-Output "write_gate=NO"
Write-Output "Run check_test_database.py to verify INSERT-only grants before enabling writes."
