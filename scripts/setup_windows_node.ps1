<#
.SYNOPSIS
Setup one-click ambiente di produzione nativo Windows 10 (Zero Docker) per Smart Home 3D Digital Twin.
Eseguibile sia sul portatile di sviluppo che sul PC Fisso server (Intel Core i5-6400 / 8 GB RAM / Intel HD 530).
#>
param(
    [switch]$WithOpenVINO,
    [switch]$WithBiometrics,
    [switch]$InstallServices,
    [string]$LanCidr = "192.168.86.0/24"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Test-PeBinary {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [int64]$MinBytes = 1048576
    )
    if (-not (Test-Path $FilePath)) { return $false }
    $item = Get-Item -Path $FilePath
    if ($item.Length -lt $MinBytes) { return $false }
    $fs = [System.IO.File]::OpenRead($FilePath)
    try {
        $b0 = $fs.ReadByte()
        $b1 = $fs.ReadByte()
        return ($b0 -eq 0x4D -and $b1 -eq 0x5A)
    } finally {
        $fs.Dispose()
    }
}

Write-Host "=== SMART HOME 3D - SETUP WINDOWS NATIVE NODE ===" -ForegroundColor Cyan
Write-Host "Workspace: $RepoRoot"

# 1. Verifica .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[OK] Creato .env da .env.example (ricordati di configurare REOLINK_CARRAIO_IP/USER/PASS e i parametri di produzione)." -ForegroundColor Yellow
    } else {
        Write-Host "[WARN] File .env e .env.example non trovati." -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] .env esistente rilevato." -ForegroundColor Green
}

# 1b. Verifica Visual C++ Redistributable x64 (necessario per OpenVINO / runtime nativi)
$VcRegPath = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$VcInstalled = $false
if (Test-Path $VcRegPath) {
    $vcProps = Get-ItemProperty -Path $VcRegPath -ErrorAction SilentlyContinue
    if ($vcProps -and $vcProps.Installed -eq 1) {
        $VcInstalled = $true
    }
}

