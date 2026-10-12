@echo off
REM Starts Reps on Windows: the Python API and the web app, each in its own window.
REM First run installs dependencies (needs Python 3.11+ and Node.js 20+ on PATH).

setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python was not found. Install Python 3.11+ from python.org and tick "Add to PATH". & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js was not found. Install Node.js 20+ from nodejs.org. & pause & exit /b 1)

if not exist "apps\api\.venv\Scripts\python.exe" (
  echo Setting up the Python environment...
  python -m venv apps\api\.venv || (pause & exit /b 1)
  apps\api\.venv\Scripts\python -m pip install --upgrade pip >nul
  apps\api\.venv\Scripts\pip install -e "apps\api[dev]" || (pause & exit /b 1)
)

if not exist "apps\web\node_modules" (
  echo Installing web dependencies...
  pushd apps\web
  call npm install || (popd & pause & exit /b 1)
  popd
)

if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"
)

start "Reps API" cmd /k "cd /d %~dp0apps\api && .venv\Scripts\python -m uvicorn reps_api.main:app --port 8000"
start "Reps web" cmd /k "cd /d %~dp0apps\web && npm run dev"

echo.
echo Reps is starting. Open http://localhost:3000 in Chrome or Edge.
timeout /t 8 >nul
start "" http://localhost:3000
endlocal
