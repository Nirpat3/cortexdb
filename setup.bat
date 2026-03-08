@echo off
setlocal EnableDelayedExpansion
title CortexDB - One Click Setup
color 0B

echo.
echo   ================================================
echo      CortexDB - One Click Setup  v5.0.0
echo      The Consciousness-Inspired Unified Database
echo   ================================================
echo.

REM Resolve project root (directory containing this script)
set "ROOT=%~dp0"
cd /d "%ROOT%"

REM --- Check prerequisites ---
REM Check Node.js
where node >nul 2>&1
if errorlevel 1 (
    color 0C
    echo   [ERROR] Node.js is not installed!
    echo           Install from https://nodejs.org ^(v18+^)
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node -v') do echo   [OK] Node.js %%v detected
for /f "tokens=*" %%v in ('npm -v') do echo   [OK] npm v%%v detected
echo.

REM Check Docker (optional for --no-docker mode)
where docker >nul 2>&1
if errorlevel 1 (
    echo   [WARN] Docker not found. Install from https://docs.docker.com/get-docker/
    echo          Docker is required for the CortexDB backend services.
    echo.
) else (
    for /f "tokens=*" %%v in ('docker --version') do echo   [OK] %%v
    echo.
)

REM ============================================
REM  Step 1: Create .env if missing
REM ============================================
echo   [1/5] Configuring environment...
if not exist "%ROOT%.env" (
    if exist "%ROOT%.env.example" (
        copy "%ROOT%.env.example" "%ROOT%.env" >nul
        echo   [OK] Created .env from .env.example
    ) else (
        echo   [ERROR] .env.example not found!
        pause
        exit /b 1
    )
) else (
    echo   [OK] .env already exists
)
echo.

REM ============================================
REM  Step 2: Generate secrets if placeholders
REM ============================================
echo   [2/5] Checking secrets...
REM Use PowerShell to generate random hex and replace placeholders
powershell -NoProfile -Command ^
  "$env = Get-Content '%ROOT%.env' -Raw;" ^
  "function GenHex { -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) }) };" ^
  "$changed = $false;" ^
  "if ($env -match 'CORTEX_SECRET_KEY=\s*$' -or $env -match 'CORTEX_SECRET_KEY=your-') { $env = $env -replace 'CORTEX_SECRET_KEY=.*', ('CORTEX_SECRET_KEY=' + (GenHex)); $changed=$true; Write-Host '  [OK] Generated CORTEX_SECRET_KEY' };" ^
  "if ($env -match 'CORTEX_ADMIN_TOKEN=\s*$' -or $env -match 'CORTEX_ADMIN_TOKEN=your-') { $env = $env -replace 'CORTEX_ADMIN_TOKEN=.*', ('CORTEX_ADMIN_TOKEN=' + (GenHex)); $changed=$true; Write-Host '  [OK] Generated CORTEX_ADMIN_TOKEN' };" ^
  "if ($env -match 'CORTEXDB_MASTER_SECRET=\s*$' -or $env -match 'CORTEXDB_MASTER_SECRET=your-') { $env = $env -replace 'CORTEXDB_MASTER_SECRET=.*', ('CORTEXDB_MASTER_SECRET=' + (GenHex)); $changed=$true; Write-Host '  [OK] Generated CORTEXDB_MASTER_SECRET' };" ^
  "if ($changed) { Set-Content '%ROOT%.env' $env -NoNewline } else { Write-Host '  [OK] Secrets already configured' }"
echo.

REM ============================================
REM  Step 3: Start Docker services
REM ============================================
echo   [3/5] Starting Docker services...
where docker >nul 2>&1
if errorlevel 1 (
    echo   [SKIP] Docker not found, skipping backend services.
    echo          Start manually: docker compose up -d
) else (
    cd /d "%ROOT%"
    docker compose up -d --build
    if errorlevel 1 (
        echo   [WARN] Docker compose failed. Check Docker Desktop is running.
    ) else (
        echo   [OK] Docker services started
    )
)
echo.

REM ============================================
REM  Step 4: Install and build dashboard
REM ============================================
echo   [4/5] Setting up dashboard...
cd /d "%ROOT%dashboard"

if not exist ".env.local" (
    echo NEXT_PUBLIC_CORTEX_API_URL=http://localhost:5400> .env.local
    echo NEXT_PUBLIC_CORTEX_WS_URL=ws://localhost:5400>> .env.local
    echo   [OK] Created dashboard/.env.local
)

if not exist "node_modules" (
    echo   Installing dependencies...
    call npm install
    echo   [OK] Dependencies installed
) else (
    echo   [OK] Dependencies already installed
)

echo   Building dashboard...
call npm run build
echo   [OK] Dashboard built
echo.

REM ============================================
REM  Step 5: Create desktop shortcut
REM ============================================
echo   [5/5] Creating desktop shortcut...
cd /d "%ROOT%"

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$env:USERPROFILE\Desktop\CortexDB Dashboard.lnk\");" ^
  "$s.TargetPath = '%ROOT%CortexDB.bat';" ^
  "$s.WorkingDirectory = '%ROOT%';" ^
  "$s.Description = 'CortexDB Dashboard';" ^
  "$s.IconLocation = 'C:\Windows\System32\shell32.dll,13';" ^
  "$s.Save()"

if exist "%USERPROFILE%\Desktop\CortexDB Dashboard.lnk" (
    echo   [OK] Desktop shortcut created
) else (
    echo   [WARN] Shortcut not created. Run CortexDB.bat manually.
)
echo.

REM ============================================
REM  Summary
REM ============================================
echo   ================================================
echo   CortexDB is ready!
echo.
echo   CortexDB API:     http://localhost:5400
echo   Health endpoint:   http://localhost:5401/health/ready
echo   Dashboard:         http://localhost:3400
echo.
echo   PostgreSQL:        localhost:5432
echo   Redis (cache):     localhost:6379
echo   Redis (streams):   localhost:6380
echo   Qdrant (vectors):  localhost:6333
echo.
echo   Quick test:
echo     curl http://localhost:5400/v1/query -H "Content-Type: application/json" -d "{\"cortexql\": \"SELECT 1 AS ping\"}"
echo   ================================================
echo.

set /p "LAUNCH=  Launch dashboard now? (Y/n): "
if /i "!LAUNCH!"=="n" goto :done

echo.
echo   Launching...
start "" "%ROOT%CortexDB.bat"

:done
echo   Done.
timeout /t 3 >nul
