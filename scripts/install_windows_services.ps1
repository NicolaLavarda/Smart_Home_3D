<#
.SYNOPSIS
Installa o aggiorna in modo idempotente i servizi Windows NSSM (go2rtc, spatial_server, Caddy)
e le regole Windows Defender Firewall per WebRTC (:8555 TCP/UDP limitato a LAN e Tailscale CGNAT).
Richiede PowerShell eseguito come Amministratore.
#>
[CmdletBinding()]
param(
    [string]$LanCidr = "192.168.86.0/24",
    [switch]$SkipFirewall,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

# 1. Verifica privilegi Amministratore
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[ERRORE] Questo script deve essere eseguito in una sessione PowerShell come Amministratore." -ForegroundColor Red
    exit 1
}

# 2. Validazione formato CIDR IPv4
if ($LanCidr -notmatch '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})/(\d{1,2})$') {
    Write-Host "[ERRORE] LanCidr non valido ('$LanCidr'). Formato atteso: es. 192.168.86.0/24" -ForegroundColor Red
    exit 1
}
$octetsValid = ([int]$Matches[1] -le 255) -and ([int]$Matches[2] -le 255) -and ([int]$Matches[3] -le 255) -and ([int]$Matches[4] -le 255)
$prefixValid = ([int]$Matches[5] -ge 0) -and ([int]$Matches[5] -le 32)
if (-not ($octetsValid -and $prefixValid)) {
    Write-Host "[ERRORE] LanCidr fuori range IPv4 ('$LanCidr')." -ForegroundColor Red
    exit 1
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

Write-Host "=== SMART HOME 3D - INSTALLAZIONE SERVIZI WINDOWS (NSSM + FIREWALL) ===" -ForegroundColor Cyan
Write-Host "Workspace: $RepoRoot"

# 3. Verifica file prerequisiti e creazione logs\
$CaddyExe = Join-Path $RepoRoot "caddy\caddy.exe"
$Caddyfile = Join-Path $RepoRoot "caddy\Caddyfile"
$NssmExe = Join-Path $RepoRoot "tools\nssm.exe"
$Go2RtcExe = Join-Path $RepoRoot "go2rtc\go2rtc.exe"
$Go2RtcYaml = Join-Path $RepoRoot "go2rtc\go2rtc.yaml"
$UvicornExe = Join-Path $RepoRoot ".venv\Scripts\uvicorn.exe"
$EnvFile = Join-Path $RepoRoot ".env"
$DistIndex = Join-Path $RepoRoot "dist\index.html"
$LogsDir = Join-Path $RepoRoot "logs"

$RequiredFiles = @(
    @{ Path = $CaddyExe; Hint = "Esegui scripts\setup_windows_node.ps1" },
    @{ Path = $Caddyfile; Hint = "Verifica la presenza di caddy\Caddyfile nel repository" },
    @{ Path = $NssmExe; Hint = "Esegui scripts\setup_windows_node.ps1" },
    @{ Path = $Go2RtcExe; Hint = "Esegui scripts\setup_windows_node.ps1" },
    @{ Path = $Go2RtcYaml; Hint = "Verifica la presenza di go2rtc\go2rtc.yaml nel repository" },
    @{ Path = $UvicornExe; Hint = "Esegui scripts\setup_windows_node.ps1" },
    @{ Path = $EnvFile; Hint = "Copia .env.example in .env e configura i parametri di produzione" }
)

foreach ($req in $RequiredFiles) {
    if (-not (Test-Path $req.Path)) {
        Write-Host "[ERRORE] Prerequisito mancante: $($req.Path) ($($req.Hint))." -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $DistIndex)) {
    Write-Host "[WARN] Build frontend dist\index.html non trovato: esegui 'npm.cmd install && npm.cmd run build' prima dell'accesso da browser." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

# 4. Parsing .env (UTF8, gestione export, commenti, virgolette esterne, = / ! / # interni)
$EnvMap = [ordered]@{}
$rawLines = Get-Content -Path $EnvFile -Encoding UTF8
foreach ($rawLine in $rawLines) {
    $line = $rawLine.Trim()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
        continue
    }
    $line = $line -replace '^export\s+', ''
    $eqIdx = $line.IndexOf('=')
    if ($eqIdx -le 0) {
        continue
    }
    $key = $line.Substring(0, $eqIdx).Trim()
    if ($key -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        continue
    }
    $val = $line.Substring($eqIdx + 1).Trim()
    if ($val.Length -ge 2) {
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
    }
    $EnvMap[$key] = $val
}

if ($EnvMap.Contains("REOLINK_CARRAIO_PASSWORD") -and [string]::IsNullOrEmpty($EnvMap["REOLINK_CARRAIO_PASS"])) {
    $EnvMap["REOLINK_CARRAIO_PASS"] = $EnvMap["REOLINK_CARRAIO_PASSWORD"]
}
if ($EnvMap.Contains("MQTT_PASSWORD") -and [string]::IsNullOrEmpty($EnvMap["MQTT_PASS"])) {
    $EnvMap["MQTT_PASS"] = $EnvMap["MQTT_PASSWORD"]
}

$SpatialPort = if ($EnvMap.Contains("SPATIAL_SERVER_PORT") -and -not [string]::IsNullOrWhiteSpace($EnvMap["SPATIAL_SERVER_PORT"])) {
    $EnvMap["SPATIAL_SERVER_PORT"]
} else {
    "8765"
}

$Go2RtcEnv = New-Object System.Collections.Generic.List[string]
foreach ($entry in $EnvMap.GetEnumerator()) {
    # Omette GO2RTC_CANDIDATE_* se vuoti cosi' go2rtc.yaml applica i default ${VAR:127.0.0.1:8555}
    if (($entry.Key -eq "GO2RTC_CANDIDATE_LAN" -or $entry.Key -eq "GO2RTC_CANDIDATE_TAILSCALE") -and [string]::IsNullOrWhiteSpace($entry.Value)) {
        continue
    }
    $Go2RtcEnv.Add("$($entry.Key)=$($entry.Value)")
}

$SpatialMap = [ordered]@{}
foreach ($entry in $EnvMap.GetEnumerator()) {
    $SpatialMap[$entry.Key] = $entry.Value
}
$SpatialMap["SPATIAL_SERVER_HOST"] = "127.0.0.1"
$SpatialMap["SPATIAL_SERVER_PORT"] = $SpatialPort

$SpatialEnv = New-Object System.Collections.Generic.List[string]
foreach ($entry in $SpatialMap.GetEnumerator()) {
    $SpatialEnv.Add("$($entry.Key)=$($entry.Value)")
}

# 5. Arresto idempotente servizi esistenti in ordine inverso alle dipendenze + cleanup processi residui del repo
$StopOrder = @("SmartHome3D-Caddy", "SmartHome3D-SpatialServer", "SmartHome3D-go2rtc")
foreach ($svcName in $StopOrder) {
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if ($null -ne $svc -and $svc.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
        Write-Host "[*] Arresto servizio esistente $svcName..." -ForegroundColor Cyan
        Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
        try {
            $svc.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(15))
        } catch {
            Write-Host "[WARN] Timeout attesa arresto $svcName, verifico processi residui..." -ForegroundColor Yellow
        }
    }
}

