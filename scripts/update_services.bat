@echo off
setlocal EnableExtensions DisableDelayedExpansion

cd /d "%~dp0\.."
set "REPO_ROOT=%CD%"

echo === SMART HOME 3D - AGGIORNAMENTO E RIAVVIO SERVIZI ===
echo Cartella: %REPO_ROOT%

where git >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Git non trovato nel PATH.
    exit /b 1
)

set "OLD_HEAD="
for /f "delims=" %%H in ('git rev-parse HEAD') do set "OLD_HEAD=%%H"
if "%OLD_HEAD%"=="" (
    echo [ERRORE] Impossibile determinare il commit corrente HEAD.
    exit /b 1
)

echo [*] Scaricamento aggiornamenti da origin/main...
git fetch origin main
if errorlevel 1 (
    echo [ERRORE] git fetch fallito. Servizi lasciati in esecuzione senza modifiche.
    exit /b 1
)

echo [*] Arresto servizi attivi...
call "%REPO_ROOT%\scripts\stop_services.bat"
if errorlevel 1 (
    echo [ERRORE] Arresto servizi fallito: aggiornamento annullato per evitare conflitti sui file.
    exit /b 1
)

echo [*] Riallineamento forzato dei file tracciati a origin/main...
git checkout -f -B main origin/main
if errorlevel 1 (
    echo [ERRORE] Impossibile riallineare il branch main a origin/main.
    exit /b 1
)
git reset --hard origin/main
if errorlevel 1 (
    echo [ERRORE] git reset --hard origin/main fallito.
    exit /b 1
)

set "NEW_HEAD="
for /f "delims=" %%H in ('git rev-parse HEAD') do set "NEW_HEAD=%%H"
if "%NEW_HEAD%"=="" (
    echo [ERRORE] Impossibile determinare il nuovo commit HEAD.
    exit /b 1
)

set "NEED_BOOTSTRAP=0"
if not exist "%REPO_ROOT%\go2rtc\go2rtc.exe" set "NEED_BOOTSTRAP=1"
if not exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "NEED_BOOTSTRAP=1"
if not exist "%REPO_ROOT%\caddy\caddy.exe" set "NEED_BOOTSTRAP=1"
if not exist "%REPO_ROOT%\tools\nssm.exe" set "NEED_BOOTSTRAP=1"

if "%NEED_BOOTSTRAP%"=="1" (
    echo [*] Componenti nativi o .venv mancanti: eseguo setup_windows_node.ps1...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\setup_windows_node.ps1" -WithOpenVINO
    if errorlevel 1 (
        echo [ERRORE] setup_windows_node.ps1 fallito.
        exit /b 1
    )
)

set "NEED_PIP=0"
set "NEED_NPM=0"
if /I "%~1"=="--deps" (
    set "NEED_PIP=1"
    set "NEED_NPM=1"
) else (
    if not exist "%REPO_ROOT%\node_modules" set "NEED_NPM=1"
    if /I not "%OLD_HEAD%"=="%NEW_HEAD%" (
        git diff --quiet "%OLD_HEAD%" "%NEW_HEAD%" -- spatial_server/requirements.txt
        if errorlevel 1 set "NEED_PIP=1"
        git diff --quiet "%OLD_HEAD%" "%NEW_HEAD%" -- package.json package-lock.json
        if errorlevel 1 set "NEED_NPM=1"
    )
)

if "%NEED_PIP%"=="1" (
    echo [*] Aggiornamento dipendenze Python ^(.venv^)...
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m pip install -r "%REPO_ROOT%\spatial_server\requirements.txt"
    if errorlevel 1 (
        echo [ERRORE] Aggiornamento dipendenze Python fallito.
        exit /b 1
    )
)

if exist "%REPO_ROOT%\tools\download_yolo_openvino_model.py" if not exist "%REPO_ROOT%\spatial_server\models\yolov8n_openvino_model\yolov8n.xml" (
    echo [*] Modello YOLOv8n OpenVINO mancante: download e conversione in corso...
    "%REPO_ROOT%\.venv\Scripts\python.exe" "%REPO_ROOT%\tools\download_yolo_openvino_model.py"
    if errorlevel 1 (
        echo [ERRORE] Download/conversione modello YOLOv8n fallito.
        exit /b 1
    )
)

