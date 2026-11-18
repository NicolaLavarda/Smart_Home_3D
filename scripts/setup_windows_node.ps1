<#
.SYNOPSIS
Setup one-click ambiente di produzione nativo Windows 10 (Zero Docker) per Smart Home 3D Digital Twin.
Eseguibile sia sul portatile di sviluppo che sul PC Fisso server (Intel Core i5-6400 / 8 GB RAM / Intel HD 530).
#>
param(
    [switch]$WithOpenVINO
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

Write-Host "=== SMART HOME 3D - SETUP WINDOWS NATIVE NODE ===" -ForegroundColor Cyan
Write-Host "Workspace: $RepoRoot"

# 1. Verifica .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[OK] Creato .env da .env.example (ricordati di inserire REOLINK_CARRAIO_PASSWORD e VITE_HA_TOKEN)." -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] .env esistente rilevato." -ForegroundColor Green
}

# 2. Scarica go2rtc.exe se mancante
$Go2RtcExe = Join-Path $RepoRoot "go2rtc\go2rtc.exe"
if (-not (Test-Path $Go2RtcExe)) {
    Write-Host "[*] Download go2rtc (Windows amd64 standalone)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "go2rtc") | Out-Null
    $ZipPath = Join-Path $RepoRoot "go2rtc\go2rtc_win64.zip"
    $Url = "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_win64.zip"
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath -UseBasicParsing
    Expand-Archive -Path $ZipPath -DestinationPath (Join-Path $RepoRoot "go2rtc") -Force
    Remove-Item $ZipPath -Force
    Write-Host "[OK] go2rtc.exe installato in go2rtc\go2rtc.exe" -ForegroundColor Green
} else {
    Write-Host "[OK] go2rtc.exe già presente." -ForegroundColor Green
}

# 3. Ambiente Python .venv + dipendenze spatial_server
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[*] Creazione virtualenv Python (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
Write-Host "[*] Installazione dipendenze spatial_server\requirements.txt..." -ForegroundColor Cyan
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -r "spatial_server\requirements.txt"

if ($WithOpenVINO) {
    Write-Host "[*] Installazione runtime OpenVINO leggero (supporto iGPU Intel HD 530 / CPU Skylake)..." -ForegroundColor Cyan
    & $VenvPy -m pip install "openvino>=2024.4.0"
}

Write-Host ""
Write-Host "=== SETUP COMPLETATO CON SUCCESSO! ===" -ForegroundColor Green
Write-Host "1) Verifica le credenziali Reolink in .env (REOLINK_CARRAIO_USER / REOLINK_CARRAIO_PASSWORD)"
Write-Host "2) Avvia i servizi con: scripts\start_services.bat"
Write-Host "3) (Solo in sviluppo) Avvia il frontend con: npm.cmd run dev"

