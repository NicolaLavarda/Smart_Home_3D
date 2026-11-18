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

for /f "delims=" %%H in ('git rev-parse HEAD') do set "OLD_HEAD=%%H"

echo [*] Scaricamento aggiornamenti da origin/main...
git fetch origin main
if errorlevel 1 (
    echo [ERRORE] git fetch fallito. Servizi lasciati in esecuzione senza modifiche.
    exit /b 1
)

echo [*] Arresto servizi attivi...
call "%REPO_ROOT%\scripts\stop_services.bat"

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

for /f "delims=" %%H in ('git rev-parse HEAD') do set "NEW_HEAD=%%H"

if not exist "go2rtc\go2rtc.exe" (
    echo [*] go2rtc.exe mancante: eseguo setup_windows_node.ps1...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\setup_windows_node.ps1" -WithOpenVINO
    if errorlevel 1 (
        echo [ERRORE] setup_windows_node.ps1 fallito.
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Virtualenv .venv mancante: eseguo setup_windows_node.ps1...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\setup_windows_node.ps1" -WithOpenVINO
    if errorlevel 1 (
        echo [ERRORE] setup_windows_node.ps1 fallito.
        exit /b 1
    )
)

if /I "%~1"=="--deps" goto force_deps
if /I "%OLD_HEAD%"=="%NEW_HEAD%" goto check_node_build

echo [*] Controllo dipendenze tra %OLD_HEAD:~0,7% e %NEW_HEAD:~0,7%...

git diff --quiet "%OLD_HEAD%" "%NEW_HEAD%" -- spatial_server/requirements.txt
if errorlevel 1 (
    echo [*] spatial_server\requirements.txt modificato: aggiorno .venv...
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m pip install -r "%REPO_ROOT%\spatial_server\requirements.txt"
    if errorlevel 1 (
        echo [ERRORE] Aggiornamento dipendenze Python fallito.
        exit /b 1
    )
)

where npm.cmd >nul 2>&1
if not errorlevel 1 (
    git diff --quiet "%OLD_HEAD%" "%NEW_HEAD%" -- package.json package-lock.json
    if errorlevel 1 (
        echo [*] package.json / package-lock.json modificati: eseguo npm.cmd install...
        call npm.cmd install
        if errorlevel 1 (
            echo [ERRORE] npm.cmd install fallito ^(se hai npm run dev aperto, fermalo con Ctrl+C e riprova^).
            exit /b 1
        )
    )
)
goto check_node_build

:force_deps
echo [*] Aggiornamento forzato dipendenze (--deps)...
"%REPO_ROOT%\.venv\Scripts\python.exe" -m pip install -r "%REPO_ROOT%\spatial_server\requirements.txt"
if errorlevel 1 (
    echo [ERRORE] Aggiornamento dipendenze Python fallito.
    exit /b 1
)
where npm.cmd >nul 2>&1
if not errorlevel 1 (
    if exist "%REPO_ROOT%\node_modules" (
        call npm.cmd install
        if errorlevel 1 (
            echo [ERRORE] npm.cmd install fallito.
            exit /b 1
        )
    )
)

:check_node_build
if exist "%REPO_ROOT%\dist" (
    where npm.cmd >nul 2>&1
    if not errorlevel 1 (
        if /I "%~1"=="--deps" (
            echo [*] Cartella dist\ presente: ricostruisco frontend...
            call npm.cmd run build
            if errorlevel 1 exit /b 1
        ) else if /I not "%OLD_HEAD%"=="%NEW_HEAD%" (
            git diff --quiet "%OLD_HEAD%" "%NEW_HEAD%" -- index.html package.json vite.config.js src public
            if errorlevel 1 (
                echo [*] Cartella dist\ presente e frontend modificato: eseguo npm.cmd run build...
                call npm.cmd run build
                if errorlevel 1 exit /b 1
            )
        )
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
