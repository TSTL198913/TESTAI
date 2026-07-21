param(
    [string[]]$Browsers = @("chromium", "firefox", "webkit")
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  TestAI - Playwright 浏览器安装脚本" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  Python 版本: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  错误: 未找到 Python，请先安装 Python" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[2/3] 安装 Playwright Python 包..." -ForegroundColor Yellow
try {
    pip install playwright
    Write-Host "  Playwright Python 包安装成功" -ForegroundColor Green
} catch {
    Write-Host "  错误: Playwright Python 包安装失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[3/3] 安装浏览器..." -ForegroundColor Yellow
foreach ($browser in $Browsers) {
    Write-Host "  安装 $browser..." -ForegroundColor Yellow
    try {
        python -m playwright install $browser
        Write-Host "  $browser 安装成功" -ForegroundColor Green
    } catch {
        Write-Host "  警告: $browser 安装失败，将跳过" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Playwright 安装完成!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "验证安装:" -ForegroundColor Yellow
Write-Host "  python -m playwright --version" -ForegroundColor Gray
Write-Host "  python -c ""from playwright.sync_api import sync_playwright; print('OK')""" -ForegroundColor Gray