$repoPrefix = $RepoRoot.TrimEnd('\') + '\'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and ($_.Name -in @("caddy.exe", "go2rtc.exe", "uvicorn.exe"))) -or
    ($_.CommandLine -and $_.CommandLine -like "*spatial_server.main:app*")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# 6. Helper NSSM + installazione/aggiornamento dei 3 servizi
function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$IgnoreNonZero
    )
    $output = & $NssmExe @Arguments 2>&1
    $code = $LASTEXITCODE
    if (-not $IgnoreNonZero -and $code -ne 0) {
        throw "Comando NSSM fallito (exit $code): nssm $($Arguments -join ' ') -> $($output | Out-String)"
    }
}

function Install-OrUpdateNssmService {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$DisplayName,
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][string]$ExePath,
        [Parameter(Mandatory = $true)][string]$AppDir,
        [Parameter(Mandatory = $true)][string]$AppParameters,
        [Parameter(Mandatory = $true)][string]$LogPrefix,
        [string[]]$Dependencies = @(),
        [string[]]$EnvLines = @()
    )

    $existing = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Host "[*] Registrazione nuovo servizio NSSM: $Name..." -ForegroundColor Cyan
        Invoke-Nssm -Arguments @("install", $Name, $ExePath)
    } else {
        Write-Host "[*] Aggiornamento servizio NSSM esistente: $Name..." -ForegroundColor Cyan
        Invoke-Nssm -Arguments @("set", $Name, "Application", $ExePath)
    }

    Invoke-Nssm -Arguments @("set", $Name, "DisplayName", $DisplayName)
    Invoke-Nssm -Arguments @("set", $Name, "Description", $Description)
    Invoke-Nssm -Arguments @("set", $Name, "AppDirectory", $AppDir)
    Invoke-Nssm -Arguments @("set", $Name, "AppParameters", $AppParameters)
    Invoke-Nssm -Arguments @("set", $Name, "Start", "SERVICE_AUTO_START")
    Invoke-Nssm -Arguments @("set", $Name, "AppExit", "Default", "Restart")
    Invoke-Nssm -Arguments @("set", $Name, "AppRestartDelay", "5000")
    Invoke-Nssm -Arguments @("set", $Name, "AppStopMethodConsole", "5000")
    Invoke-Nssm -Arguments @("set", $Name, "AppStopMethodWindow", "5000")
    Invoke-Nssm -Arguments @("set", $Name, "AppStopMethodThreads", "5000")
    Invoke-Nssm -Arguments @("set", $Name, "AppStdout", (Join-Path $LogsDir "$LogPrefix.stdout.log"))
    Invoke-Nssm -Arguments @("set", $Name, "AppStderr", (Join-Path $LogsDir "$LogPrefix.stderr.log"))
    Invoke-Nssm -Arguments @("set", $Name, "AppRotateFiles", "1")
    Invoke-Nssm -Arguments @("set", $Name, "AppRotateOnline", "1")
    Invoke-Nssm -Arguments @("set", $Name, "AppRotateBytes", "5242880")

    if ($Dependencies.Count -gt 0) {
        $depArgs = @("set", $Name, "DependOnService") + $Dependencies
        Invoke-Nssm -Arguments $depArgs
    } else {
        Invoke-Nssm -Arguments @("reset", $Name, "DependOnService") -IgnoreNonZero
    }

    Invoke-Nssm -Arguments @("reset", $Name, "AppEnvironmentExtra") -IgnoreNonZero
    if ($EnvLines.Count -gt 0) {
        Invoke-Nssm -Arguments (@("set", $Name, "AppEnvironmentExtra") + $EnvLines) -IgnoreNonZero
        $paramRegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name\Parameters"
        if (-not (Test-Path $paramRegPath)) {
            New-Item -Path $paramRegPath -Force | Out-Null
        }
        Set-ItemProperty -Path $paramRegPath -Name "AppEnvironmentExtra" -Value ([string[]]$EnvLines) -Type MultiString
    }

    Write-Host "[OK] Servizio $Name configurato." -ForegroundColor Green
}

