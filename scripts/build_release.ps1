param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

# ---------------- PATH SETUP ---------------- #
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VersionSource = Join-Path $ProjectRoot "app_version.py"
$BuildAppScript = Join-Path $ProjectRoot "scripts\build_app.ps1"
$BuildMsiScript = Join-Path $ProjectRoot "scripts\build_msi.ps1"

# ---------------- VERSION RESOLUTION ---------------- #
if ([string]::IsNullOrWhiteSpace($Version)) {
    $VersionMatch = Select-String -Path $VersionSource -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if (-not $VersionMatch) {
        throw "Could not read APP_VERSION from $VersionSource"
    }
    $Version = $VersionMatch.Matches[0].Groups[1].Value
}

# ---------------- RELEASE BUILD ---------------- #
powershell -ExecutionPolicy Bypass -File $BuildAppScript -Version $Version
if ($LASTEXITCODE -ne 0) {
    throw "Application build failed."
}

powershell -ExecutionPolicy Bypass -File $BuildMsiScript -Version $Version
if ($LASTEXITCODE -ne 0) {
    throw "MSI build failed."
}

Write-Host "Release build complete for version $Version"
