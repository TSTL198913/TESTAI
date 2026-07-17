#!/bin/bash

set -e

echo "========================================="
echo "         TestAI 启动脚本"
echo "========================================="

show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help          显示帮助信息"
    echo "  -d, --dev           开发模式启动"
    echo "  -p, --prod          生产模式启动"
    echo "  -t, --test          运行测试套件"
    echo "  -b, --build         构建Docker镜像"
    echo "  -u, --up            启动Docker容器"
    echo "  -s, --stop          停止Docker容器"
    echo "  -c, --clean         清理Docker资源"
    echo "  -v, --validate      验证配置和依赖"
}

validate_config() {
    echo "[验证] 检查Python环境..."
    if ! command -v python3 &> /dev/null; then
        echo "[错误] 未找到python3，请安装Python 3.10+"
        exit 1
    fi

    echo "[验证] Python版本: $(python3 --version)"

    echo "[验证] 检查依赖..."
    if [ ! -f "pyproject.toml" ]; then
        echo "[错误] 未找到pyproject.toml"
        exit 1
    fi

    echo "[验证] 检查配置文件..."
    if [ ! -f ".env" ]; then
        echo "[警告] 未找到.env文件，将使用默认配置"
        echo "[提示] 复制.env.example为.env并配置环境变量"
    fi

    echo "[验证] 检查核心模块..."
    if [ ! -d "src" ]; then
        echo "[错误] 未找到src目录"
        exit 1
    fi

    echo "[验证] 检查测试目录..."
    if [ ! -d "tests" ]; then
        echo "[警告] 未找到tests目录"
    fi

    echo "[验证] 检查数据目录..."
    mkdir -p data reports

    echo "[验证] 完成"
}

run_tests() {
    echo "[测试] 运行测试套件..."
    python3 -m pytest tests/ -v --tb=short --timeout=60
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "[测试] 所有测试通过！"
    else
        echo "[测试] 测试失败，退出码: $exit_code"
    fi
    
    exit $exit_code
}

build_docker() {
    echo "[构建] 构建Docker镜像..."
    docker-compose build --no-cache
    echo "[构建] 完成"
}

start_docker() {
    echo "[启动] 启动Docker容器..."
    docker-compose up -d
    echo "[启动] 完成"
    echo "[提示] 运行 'docker-compose logs -f' 查看日志"
}

stop_docker() {
    echo "[停止] 停止Docker容器..."
    docker-compose down
    echo "[停止] 完成"
}

clean_docker() {
    echo "[清理] 清理Docker资源..."
    docker-compose down -v --remove-orphans
    echo "[清理] 完成"
}

start_dev() {
    echo "[启动] 开发模式..."
    
    echo "[启动] 安装依赖..."
    pip install -e .
    
    echo "[启动] 启动API服务..."
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
}

start_prod() {
    echo "[启动] 生产模式..."
    
    echo "[启动] 安装依赖..."
    pip install -e .
    
    echo "[启动] 启动API服务..."
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
}

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

case "$1" in
    -h|--help)
        show_help
        ;;
    -d|--dev)
        validate_config
        start_dev
        ;;
    -p|--prod)
        validate_config
        start_prod
        ;;
    -t|--test)
        validate_config
        run_tests
        ;;
    -b|--build)
        build_docker
        ;;
    -u|--up)
        start_docker
        ;;
    -s|--stop)
        stop_docker
        ;;
    -c|--clean)
        clean_docker
        ;;
    -v|--validate)
        validate_config
        ;;
    *)
        echo "[错误] 未知选项: $1"
        show_help
        exit 1
        ;;
esac