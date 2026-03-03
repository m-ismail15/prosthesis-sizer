param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

# ---------------- PATH SETUP ---------------- #
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SpecFile = Join-Path $ProjectRoot "app.spec"
$SourceImagesDir = Join-Path $ProjectRoot "images"
$SplashBackgroundSource = Join-Path $ProjectRoot "MedTechBG.png"
$ReadmeSource = Join-Path $ProjectRoot "README.md"
$InstallGuideSource = Join-Path $ProjectRoot "INSTALL.txt"
$VersionSource = Join-Path $ProjectRoot "app_version.py"
$DistDir = Join-Path $ProjectRoot "dist"
$DistImagesDir = Join-Path $DistDir "images"
$DistDataDir = Join-Path $DistDir "data"
$DistConfigDir = Join-Path $DistDir "config"

# ---------------- VALIDATION ---------------- #
foreach ($RequiredPath in @($SpecFile, $SourceImagesDir, $SplashBackgroundSource, $ReadmeSource, $InstallGuideSource, $VersionSource)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Required build input not found: $RequiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $VersionMatch = Select-String -Path $VersionSource -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if (-not $VersionMatch) {
        throw "Could not read APP_VERSION from $VersionSource"
    }
    $Version = $VersionMatch.Matches[0].Groups[1].Value
}

# ---------------- PYINSTALLER DISCOVERY ---------------- #
$PyInstallerCommand = $null

if (Test-Path (Join-Path $ProjectRoot "venv\Scripts\pyinstaller.exe")) {
    $PyInstallerCommand = (Join-Path $ProjectRoot "venv\Scripts\pyinstaller.exe")
} elseif (Get-Command pyinstaller.exe -ErrorAction SilentlyContinue) {
    $PyInstallerCommand = (Get-Command pyinstaller.exe).Source
}

if (-not $PyInstallerCommand) {
    throw "PyInstaller was not found. Install it in the active environment before building the app."
}

# ---------------- EXECUTABLE BUILD ---------------- #
& $PyInstallerCommand --clean $SpecFile

# ---------------- DIST STAGING ---------------- #
if (Test-Path $DistImagesDir) {
    Remove-Item $DistImagesDir -Recurse -Force
}

New-Item -ItemType Directory -Path $DistImagesDir -Force | Out-Null
New-Item -ItemType Directory -Path $DistDataDir -Force | Out-Null
New-Item -ItemType Directory -Path $DistConfigDir -Force | Out-Null

Copy-Item (Join-Path $SourceImagesDir "*") $DistImagesDir -Recurse -Force
Copy-Item $SplashBackgroundSource (Join-Path $DistDir "MedTechBG.png") -Force
Copy-Item $ReadmeSource (Join-Path $DistDir "README.txt") -Force
Copy-Item $InstallGuideSource (Join-Path $DistDir "INSTALL.txt") -Force

if (-not (Test-Path (Join-Path $DistDataDir "offline_records.json"))) {
    '{ "prosthesis_records": [] }' | Set-Content -Path (Join-Path $DistDataDir "offline_records.json") -Encoding UTF8
}

Write-Host "App build complete: $DistDir (version $Version)"
