@echo off
chcp 65001 >nul

echo ============================================
echo    TestAI Platform - Monorepo Launcher
echo ============================================
echo.

set PROJECT_ROOT=%~dp0
set PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%

echo 1. 启动前端 (Next.js)
echo 2. 启动后端 (FastAPI)
echo 3. 启动前后端 (同时)
echo 4. 运行后端测试
echo 5. 运行变异测试
echo 6. 前端构建
echo 7. 退出
echo.

set /p CHOICE=请选择操作 [1-7]: 

if "%CHOICE%"=="1" (
    echo 正在启动前端...
    cd apps\web
    npm run dev
    pause
    exit /b
)

if "%CHOICE%"=="2" (
    echo 正在启动后端...
    cd apps\server
    python main.py
    pause
    exit /b
)

if "%CHOICE%"=="3" (
    echo 正在启动前端...
    start cmd /k "cd apps\web && npm run dev"
    timeout /t 3 /nobreak >nul
    echo 正在启动后端...
    cd apps\server
    python main.py
    pause
    exit /b
)

if "%CHOICE%"=="4" (
    echo 正在运行后端测试...
    python -m pytest tests/ -v --tb=short
    pause
    exit /b
)

if "%CHOICE%"=="5" (
    echo 正在运行变异测试...
    python tests\utils\custom_mutation_test.py
    pause
    exit /b
)

if "%CHOICE%"=="6" (
    echo 正在构建前端...
    cd apps\web
    npm run build
    pause
    exit /b
)

if "%CHOICE%"=="7" (
    exit /b
)

echo 无效选择，请重新运行脚本
pause