@echo off
setlocal
echo === ARRESTO SERVIZI SMART HOME 3D ===

echo [*] Terminazione go2rtc.exe...
taskkill /F /IM go2rtc.exe /T >nul 2>&1

echo [*] Terminazione uvicorn / spatial_server...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spatial_server.main:app*' -or $_.Name -eq 'uvicorn.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [OK] Servizi arrestati.
endlocal

