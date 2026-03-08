@echo off
setlocal EnableDelayedExpansion
title CortexDB Dashboard
color 0B

REM Resolve project root
set "ROOT=%~dp0"
cd /d "%ROOT%dashboard"

echo.
echo   ========================================
echo      CortexDB Dashboard  v5.0.0
echo      The Consciousness-Inspired Database
echo   ========================================
echo.

REM --- Check Node.js ---
where node >nul 2>&1
if errorlevel 1 (
    color 0C
    echo   [ERROR] Node.js is not installed!
    echo           Install from https://nodejs.org
    pause
    exit /b 1
)

REM --- Install dependencies if needed ---
if not exist "node_modules" (
    echo   [SETUP] Installing dependencies...
    call npm install
    echo.
)

REM --- Find available port ---
echo   [INFO] Finding available port...
set "PORT=3400"
if exist "scripts\find-port.js" (
    for /f %%p in ('node scripts\find-port.js 3400') do set "PORT=%%p"
)

if "!PORT!"=="3400" (
    echo   [OK] Using port 3400
) else (
    echo   [WARN] Port 3400 in use, using port !PORT!
)
echo.

echo   ========================================
echo   Starting on http://localhost:!PORT!
echo   Press Ctrl+C to stop
echo   ========================================
echo.

REM --- Open browser after delay ---
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://localhost:!PORT!"

REM --- Start the dashboard ---
call npx next dev --port !PORT!

echo.
echo   Dashboard stopped.
pause
