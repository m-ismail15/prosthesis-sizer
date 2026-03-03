param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

# ---------------- PATH SETUP ---------------- #
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistDir = Join-Path $ProjectRoot "dist"
$StagingDir = Join-Path $ProjectRoot "build\msi_staging"
$ObjectDir = Join-Path $ProjectRoot "build\msi_obj"
$OutputDir = Join-Path $ProjectRoot "build\msi"
$InstallerSource = Join-Path $ProjectRoot "installer\ProsthesisSizingApp.wxs"
$VersionSource = Join-Path $ProjectRoot "app_version.py"

$AppExe = Join-Path $DistDir "app.exe"
$ImagesDir = Join-Path $ProjectRoot "images"
$ReadmeSource = Join-Path $ProjectRoot "README.md"
$InstallGuideSource = Join-Path $ProjectRoot "INSTALL.txt"
$IconSource = Join-Path $ProjectRoot "MedTechLogo.ico"
$SplashBackgroundSource = Join-Path $ProjectRoot "MedTechBG.png"

# ---------------- VALIDATION ---------------- #
foreach ($RequiredPath in @($ImagesDir, $ReadmeSource, $InstallGuideSource, $IconSource, $SplashBackgroundSource, $InstallerSource, $VersionSource)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Required installer input not found: $RequiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $VersionMatch = Select-String -Path $VersionSource -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if (-not $VersionMatch) {
        throw "Could not read APP_VERSION from $VersionSource"
    }
    $Version = $VersionMatch.Matches[0].Groups[1].Value
}

if (-not (Test-Path $AppExe)) {
    throw "Missing build artifact: $AppExe. Run scripts\\build_app.ps1 before building the MSI."
}

# ---------------- STAGING ---------------- #
if (Test-Path $StagingDir) {
    Remove-Item $StagingDir -Recurse -Force
}

New-Item -ItemType Directory -Path $StagingDir | Out-Null
New-Item -ItemType Directory -Path (Join-Path $StagingDir "images") | Out-Null
New-Item -ItemType Directory -Path $ObjectDir -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Copy-Item $AppExe (Join-Path $StagingDir "app.exe")
Copy-Item $IconSource (Join-Path $StagingDir "MedTechLogo.ico")
Copy-Item $SplashBackgroundSource (Join-Path $StagingDir "MedTechBG.png")
Copy-Item $ReadmeSource (Join-Path $StagingDir "README.txt")
Copy-Item $InstallGuideSource (Join-Path $StagingDir "INSTALL.txt")
Copy-Item (Join-Path $ImagesDir "*") (Join-Path $StagingDir "images") -Recurse

# ---------------- WIX DISCOVERY ---------------- #
$CandleCandidates = @(
    (Get-Command candle.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "C:\Program Files (x86)\WiX Toolset v3.11\bin\candle.exe",
    "C:\Program Files\WiX Toolset v3.11\bin\candle.exe"
) | Where-Object { $_ -and (Test-Path $_) }

$LightCandidates = @(
    (Get-Command light.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "C:\Program Files (x86)\WiX Toolset v3.11\bin\light.exe",
    "C:\Program Files\WiX Toolset v3.11\bin\light.exe"
) | Where-Object { $_ -and (Test-Path $_) }

$Candle = $CandleCandidates | Select-Object -First 1
$Light = $LightCandidates | Select-Object -First 1

if (-not $Candle -or -not $Light) {
    Write-Host "MSI staging prepared at: $StagingDir"
    Write-Host "WiX Toolset v3.x was not found."
    Write-Host "Install WiX Toolset, then rerun:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\build_msi.ps1`" -Version $Version"
    exit 0
}

# ---------------- MSI BUILD ---------------- #
$WixObj = Join-Path $ObjectDir "ProsthesisSizingApp.wixobj"
$MsiOut = Join-Path $OutputDir ("ProsthesisSizingApp_" + $Version + ".msi")

& $Candle `
    "-dVersion=$Version" `
    "-dProjectRoot=$ProjectRoot" `
    "-dStagingDir=$StagingDir" `
    "-out" $WixObj `
    $InstallerSource

& $Light `
    "-out" $MsiOut `
    $WixObj

Write-Host "MSI created at: $MsiOut"