if ($VcInstalled) {
    Write-Host "[OK] Microsoft Visual C++ Redistributable x64 già installato." -ForegroundColor Green
} else {
    Write-Host "[*] Microsoft Visual C++ Redistributable x64 mancante: avvio download e installazione..." -ForegroundColor Cyan
    $VcTempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sh3d-vcredist-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $VcTempDir | Out-Null
    try {
        $VcExe = Join-Path $VcTempDir "vc_redist.x64.exe"
        Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile $VcExe -UseBasicParsing
        $isAdmin = (New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $proc = $null
        if ($isAdmin) {
            $proc = Start-Process -FilePath $VcExe -ArgumentList "/install", "/quiet", "/norestart" -Wait -PassThru
        } else {
            try {
                $proc = Start-Process -FilePath $VcExe -ArgumentList "/install", "/quiet", "/norestart" -Verb RunAs -Wait -PassThru
            } catch {
                $msg = "Impossibile elevare privilegi (UAC) per installare VC_redist.x64. Esegui PowerShell come Amministratore e riprova (oppure installa manualmente vc_redist.x64.exe da https://aka.ms/vs/17/release/vc_redist.x64.exe)."
                if ($WithOpenVINO) {
                    throw $msg
                } else {
                    Write-Host "[WARN] $msg" -ForegroundColor Yellow
                }
            }
        }

        if ($null -ne $proc) {
            switch ($proc.ExitCode) {
                0 { Write-Host "[OK] VC_redist.x64 installato con successo." -ForegroundColor Green }
                1638 { Write-Host "[OK] VC_redist.x64 versione più recente già presente (exit 1638)." -ForegroundColor Green }
                3010 { Write-Host "[WARN] VC_redist.x64 installato: riavvio di Windows consigliato (exit 3010)." -ForegroundColor Yellow }
                default { throw "Installazione VC_redist.x64 fallita con codice di uscita $($proc.ExitCode)." }
            }
        }
    } finally {
        if (Test-Path $VcTempDir) {
            Remove-Item -Path $VcTempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# 2a. Scarica go2rtc.exe se mancante
$Go2RtcExe = Join-Path $RepoRoot "go2rtc\go2rtc.exe"
if (-not (Test-Path $Go2RtcExe)) {
    Write-Host "[*] Download go2rtc (Windows amd64 standalone)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "go2rtc") | Out-Null
    $Go2RtcTempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sh3d-go2rtc-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $Go2RtcTempDir | Out-Null
    try {
        $ZipPath = Join-Path $Go2RtcTempDir "go2rtc_win64.zip"
        $ExtractDir = Join-Path $Go2RtcTempDir "extract"
        $Url = "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_win64.zip"
        Invoke-WebRequest -Uri $Url -OutFile $ZipPath -UseBasicParsing
        Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force
        $extractedExe = Get-ChildItem -Path $ExtractDir -Filter "go2rtc.exe" -Recurse | Select-Object -First 1
        if (-not $extractedExe) {
            throw "go2rtc.exe non trovato nell'archivio go2rtc_win64.zip."
        }
        Copy-Item -Path $extractedExe.FullName -Destination $Go2RtcExe -Force
        Write-Host "[OK] go2rtc.exe installato in go2rtc\go2rtc.exe" -ForegroundColor Green
    } finally {
        if (Test-Path $Go2RtcTempDir) {
            Remove-Item -Path $Go2RtcTempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "[OK] go2rtc.exe già presente." -ForegroundColor Green
}

# 2b. Scarica caddy.exe se mancante
$CaddyExe = Join-Path $RepoRoot "caddy\caddy.exe"
if (-not (Test-Path $CaddyExe)) {
    Write-Host "[*] Download Caddy (Windows amd64 standalone)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "caddy") | Out-Null
    $CaddyTempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sh3d-caddy-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $CaddyTempDir | Out-Null
    try {
        $TempCaddy = Join-Path $CaddyTempDir "caddy.exe"
        $downloaded = $false
        try {
            Invoke-WebRequest -Uri "https://caddyserver.com/api/download?os=windows&arch=amd64" -OutFile $TempCaddy -UseBasicParsing
            if (Test-PeBinary -FilePath $TempCaddy -MinBytes 1048576) {
                Copy-Item -Path $TempCaddy -Destination $CaddyExe -Force
                $downloaded = $true
            }
        } catch {
            Write-Host "[WARN] Download diretto Caddy API non riuscito, provo fallback GitHub Releases..." -ForegroundColor Yellow
        }

        if (-not $downloaded) {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/caddyserver/caddy/releases/latest" -Headers @{ "User-Agent" = "SmartHome3D-Setup" } -UseBasicParsing
            $asset = $release.assets | Where-Object { $_.name -match '^caddy_.*_windows_amd64\.zip$' } | Select-Object -First 1
            if (-not $asset) {
                throw "Asset Windows amd64 non trovato nell'ultima release GitHub di Caddy."
            }
            $CaddyZip = Join-Path $CaddyTempDir "caddy.zip"
            $CaddyExtract = Join-Path $CaddyTempDir "extract"
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $CaddyZip -UseBasicParsing
            Expand-Archive -Path $CaddyZip -DestinationPath $CaddyExtract -Force
            $extractedCaddy = Get-ChildItem -Path $CaddyExtract -Filter "caddy.exe" -Recurse | Select-Object -First 1
            if (-not $extractedCaddy -or -not (Test-PeBinary -FilePath $extractedCaddy.FullName -MinBytes 1048576)) {
                throw "Binario caddy.exe non valido o mancante nell'archivio GitHub."
            }
            Copy-Item -Path $extractedCaddy.FullName -Destination $CaddyExe -Force
        }
        Write-Host "[OK] caddy.exe installato in caddy\caddy.exe" -ForegroundColor Green
    } finally {
        if (Test-Path $CaddyTempDir) {
            Remove-Item -Path $CaddyTempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "[OK] caddy.exe già presente." -ForegroundColor Green
}

# 2c. Scarica tools\nssm.exe se mancante
$NssmExe = Join-Path $RepoRoot "tools\nssm.exe"
if (-not (Test-Path $NssmExe)) {
    Write-Host "[*] Download NSSM (Non-Sucking Service Manager win64)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "tools") | Out-Null
    $NssmTempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sh3d-nssm-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $NssmTempDir | Out-Null
    try {
        $NssmZip = Join-Path $NssmTempDir "nssm.zip"
        $NssmExtract = Join-Path $NssmTempDir "extract"
        $nssmUrls = @(
            "https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip",
            "https://nssm.cc/release/nssm-2.24.zip"
        )
        $zipOk = $false
        foreach ($nssmUrl in $nssmUrls) {
            try {
                Invoke-WebRequest -Uri $nssmUrl -OutFile $NssmZip -UseBasicParsing
                if ((Test-Path $NssmZip) -and ((Get-Item $NssmZip).Length -gt 50000)) {
                    $zipOk = $true
                    break
                }
            } catch {
                Write-Host "[WARN] Download NSSM fallito da $nssmUrl, provo mirror successivo..." -ForegroundColor Yellow
            }
        }
        if (-not $zipOk) {
            throw "Impossibile scaricare NSSM dai mirror ufficiali."
        }
        Expand-Archive -Path $NssmZip -DestinationPath $NssmExtract -Force
        $extractedNssm = Get-ChildItem -Path $NssmExtract -Filter "nssm.exe" -Recurse | Where-Object { $_.Directory.Name -eq "win64" } | Select-Object -First 1
        if (-not $extractedNssm -or -not (Test-PeBinary -FilePath $extractedNssm.FullName -MinBytes 102400)) {
            throw "win64\nssm.exe non valido o mancante nell'archivio NSSM."
        }
        Copy-Item -Path $extractedNssm.FullName -Destination $NssmExe -Force
        Write-Host "[OK] nssm.exe installato in tools\nssm.exe" -ForegroundColor Green
    } finally {
        if (Test-Path $NssmTempDir) {
            Remove-Item -Path $NssmTempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "[OK] tools\nssm.exe già presente." -ForegroundColor Green
}

# 3. Ambiente Python .venv + dipendenze spatial_server
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python non trovato nel PATH. Installa Python 3.11+ (con opzione 'Add Python to PATH') e riprova."
    }
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
    $YoloDownloadScript = Join-Path $RepoRoot "tools\download_yolo_openvino_model.py"
    if (Test-Path $YoloDownloadScript) {
        Write-Host "[*] Download e conversione modello YOLOv8n OpenVINO IR (FP16)..." -ForegroundColor Cyan
        & $VenvPy $YoloDownloadScript
    }
}

if ($WithBiometrics) {
    $BioDownloadScript = Join-Path $RepoRoot "tools\download_biometric_models.py"
    if (Test-Path $BioDownloadScript) {
        Write-Host "[*] Download modelli ONNX Biometria (Face Recognition SCRFD/MobileFaceNet + ALPR IT/EU)..." -ForegroundColor Cyan
        & $VenvPy $BioDownloadScript
    } else {
        Write-Host "[WARN] Script tools\download_biometric_models.py non trovato." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== SETUP COMPLETATO CON SUCCESSO! ===" -ForegroundColor Green
Write-Host "1) Verifica in .env le credenziali Reolink: REOLINK_CARRAIO_IP / REOLINK_CARRAIO_USER / REOLINK_CARRAIO_PASS"
Write-Host "2) Per PRODUZIONE (Tailscale Serve + OAuth2 HA):"
Write-Host "   - Imposta VITE_HA_PUBLIC_URL=https://<pc-fisso>.<tailnet>.ts.net:8443 e lascia VITE_HA_TOKEN= vuoto"
Write-Host "   - Imposta SPATIAL_SERVER_HOST=127.0.0.1, SPATIAL_AUTH_REQUIRED=true, SPATIAL_ALLOWED_ORIGINS=https://<pc-fisso>.<tailnet>.ts.net"
Write-Host "   - Imposta SPATIAL_SESSION_SECRET, GO2RTC_CANDIDATE_LAN=<IP_LAN>:8555 e GO2RTC_CANDIDATE_TAILSCALE=<IP_TAILSCALE>:8555"
Write-Host "3) (Opzionale - Biometria locale) Scarica modelli con -WithBiometrics, genera la galleria volti (.venv\Scripts\python.exe tools\enroll_faces.py), valida con tools\benchmark_biometrics.py e imposta BIOMETRICS_ENABLED=true in .env"
Write-Host "4) Compila il frontend PWA di produzione: npm.cmd install && npm.cmd run build"
Write-Host "5) Registra i servizi NSSM e Firewall (PowerShell Amministratore):"
Write-Host "   powershell -ExecutionPolicy Bypass -File scripts\install_windows_services.ps1 -LanCidr $LanCidr"
Write-Host "6) Esponi con Tailscale Serve (PowerShell Amministratore):"
Write-Host "   tailscale serve --bg 8080"
Write-Host "   netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=8123 connectaddress=192.168.86.24 connectport=8123"
Write-Host "   tailscale serve --bg --https=8443 8123"
Write-Host "7) (Solo sviluppo) Avvio manuale: scripts\start_services.bat + npm.cmd run dev"

if ($InstallServices) {
    $InstallServicesScript = Join-Path $PSScriptRoot "install_windows_services.ps1"
    if (-not (Test-Path $InstallServicesScript)) {
        throw "Script mancante: $InstallServicesScript"
    }
    Write-Host ""
    Write-Host "[*] Invocazione install_windows_services.ps1 -LanCidr $LanCidr..." -ForegroundColor Cyan
    & $InstallServicesScript -LanCidr $LanCidr
}