$Go2RtcParams = '-c \"' + $Go2RtcYaml + '\"'
Install-OrUpdateNssmService `
    -Name "SmartHome3D-go2rtc" `
    -DisplayName "Smart Home 3D - go2rtc Media Server" `
    -Description "Server streaming RTSP/WebRTC/MSE per Smart Home 3D (API loopback 127.0.0.1:1984, WebRTC :8555)." `
    -ExePath $Go2RtcExe `
    -AppDir $RepoRoot `
    -AppParameters $Go2RtcParams `
    -LogPrefix "go2rtc" `
    -Dependencies @() `
    -EnvLines $Go2RtcEnv.ToArray()

$SpatialParams = "spatial_server.main:app --host 127.0.0.1 --port $SpatialPort"
Install-OrUpdateNssmService `
    -Name "SmartHome3D-SpatialServer" `
    -DisplayName "Smart Home 3D - Spatial CV & Auth Server" `
    -Description "Backend FastAPI auth/RBAC/OpenVINO/MQTT su 127.0.0.1:$SpatialPort per Smart Home 3D." `
    -ExePath $UvicornExe `
    -AppDir $RepoRoot `
    -AppParameters $SpatialParams `
    -LogPrefix "spatial_server" `
    -Dependencies @("SmartHome3D-go2rtc") `
    -EnvLines $SpatialEnv.ToArray()

