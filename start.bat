@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =========================================
echo          TestAI 启动脚本
echo =========================================

if "%1"=="" goto :help
if "%1"=="-h" goto :help
if "%1"=="--help" goto :help
if "%1"=="-d" goto :dev
if "%1"=="--dev" goto :dev
if "%1"=="-p" goto :prod
if "%1"=="--prod" goto :prod
if "%1"=="-t" goto :test
if "%1"=="--test" goto :test
if "%1"=="-b" goto :build
if "%1"=="--build" goto :build
if "%1"=="-u" goto :up
if "%1"=="--up" goto :up
if "%1"=="-s" goto :stop
if "%1"=="--stop" goto :stop
if "%1"=="-c" goto :clean
if "%1"=="--clean" goto :clean
if "%1"=="-v" goto :validate
if "%1"=="--validate" goto :validate

echo [错误] 未知选项: %1
goto :help

:help
echo 用法: %0 [选项]
echo.
echo 选项:
echo   -h, --help          显示帮助信息
echo   -d, --dev           开发模式启动
echo   -p, --prod          生产模式启动
echo   -t, --test          运行测试套件
echo   -b, --build         构建Docker镜像
echo   -u, --up            启动Docker容器
echo   -s, --stop          停止Docker容器
echo   -c, --clean         清理Docker资源
echo   -v, --validate      验证配置和依赖
goto :end

:validate
echo [验证] 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python，请安装Python 3.10+
    goto :end
)

for /f "tokens=2" %%a in ('python --version 2^>^&1') do set PYTHON_VERSION=%%a
echo [验证] Python版本: !PYTHON_VERSION!

echo [验证] 检查依赖...
if not exist "pyproject.toml" (
    echo [错误] 未找到pyproject.toml
    goto :end
)

echo [验证] 检查配置文件...
if not exist ".env" (
    echo [警告] 未找到.env文件，将使用默认配置
    echo [提示] 复制.env.example为.env并配置环境变量
)

echo [验证] 检查核心模块...
if not exist "src" (
    echo [错误] 未找到src目录
    goto :end
)

echo [验证] 检查测试目录...
if not exist "tests" (
    echo [警告] 未找到tests目录
)

echo [验证] 检查数据目录...
if not exist "data" mkdir data
if not exist "reports" mkdir reports

echo [验证] 完成
goto :end

:test
call :validate
echo [测试] 运行测试套件...
python -m pytest tests/ -v --tb=short --timeout=60
if %errorlevel% equ 0 (
    echo [测试] 所有测试通过！
) else (
    echo [测试] 测试失败，退出码: %errorlevel%
)
goto :end

:build
echo [构建] 构建Docker镜像...
docker-compose build --no-cache
echo [构建] 完成
goto :end

:up
echo [启动] 启动Docker容器...
docker-compose up -d
echo [启动] 完成
echo [提示] 运行 'docker-compose logs -f' 查看日志
goto :end

:stop
echo [停止] 停止Docker容器...
docker-compose down
echo [停止] 完成
goto :end

:clean
echo [清理] 清理Docker资源...
docker-compose down -v --remove-orphans
echo [清理] 完成
goto :end

:dev
call :validate
echo [启动] 开发模式...
echo [启动] 安装依赖...
pip install -e .
echo [启动] 启动API服务...
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
goto :end

:prod
call :validate
echo [启动] 生产模式...
echo [启动] 安装依赖...
pip install -e .
echo [启动] 启动API服务...
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
goto :end

:end
endlocal