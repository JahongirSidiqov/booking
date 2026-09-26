# Builds static/css/app.css with the pinned Tailwind standalone CLI (no Node.js needed).
# Usage:  .\scripts\build-css.ps1
$ErrorActionPreference = "Stop"
$Version = "v4.3.3"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root ".tools\tailwindcss-$Version.exe"

if (-not (Test-Path $Exe)) {
    New-Item -ItemType Directory -Force (Split-Path $Exe) | Out-Null
    $Url = "https://github.com/tailwindlabs/tailwindcss/releases/download/$Version/tailwindcss-windows-x64.exe"
    Write-Host "Downloading Tailwind $Version ..."
    Invoke-WebRequest -Uri $Url -OutFile $Exe
}

# The CLI's `-o` fails with EEXIST inside OneDrive folders (Bun mkdir bug), so the CSS is
# written through stdout. cmd's `>` keeps the bytes as-is; PowerShell 5.1's `>` would
# re-encode them as UTF-16.
Push-Location $Root
try {
    cmd /c "`"$Exe`" -i static\src\app.css --minify > static\css\app.css"
    if ($LASTEXITCODE -ne 0) { throw "Tailwind build failed" }
    Write-Host "static/css/app.css rebuilt"
} finally {
    Pop-Location
}