$CaddyParams = 'run --config \"' + $Caddyfile + '\" --adapter caddyfile'
Install-OrUpdateNssmService `
    -Name "SmartHome3D-Caddy" `
    -DisplayName "Smart Home 3D - Caddy Reverse Proxy" `
    -Description "Reverse proxy same-origin HTTP su 127.0.0.1:8080 per PWA, API e forward_auth go2rtc." `
    -ExePath $CaddyExe `
    -AppDir $RepoRoot `
    -AppParameters $CaddyParams `
    -LogPrefix "caddy" `
    -Dependencies @("SmartHome3D-SpatialServer", "SmartHome3D-go2rtc") `
    -EnvLines @()

# 7. Regole Windows Defender Firewall per WebRTC (:8555 TCP/UDP limitato a LAN + Tailscale CGNAT)
if (-not $SkipFirewall) {
    Write-Host "[*] Configurazione regole Windows Defender Firewall per WebRTC :8555 (LAN $LanCidr + Tailscale 100.64.0.0/10)..." -ForegroundColor Cyan
    Get-NetFirewallRule -DisplayName "SmartHome3D-WebRTC-*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Get-NetFirewallRule -Name "SmartHome3D-WebRTC-*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

    $RemoteAddresses = @($LanCidr, "100.64.0.0/10")

    New-NetFirewallRule `
        -Name "SmartHome3D-WebRTC-TCP-8555" `
        -DisplayName "SmartHome3D-WebRTC-TCP-8555" `
        -Description "Consente WebRTC ICE TCP sulla porta 8555 solo da LAN locale ($LanCidr) e Tailscale CGNAT (100.64.0.0/10)." `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Any `
        -Protocol TCP `
        -LocalPort 8555 `
        -RemoteAddress $RemoteAddresses | Out-Null

    New-NetFirewallRule `
        -Name "SmartHome3D-WebRTC-UDP-8555" `
        -DisplayName "SmartHome3D-WebRTC-UDP-8555" `
        -Description "Consente media WebRTC UDP sulla porta 8555 solo da LAN locale ($LanCidr) e Tailscale CGNAT (100.64.0.0/10)." `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Any `
        -Protocol UDP `
        -LocalPort 8555 `
        -RemoteAddress $RemoteAddresses | Out-Null

    Write-Host "[OK] Regole Firewall SmartHome3D-WebRTC-TCP-8555 e SmartHome3D-WebRTC-UDP-8555 configurate." -ForegroundColor Green
} else {
    Write-Host "[*] -SkipFirewall specificato: regole Windows Defender Firewall non modificate." -ForegroundColor Yellow
}

# 8. Avvio ordinato dei servizi
if (-not $NoStart) {
    $StartOrder = @("SmartHome3D-go2rtc", "SmartHome3D-SpatialServer", "SmartHome3D-Caddy")
    foreach ($svcName in $StartOrder) {
        Write-Host "[*] Avvio servizio $svcName..." -ForegroundColor Cyan
        Start-Service -Name $svcName
        $svc = Get-Service -Name $svcName
        try {
            $svc.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(15))
        } catch {
            throw "Il servizio $svcName non è entrato in stato Running entro 15s (stato attuale: $($svc.Status)). Controlla i log in $LogsDir."
        }
        if ($svc.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {
            throw "Il servizio $svcName non è in stato Running (stato attuale: $($svc.Status))."
        }
        Write-Host "[OK] $svcName avviato (Running)." -ForegroundColor Green
    }
} else {
    Write-Host "[*] -NoStart specificato: servizi registrati/aggiornati ma non avviati." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== INSTALLAZIONE COMPLETATA ===" -ForegroundColor Green
Write-Host "Nota: se modifichi .env in futuro, riesegui scripts\install_windows_services.ps1 (o scripts\update_services.bat da Admin) per aggiornare AppEnvironmentExtra nei servizi NSSM."
