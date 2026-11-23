<#
.SYNOPSIS
Audit sicuro e dismissione reversibile del server CodeProject.AI su Windows 10 (i5-6400 / 8 GB RAM)
dopo la messa in produzione del sottosistema biometrico nativo dentro SmartHome3D-SpatialServer.
In modalita' predefinita (senza -Apply) esegue esclusivamente un audit in sola lettura (dry-run).
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$SkipSpatialCheck
)

$ErrorActionPreference = "Stop"

Write-Host "=== SMART HOME 3D - AUDIT & DISMISSIONE CODEPROJECT.AI ===" -ForegroundColor Cyan

$osInfo = $null
try {
    $osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
} catch {
    $osInfo = $null
}
$freeRamBeforeMb = if ($osInfo -and $osInfo.FreePhysicalMemory) {
    [math]::Round($osInfo.FreePhysicalMemory / 1024.0, 1)
} else {
    0.0
}
$totalRamMb = if ($osInfo -and $osInfo.TotalVisibleMemorySize) {
    [math]::Round($osInfo.TotalVisibleMemorySize / 1024.0, 1)
} else {
    0.0
}
Write-Host ("RAM fisica libera attuale: {0} MB su {1} MB" -f $freeRamBeforeMb, $totalRamMb)

$cpaiServices = @()
try {
    $cpaiServices = @(
        Get-Service -ErrorAction Stop | Where-Object {
            $_.Name -like "*CodeProject*" -or $_.DisplayName -like "*CodeProject*"
        }
    )
} catch {
    $cpaiServices = @()
}
$cpaiServicePids = New-Object 'System.Collections.Generic.HashSet[int]'
$cpaiServiceInfo = @()
foreach ($svc in $cpaiServices) {
    $cimSvc = $null
    try {
        $cimSvc = Get-CimInstance Win32_Service -Filter ("Name='{0}'" -f $svc.Name.Replace("'", "''")) -ErrorAction Stop
    } catch {
        $cimSvc = $null
    }
    $startMode = if ($cimSvc) { $cimSvc.StartMode } else { "Unknown" }
    if ($cimSvc -and $cimSvc.ProcessId -and [int]$cimSvc.ProcessId -gt 0) {
        [void]$cpaiServicePids.Add([int]$cimSvc.ProcessId)
    }
    $cpaiServiceInfo += [pscustomobject]@{
        Service   = $svc
        StartMode = $startMode
        Pid       = if ($cimSvc -and $cimSvc.ProcessId) { [int]$cimSvc.ProcessId } else { 0 }
    }
}

# Rileva sia i processi principali (.NET) sia tutti i worker figli (es. python.exe dei moduli AI)
$allCimProcs = @()
try {
    $allCimProcs = @(Get-CimInstance Win32_Process -ErrorAction Stop)
} catch {
    $allCimProcs = @()
}

$excludedShells = @("powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe")
$cpaiPidSet = New-Object 'System.Collections.Generic.HashSet[int]'
$cimByPid = @{}

if ($allCimProcs.Count -gt 0) {
    $childrenByParent = @{}
    foreach ($p in $allCimProcs) {
        $procPid = [int]$p.ProcessId
        $parentPid = [int]$p.ParentProcessId
        $cimByPid[$procPid] = $p
        if (-not $childrenByParent.ContainsKey($parentPid)) {
            $childrenByParent[$parentPid] = New-Object 'System.Collections.Generic.List[int]'
        }
        [void]$childrenByParent[$parentPid].Add($procPid)
    }

    $seedQueue = New-Object 'System.Collections.Generic.Queue[int]'
    foreach ($p in $allCimProcs) {
        $procPid = [int]$p.ProcessId
        if ($procPid -eq $PID) { continue }
        $pname = [string]$p.Name
        if ($excludedShells -contains $pname.ToLowerInvariant()) { continue }

        $exePath = [string]$p.ExecutablePath
        $cmdLine = [string]$p.CommandLine
        $isSeed = $cpaiServicePids.Contains($procPid) -or
                  $pname -like "CodeProject*" -or
                  $pname -like "AnalysisLayer*" -or
                  $exePath -like "*CodeProject*AI*" -or
                  $cmdLine -like "*CodeProject*AI*" -or
                  $cmdLine -like "*AnalysisLayer*"

        if ($isSeed -and $cpaiPidSet.Add($procPid)) {
            $seedQueue.Enqueue($procPid)
        }
    }

    # Espande ricorsivamente tutti i figli dei processi CodeProject.AI (es. worker python/onnx/paddle)
    while ($seedQueue.Count -gt 0) {
        $parentId = $seedQueue.Dequeue()
        if ($childrenByParent.ContainsKey($parentId)) {
            foreach ($childPid in $childrenByParent[$parentId]) {
                if ($childPid -ne $PID -and $cpaiPidSet.Add($childPid)) {
                    $seedQueue.Enqueue($childPid)
                }
            }
        }
    }
} else {
    foreach ($gp in (Get-Process -ErrorAction SilentlyContinue)) {
        if ($gp.Id -ne $PID -and ($gp.ProcessName -like "CodeProject*" -or $gp.ProcessName -like "AnalysisLayer*")) {
            [void]$cpaiPidSet.Add([int]$gp.Id)
        }
    }
}

