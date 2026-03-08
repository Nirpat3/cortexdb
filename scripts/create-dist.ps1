# CortexDB Distribution Package Creator
# Creates a zip file ready for download and installation
# Usage: powershell -ExecutionPolicy Bypass -File scripts/create-dist.ps1

param(
    [string]$OutputPath = "$env:USERPROFILE\Desktop\CortexDB-v5.0.0.zip",
    [string]$Version = "5.0.0"
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host ""
Write-Host "  CortexDB Distribution Packager v$Version" -ForegroundColor Cyan
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""

$excludeDirs = @('.git', 'node_modules', '.next', '__pycache__', 'venv', '.venv',
    'data', 'logs', 'certs', '.pytest_cache', 'htmlcov', '.idea', '.vscode',
    'output', 'dist', 'build', '.mypy_cache', '.ruff_cache', '.claude', '.eggs',
    'env', '.coverage')

$excludeFiles = @('.env', '.env.prod', '.env.staging', '.env.local',
    '.env.previous', '.coverage', 'docker-compose.override.yml',
    'Thumbs.db', '.DS_Store')

$excludeExts = @('.pyc', '.pyo', '.log', '.swp', '.swo', '.egg-info')

$folderName = "CortexDB-v$Version"
$tempDir = Join-Path $env:TEMP $folderName

# Cleanup previous
if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force }
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }

Write-Host "  [1/3] Scanning files..." -ForegroundColor Yellow

$files = Get-ChildItem -Path $source -Recurse -File -Force | Where-Object {
    $path = $_.FullName
    $relPath = $path.Substring($source.Length + 1)
    $parts = $relPath.Split('\')

    # Check if any path component is in exclude dirs
    $skip = $false
    foreach ($part in $parts[0..($parts.Length-2)]) {
        if ($excludeDirs -contains $part) { $skip = $true; break }
    }
    if ($skip) { return $false }

    # Check filename
    if ($excludeFiles -contains $_.Name) { return $false }

    # Check extension
    if ($excludeExts -contains $_.Extension) { return $false }

    # Check .env.backup.* pattern
    if ($_.Name -match '^\.env\.backup\.') { return $false }

    # Exclude egg-info directories
    if ($relPath -match '\.egg-info') { return $false }

    return $true
}

$fileCount = ($files | Measure-Object).Count
Write-Host "  [OK] Found $fileCount files to package" -ForegroundColor Green

Write-Host "  [2/3] Copying to staging directory..." -ForegroundColor Yellow

$count = 0
foreach ($file in $files) {
    $relPath = $file.FullName.Substring($source.Length + 1)
    $destPath = Join-Path $tempDir $relPath
    $destDir = Split-Path $destPath -Parent
    if (!(Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item $file.FullName $destPath
    $count++
    if ($count % 50 -eq 0) {
        Write-Host "    Copied $count / $fileCount files..." -ForegroundColor DarkGray
    }
}
Write-Host "  [OK] Copied $count files" -ForegroundColor Green

Write-Host "  [3/3] Creating zip archive..." -ForegroundColor Yellow

Compress-Archive -Path $tempDir -DestinationPath $OutputPath -CompressionLevel Optimal

$zipSize = (Get-Item $OutputPath).Length
$sizeMB = [math]::Round($zipSize / 1MB, 2)

# Cleanup
Remove-Item $tempDir -Recurse -Force

Write-Host "  [OK] Archive created" -ForegroundColor Green
Write-Host ""
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host "  Output: $OutputPath" -ForegroundColor White
Write-Host "  Size:   $sizeMB MB ($count files)" -ForegroundColor White
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To install on a new machine:" -ForegroundColor Yellow
Write-Host "    1. Extract the zip" -ForegroundColor White
Write-Host "    2. Windows: Run setup.bat" -ForegroundColor White
Write-Host "    3. Linux/Mac: Run ./install.sh" -ForegroundColor White
Write-Host ""
