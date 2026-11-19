@echo off
setlocal EnableExtensions DisableDelayedExpansion

cd /d "%~dp0\.."
set "REPO_ROOT=%CD%"

echo === SMART HOME 3D - AVVIO SERVIZI NATIVI (go2rtc + spatial_server + Caddy) ===
echo Cartella: %REPO_ROOT%

if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        set "_K=%%A"
        set "_V=%%~B"
        call :apply_env
    )
)

rem Supporto retrocompatibile tra REOLINK_CARRAIO_PASS e REOLINK_CARRAIO_PASSWORD
if not defined REOLINK_CARRAIO_PASS if defined REOLINK_CARRAIO_PASSWORD set "REOLINK_CARRAIO_PASS=%REOLINK_CARRAIO_PASSWORD%"
if not defined MQTT_PASS if defined MQTT_PASSWORD set "MQTT_PASS=%MQTT_PASSWORD%"

if "%SPATIAL_SERVER_HOST%"=="" set "SPATIAL_SERVER_HOST=127.0.0.1"
if "%SPATIAL_SERVER_PORT%"=="" set "SPATIAL_SERVER_PORT=8765"

set "USE_NSSM=0"
sc query SmartHome3D-go2rtc >nul 2>&1 && set "USE_NSSM=1"
sc query SmartHome3D-SpatialServer >nul 2>&1 && set "USE_NSSM=1"
sc query SmartHome3D-Caddy >nul 2>&1 && set "USE_NSSM=1"
if "%USE_NSSM%"=="1" goto start_nssm_services

rem Modalita console / sviluppo (servizi NSSM non registrati)
if not exist "go2rtc\go2rtc.exe" (
    echo [ERRORE] go2rtc\go2rtc.exe non trovato. Esegui prima scripts\setup_windows_node.ps1
    exit /b 1
)

if not exist ".venv\Scripts\uvicorn.exe" (
    echo [ERRORE] Virtualenv .venv non configurato. Esegui prima scripts\setup_windows_node.ps1
    exit /b 1
)

set "START_CADDY=0"
if exist "caddy\caddy.exe" if exist "caddy\Caddyfile" set "START_CADDY=1"
if "%START_CADDY%"=="1" (
    if not exist "dist\index.html" (
        echo [AVVISO] dist\index.html non trovato: Caddy servira' il fallback SPA solo dopo 'npm.cmd run build'.
    )
) else (
    echo [AVVISO] caddy\caddy.exe o caddy\Caddyfile mancante: avvio senza reverse proxy Caddy.
)

rem Chiude eventuali istanze console precedenti per garantire il ricaricamento pulito di .env
taskkill /F /IM caddy.exe /T >nul 2>&1
taskkill /F /IM go2rtc.exe /T >nul 2>&1
powershell -NoProfile -Command "$repo = $env:REPO_ROOT; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spatial_server.main:app*' -or ($_.Name -eq 'uvicorn.exe' -and $repo -and $_.ExecutablePath -like ($repo + '\*')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [*] Avvio go2rtc su 127.0.0.1:1984 (WebRTC/MSE/RTSP)...
start "go2rtc Server" /MIN /D "%REPO_ROOT%\go2rtc" "%REPO_ROOT%\go2rtc\go2rtc.exe" -c "%REPO_ROOT%\go2rtc\go2rtc.yaml"

ping -n 3 127.0.0.1 >nul

echo [*] Avvio Spatial CV Server (FastAPI) su %SPATIAL_SERVER_HOST%:%SPATIAL_SERVER_PORT%...
start "Spatial CV Server" /MIN /D "%REPO_ROOT%" "%REPO_ROOT%\.venv\Scripts\uvicorn.exe" spatial_server.main:app --host %SPATIAL_SERVER_HOST% --port %SPATIAL_SERVER_PORT%

if "%START_CADDY%"=="1" (
    ping -n 3 127.0.0.1 >nul
    echo [*] Avvio Caddy Reverse Proxy su http://127.0.0.1:8080...
    start "Caddy Reverse Proxy" /MIN /D "%REPO_ROOT%" "%REPO_ROOT%\caddy\caddy.exe" run --config "%REPO_ROOT%\caddy\Caddyfile" --adapter caddyfile
)

echo.
echo [OK] Servizi avviati in modalita' console:
if "%START_CADDY%"=="1" echo   - Caddy Same-Origin:     http://127.0.0.1:8080
echo   - Spatial API Status:    http://127.0.0.1:%SPATIAL_SERVER_PORT%/api/v1/status
echo   - Spatial WebSocket:     ws://127.0.0.1:%SPATIAL_SERVER_PORT%/ws/spatial
echo   - go2rtc API (loopback): http://127.0.0.1:1984
echo.
echo Per arrestare tutto: scripts\stop_services.bat
endlocal
exit /b 0

:start_nssm_services
echo [*] Rilevati servizi Windows NSSM: avvio in ordine di dipendenza...
call :start_win_service "SmartHome3D-go2rtc"
if errorlevel 1 exit /b 1
call :start_win_service "SmartHome3D-SpatialServer"
if errorlevel 1 exit /b 1
call :start_win_service "SmartHome3D-Caddy"
if errorlevel 1 exit /b 1

echo.
echo [OK] Servizi Windows NSSM attivi:
echo   - Caddy Same-Origin:     http://127.0.0.1:8080
echo   - Spatial API Status:    http://127.0.0.1:%SPATIAL_SERVER_PORT%/api/v1/status
echo   - go2rtc API (loopback): http://127.0.0.1:1984
echo.
echo Per arrestare tutto: scripts\stop_services.bat
endlocal
exit /b 0

:start_win_service
sc query "%~1" >nul 2>&1
if errorlevel 1 (
    echo [AVVISO] Servizio %~1 non registrato, salto.
    exit /b 0
)
sc query "%~1" | find /I "RUNNING" >nul
if not errorlevel 1 (
    echo [OK] %~1 gia' attivo.
    exit /b 0
)
if exist "%REPO_ROOT%\tools\nssm.exe" (
    "%REPO_ROOT%\tools\nssm.exe" start "%~1" >nul 2>&1
) else (
    net start "%~1" >nul 2>&1
)
sc query "%~1" | find /I "RUNNING" >nul
if not errorlevel 1 (
    echo [OK] %~1 avviato.
    exit /b 0
)
net start "%~1" >nul 2>&1
sc query "%~1" | find /I "RUNNING" >nul
if errorlevel 1 (
    echo [ERRORE] Impossibile avviare %~1 ^(esegui il prompt come Amministratore^).
    exit /b 1
)
echo [OK] %~1 avviato.
exit /b 0

:apply_env
set "_K_CLEAN="
for /f "tokens=1,*" %%X in ("%_K%") do (
    if /I "%%X"=="export" (
        if not "%%Y"=="" (
            set "_K_CLEAN=%%Y"
        ) else (
            set "_K_CLEAN=%%X"
        )
    ) else (
        set "_K_CLEAN=%%X"
    )
)
set "_K=%_K_CLEAN%"
if "%_K%"=="" goto :apply_env_cleanup
if "%_K:~0,1%"=="#" goto :apply_env_cleanup
if "%_K:~0,1%"==";" goto :apply_env_cleanup
if not defined _V goto :apply_env_set
if "%_V:~0,1%"=="'" if "%_V:~-1%"=="'" set "_V=%_V:~1,-1%"
:apply_env_set
set "%_K%=%_V%"
:apply_env_cleanup
set "_K="
set "_K_CLEAN="
set "_V="
goto :eof