$cpaiProcesses = @()
foreach ($cpaiPid in ($cpaiPidSet | Sort-Object)) {
    $procObj = Get-Process -Id $cpaiPid -ErrorAction SilentlyContinue
    if ($null -ne $procObj) {
        $cimProc = $cimByPid[$cpaiPid]
        $cpaiProcesses += [pscustomobject]@{
            Process     = $procObj
            Id          = $cpaiPid
            ProcessName = $procObj.ProcessName
            WorkingMb   = [math]::Round($procObj.WorkingSet64 / 1MB, 1)
            PrivateMb   = [math]::Round($procObj.PrivateMemorySize64 / 1MB, 1)
            ExePath     = if ($cimProc) { [string]$cimProc.ExecutablePath } else { "" }
        }
    }
}

$port32168 = @()
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $port32168 = @(Get-NetTCPConnection -LocalPort 32168 -State Listen -ErrorAction SilentlyContinue)
}

Write-Host ("Servizi Windows CodeProject.AI rilevati: {0}" -f $cpaiServices.Count)
foreach ($item in $cpaiServiceInfo) {
    Write-Host ("  - {0} ({1}): Status={2}, StartMode={3}" -f $item.Service.Name, $item.Service.DisplayName, $item.Service.Status, $item.StartMode)
}

$totalProcWorkingMb = 0.0
$totalProcPrivateMb = 0.0
Write-Host ("Processi attivi CodeProject.AI (inclusi worker figli): {0}" -f $cpaiProcesses.Count)
foreach ($entry in $cpaiProcesses) {
    $totalProcWorkingMb += $entry.WorkingMb
    $totalProcPrivateMb += $entry.PrivateMb
    Write-Host ("  - PID {0} ({1}): WorkingSet={2} MB, Private={3} MB" -f $entry.Id, $entry.ProcessName, $entry.WorkingMb, $entry.PrivateMb)
}
Write-Host ("Impronta RAM stimata processi CodeProject.AI: {0} MB WorkingSet ({1} MB Private)" -f [math]::Round($totalProcWorkingMb, 1), [math]::Round($totalProcPrivateMb, 1))

if ($port32168.Count -gt 0) {
    Write-Host "[*] Porta TCP 32168 (API CodeProject.AI) attualmente in ascolto." -ForegroundColor Yellow
} else {
    Write-Host "[OK] Porta TCP 32168 non in ascolto." -ForegroundColor Green
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "[DRY-RUN] Nessuna modifica applicata al sistema." -ForegroundColor Yellow
    if ($cpaiServices.Count -gt 0 -or $cpaiProcesses.Count -gt 0) {
        Write-Host "Per arrestare e disabilitare CodeProject.AI in sicurezza dopo aver verificato SmartHome3D-SpatialServer:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\decommission_codeproject_ai.ps1 -Apply"
    } else {
        Write-Host "[OK] Nessun servizio o processo CodeProject.AI attivo da dismettere." -ForegroundColor Green
    }
    exit 0
}

# Modalita' -Apply: richiede privilegi Amministratore
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[ERRORE] L'opzione -Apply richiede una sessione PowerShell come Amministratore." -ForegroundColor Red
    exit 1
}

if (-not $SkipSpatialCheck) {
    $spatialSvc = Get-Service -Name "SmartHome3D-SpatialServer" -ErrorAction SilentlyContinue
    if ($null -eq $spatialSvc -or $spatialSvc.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {
        $st = if ($null -eq $spatialSvc) { "Non installato" } else { [string]$spatialSvc.Status }
        Write-Host ("[ERRORE] SmartHome3D-SpatialServer non e' attivo (stato: {0}). Verifica la biometria locale o passa -SkipSpatialCheck per forzare." -f $st) -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] SmartHome3D-SpatialServer attivo e verificato." -ForegroundColor Green
}

foreach ($svc in $cpaiServices) {
    if ($svc.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
        Write-Host ("[*] Arresto servizio {0}..." -f $svc.Name) -ForegroundColor Cyan
        Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
        try {
            $svc.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(20))
        } catch {
            Write-Host ("[WARN] Timeout arresto servizio {0}." -f $svc.Name) -ForegroundColor Yellow
        }
    }
    Write-Host ("[*] Imposto StartupType=Disabled su {0}..." -f $svc.Name) -ForegroundColor Cyan
    Set-Service -Name $svc.Name -StartupType Disabled
    Write-Host ("[OK] Servizio {0} arrestato e disabilitato (rollback: Set-Service -Name '{0}' -StartupType Automatic; Start-Service -Name '{0}')." -f $svc.Name) -ForegroundColor Green
}

foreach ($entry in $cpaiProcesses) {
    if ($entry.Process -and -not $entry.Process.HasExited) {
        Stop-Process -Id $entry.Id -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 2
$osAfter = $null
try {
    $osAfter = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
} catch {
    $osAfter = $null
}
$freeRamAfterMb = if ($osAfter -and $osAfter.FreePhysicalMemory) {
    [math]::Round($osAfter.FreePhysicalMemory / 1024.0, 1)
} else {
    $freeRamBeforeMb
}
$recoveredMb = [math]::Round($freeRamAfterMb - $freeRamBeforeMb, 1)

Write-Host ""
Write-Host "=== DISMISSIONE COMPLETATA ===" -ForegroundColor Green
Write-Host ("RAM libera dopo l'arresto: {0} MB (variazione: {1:+#0.0;-#0.0;0.0} MB)" -f $freeRamAfterMb, $recoveredMb)
Write-Host "Ricorda di verificare che in .env la variabile FACE_RECOGNITION_WEBHOOK_URL= sia vuota e BIOMETRICS_ENABLED=true."
