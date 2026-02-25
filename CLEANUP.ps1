# Trading Bot Cleanup Script
# Removes unnecessary files and directories

Write-Host "Trading Bot Cleanup Script" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
Set-Location $PSScriptRoot

# Ask for confirmation
$confirm = Read-Host "This will remove unnecessary files. Continue? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "Cleanup cancelled." -ForegroundColor Yellow
    exit
}

Write-Host ""
Write-Host "Removing test files..." -ForegroundColor Yellow
Remove-Item -Force -ErrorAction SilentlyContinue @(
    "cleanup_trade.py",
    "fetch_triggers.py",
    "get_triggers.py",
    "list_tables.py",
    "live_dry_run.py",
    "show_walkthrough.py",
    "test_algorithm_upgrades.py",
    "test_kite_direct.py",
    "test_trading_apis.py",
    "verify_sl_orders.py"
)
Write-Host "[+] Test files removed" -ForegroundColor Green

Write-Host ""
Write-Host "Removing old stop-loss scripts..." -ForegroundColor Yellow
Remove-Item -Force -ErrorAction SilentlyContinue @(
    "place_sl_orders.py",
    "place_sl_orders_circuit_safe.py",
    "place_sl_orders_fixed.py",
    "place_sl_orders_v2.py",
    "place_sl_orders_v3.py"
)
Write-Host "[+] Old stop-loss scripts removed" -ForegroundColor Green

Write-Host ""
Write-Host "Removing documentation files..." -ForegroundColor Yellow
Remove-Item -Force -ErrorAction SilentlyContinue @(
    "DB_SYNC_IMPROVEMENTS.md",
    "EXIT_STRATEGY_CODE_REVIEW.md",
    "EXIT_STRATEGY_EXAMPLES.md",
    "STOPLOSS_RESOLUTION.md"
)
Write-Host "[+] Documentation files removed" -ForegroundColor Green

Write-Host ""
Write-Host "Removing __pycache__ directories..." -ForegroundColor Yellow
Get-ChildItem -Path . -Directory -Name "__pycache__" -Recurse -Force | ForEach-Object {
    Remove-Item -Path $_ -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "[+] __pycache__ removed" -ForegroundColor Green

Write-Host ""
Write-Host "Removing requirements-local.txt..." -ForegroundColor Yellow
Remove-Item -Force -ErrorAction SilentlyContinue "backend\requirements-local.txt"
Write-Host "[+] requirements-local.txt removed" -ForegroundColor Green

Write-Host ""
$removeScripts = Read-Host "Remove batch/PowerShell scripts (yes/no)?"
if ($removeScripts -eq "yes") {
    Remove-Item -Force -ErrorAction SilentlyContinue @(
        "START.bat",
        "STOP.bat",
        "test.bat",
        "rem.bat",
        "START.ps1",
        "STOP.ps1",
        "RESTART.ps1"
    )
    Write-Host "[+] Batch/PowerShell scripts removed" -ForegroundColor Green
}

Write-Host ""
$removeGit = Read-Host "Remove .git folder (version control)? (yes/no)"
if ($removeGit -eq "yes") {
    Remove-Item -Path ".git" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Force -ErrorAction SilentlyContinue ".gitignore"
    Write-Host "[+] Git folder removed" -ForegroundColor Green
}

Write-Host ""
$removeVscode = Read-Host "Remove .vscode folder (VS Code settings)? (yes/no)"
if ($removeVscode -eq "yes") {
    Remove-Item -Path ".vscode" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[+] .vscode folder removed" -ForegroundColor Green
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "[+] Cleanup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Remaining essential files:" -ForegroundColor Cyan
Write-Host "  [+] app_files/ (bot core)"
Write-Host "  [+] backend/ (API)"
Write-Host "  [+] frontend/ (UI)"
Write-Host "  [+] .env (credentials)"
Write-Host "  [+] tradingbot.db (database)"
Write-Host "  [+] trigger_cache.json (cache)"
Write-Host ""
