@echo off
title FireGuard AI - Startup
color 0A
setlocal

echo.
echo  ============================================
echo   FIREGUARD AI - Intelligent Fire Detection
echo  ============================================
echo.

:: ---- Python 3.10 - 3.12 (numpy 1.26 / torch wheels) via the py launcher
set "PY="
for %%V in (3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V --version >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    echo [ERROR] Python 3.10, 3.11 or 3.12 is required ^(3.13 is not supported by the pinned packages^).
    echo         Install it from https://www.python.org/downloads/ and re-run.
    pause
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

:: ---- Backend virtual environment
if not exist "backend\venv\Scripts\activate.bat" (
    echo [SETUP] Creating Python virtual environment with %PY% ...
    pushd backend
    %PY% -m venv venv
    call venv\Scripts\activate.bat
    echo [SETUP] Installing CPU PyTorch ...
    python -m pip install --upgrade pip
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    pip install -r requirements.txt
    popd
) else (
    echo [OK] Python virtual environment found.
)

if not exist "backend\.env" (
    echo [SETUP] Creating backend\.env from template...
    copy "backend\.env.example" "backend\.env" >nul
)

:: ---- Demo assets
if not exist "backend\models\best.pt" (
    echo [WARN] backend\models\best.pt not found - the colour-segmentation fallback will be used.
    echo        Copy your trained YOLOv8 weights to backend\models\best.pt
)
if not exist "backend\media\clips.json" (
    echo [WARN] No demo clips in backend\media - see README "Demo assets" ^(tools\prepare_media.py^).
)

echo.
echo [START] FastAPI backend on http://localhost:8000 ...
:: Backend listens on localhost only; the dashboard server proxies /api and /ws to it.
start "FireGuard Backend" cmd /k "cd backend && venv\Scripts\activate && uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

if not exist "frontend\node_modules" (
    echo [SETUP] Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
)

echo [START] React dashboard on http://localhost:3000 ...
start "FireGuard Frontend" cmd /k "cd frontend && npm run dev -- --host"

echo.
echo  ============================================
echo   Open http://localhost:3000  (Pipeline page)
echo   Presenter remote: http://^<this-PC-IP^>:3000/presenter
echo  ============================================
echo.
pause