if "%NEED_NPM%"=="1" (
    where npm.cmd >nul 2>&1
    if errorlevel 1 (
        echo [ERRORE] npm.cmd non trovato nel PATH: impossibile installare le dipendenze Node.
        exit /b 1
    )
    echo [*] Aggiornamento dipendenze Node ^(npm.cmd install^)...
    call npm.cmd install
    if errorlevel 1 (
        echo [ERRORE] npm.cmd install fallito ^(se hai npm run dev aperto, fermalo con Ctrl+C e riprova^).
        exit /b 1
    )
)

set "NEED_BUILD=0"
if not exist "%REPO_ROOT%\dist" set "NEED_BUILD=1"
if not exist "%REPO_ROOT%\dist\index.html" set "NEED_BUILD=1"
if not exist "%REPO_ROOT%\dist\sw.js" set "NEED_BUILD=1"
if /I "%~1"=="--deps" set "NEED_BUILD=1"
if "%NEED_BUILD%"=="0" if /I not "%OLD_HEAD%"=="%NEW_HEAD%" (
    git diff --quiet "%OLD_HEAD%" "%NEW_HEAD%" -- index.html package.json package-lock.json vite.config.js src public
    if errorlevel 1 set "NEED_BUILD=1"
)

if "%NEED_BUILD%"=="1" (
    where npm.cmd >nul 2>&1
    if errorlevel 1 (
        echo [ERRORE] npm.cmd non trovato nel PATH: impossibile compilare il frontend dist\.
        exit /b 1
    )
    if not exist "%REPO_ROOT%\node_modules" (
        call npm.cmd install
        if errorlevel 1 (
            echo [ERRORE] npm.cmd install fallito.
            exit /b 1
        )
    )
    echo [*] Compilazione frontend PWA ^(npm.cmd run build^)...
    call npm.cmd run build
    if errorlevel 1 (
        echo [ERRORE] npm.cmd run build fallito.
        exit /b 1
    )
)

set "HAS_NSSM=0"
sc query SmartHome3D-go2rtc >nul 2>&1 && set "HAS_NSSM=1"
sc query SmartHome3D-SpatialServer >nul 2>&1 && set "HAS_NSSM=1"
sc query SmartHome3D-Caddy >nul 2>&1 && set "HAS_NSSM=1"
if "%HAS_NSSM%"=="1" if exist "%REPO_ROOT%\scripts\install_windows_services.ps1" (
    net session >nul 2>&1
    if not errorlevel 1 (
        echo [*] Aggiornamento variabili .env e configurazione servizi NSSM...
        powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\install_windows_services.ps1" -NoStart -SkipFirewall
        if errorlevel 1 (
            echo [ERRORE] Aggiornamento configurazione servizi NSSM fallito.
            exit /b 1
        )
    ) else (
        echo [AVVISO] Servizi NSSM installati ma prompt non Amministratore: se hai modificato .env, riesegui scripts\install_windows_services.ps1 da Admin.
    )
)

if exist "%REPO_ROOT%\caddy\caddy.exe" if exist "%REPO_ROOT%\caddy\Caddyfile" (
    echo [*] Validazione caddy\Caddyfile...
    "%REPO_ROOT%\caddy\caddy.exe" validate --config "%REPO_ROOT%\caddy\Caddyfile" --adapter caddyfile
    if errorlevel 1 (
        echo [ERRORE] caddy\Caddyfile non valido.
        exit /b 1
    )
    tasklist /FI "IMAGENAME eq caddy.exe" | find /I "caddy.exe" >nul 2>&1
    if not errorlevel 1 (
        "%REPO_ROOT%\caddy\caddy.exe" reload --config "%REPO_ROOT%\caddy\Caddyfile" --adapter caddyfile >nul 2>&1
    )
)

echo [*] Riavvio servizi...
call "%REPO_ROOT%\scripts\start_services.bat"
if errorlevel 1 (
    echo [ERRORE] Avvio servizi fallito.
    exit /b 1
)

echo.
echo [OK] Aggiornamento completato (%OLD_HEAD:~0,7% -^> %NEW_HEAD:~0,7%).
echo Se hai "npm.cmd run dev" attivo nell'altro terminale, ricarica la pagina (F5).
endlocal
exit /b 0
