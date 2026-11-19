@echo off
setlocal EnableExtensions DisableDelayedExpansion

cd /d "%~dp0\.."
set "REPO_ROOT=%CD%"

echo === ARRESTO SERVIZI SMART HOME 3D ===

call :stop_win_service "SmartHome3D-Caddy"
if errorlevel 1 exit /b 1
call :stop_win_service "SmartHome3D-SpatialServer"
if errorlevel 1 exit /b 1
call :stop_win_service "SmartHome3D-go2rtc"
if errorlevel 1 exit /b 1

echo [*] Terminazione eventuali processi console residui (caddy, go2rtc, spatial_server)...
taskkill /F /IM caddy.exe /T >nul 2>&1
taskkill /F /IM go2rtc.exe /T >nul 2>&1
powershell -NoProfile -Command "$repo = $env:REPO_ROOT; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spatial_server.main:app*' -or ($_.Name -eq 'uvicorn.exe' -and $repo -and $_.ExecutablePath -like ($repo + '\*')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [OK] Servizi arrestati.
endlocal
exit /b 0

:stop_win_service
sc query "%~1" >nul 2>&1
if errorlevel 1 exit /b 0

sc query "%~1" | find /I "STOPPED" >nul
if not errorlevel 1 exit /b 0

echo [*] Arresto servizio Windows %~1...
if exist "%REPO_ROOT%\tools\nssm.exe" (
    "%REPO_ROOT%\tools\nssm.exe" stop "%~1" >nul 2>&1
) else (
    net stop "%~1" /y >nul 2>&1
)

sc query "%~1" | find /I "STOPPED" >nul
if not errorlevel 1 exit /b 0

net stop "%~1" /y >nul 2>&1
for /L %%I in (1,1,15) do (
    sc query "%~1" | find /I "STOPPED" >nul
    if not errorlevel 1 exit /b 0
    ping -n 2 127.0.0.1 >nul
)

echo [ERRORE] Impossibile arrestare %~1 ^(esegui il prompt come Amministratore^).
exit /b 1

