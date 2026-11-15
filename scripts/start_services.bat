@echo off
setlocal EnableExtensions DisableDelayedExpansion

cd /d "%~dp0\.."
set "REPO_ROOT=%CD%"

echo === SMART HOME 3D - AVVIO SERVIZI NATIVI (go2rtc + spatial_server) ===
echo Cartella: %REPO_ROOT%

if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

rem Supporto retrocompatibile tra REOLINK_CARRAIO_PASS e REOLINK_CARRAIO_PASSWORD
if not defined REOLINK_CARRAIO_PASS if defined REOLINK_CARRAIO_PASSWORD set "REOLINK_CARRAIO_PASS=%REOLINK_CARRAIO_PASSWORD%"
if not defined MQTT_PASS if defined MQTT_PASSWORD set "MQTT_PASS=%MQTT_PASSWORD%"

if "%SPATIAL_SERVER_HOST%"=="" set "SPATIAL_SERVER_HOST=0.0.0.0"
if "%SPATIAL_SERVER_PORT%"=="" set "SPATIAL_SERVER_PORT=8765"

if not exist "go2rtc\go2rtc.exe" (
    echo [ERRORE] go2rtc\go2rtc.exe non trovato. Esegui prima scripts\setup_windows_node.ps1
    exit /b 1
)

if not exist ".venv\Scripts\uvicorn.exe" (
    echo [ERRORE] Virtualenv .venv non configurato. Esegui prima scripts\setup_windows_node.ps1
    exit /b 1
)

rem Chiude eventuali istanze precedenti per garantire il ricaricamento pulito di .env
taskkill /F /IM go2rtc.exe /T >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spatial_server.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [*] Avvio go2rtc su porta 1984 (WebRTC/MSE/RTSP)...
start "go2rtc Server" /MIN /D "%REPO_ROOT%\go2rtc" "%REPO_ROOT%\go2rtc\go2rtc.exe" -c "%REPO_ROOT%\go2rtc\go2rtc.yaml"

ping -n 3 127.0.0.1 >nul

echo [*] Avvio Spatial CV Server (FastAPI) su %SPATIAL_SERVER_HOST%:%SPATIAL_SERVER_PORT%...
start "Spatial CV Server" /MIN /D "%REPO_ROOT%" "%REPO_ROOT%\.venv\Scripts\uvicorn.exe" spatial_server.main:app --host %SPATIAL_SERVER_HOST% --port %SPATIAL_SERVER_PORT%

echo.
echo [OK] Servizi avviati in background:
echo   - go2rtc Web UI / API:   http://localhost:1984
echo   - Spatial API Status:    http://localhost:%SPATIAL_SERVER_PORT%/api/v1/status
echo   - Spatial WebSocket:     ws://localhost:%SPATIAL_SERVER_PORT%/ws/spatial
echo.
echo Per arrestare tutto: scripts\stop_services.bat
endlocal
