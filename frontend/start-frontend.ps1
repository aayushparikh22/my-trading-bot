# Start Frontend Development Server
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Frontend Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Change to frontend directory
Set-Location $PSScriptRoot

# Start React development server
Write-Host "`nStarting React development server..." -ForegroundColor Yellow
npm start

Write-Host "`nFrontend server stopped." -ForegroundColor Red
