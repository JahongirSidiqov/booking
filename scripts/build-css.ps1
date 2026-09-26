# Builds static/css/app.css from assets/css/app.css with the pinned Tailwind standalone CLI
# (no Node.js needed).
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
    # Build into a temp file and only replace app.css on success: a failed build must never
    # leave an empty stylesheet behind (cmd's `>` creates the file before Tailwind runs).
    $Tmp = "static\css\app.css.tmp"
    cmd /c "`"$Exe`" -i assets\css\app.css --minify > $Tmp"
    $ok = ($LASTEXITCODE -eq 0) -and (Test-Path $Tmp) -and ((Get-Item $Tmp).Length -gt 1000)
    if (-not $ok) {
        Remove-Item -Force -ErrorAction SilentlyContinue $Tmp
        throw "Tailwind build failed; static/css/app.css was left unchanged"
    }
    Move-Item -Force $Tmp "static\css\app.css"
    Write-Host "static/css/app.css rebuilt"
} finally {
    Pop-Location
}
