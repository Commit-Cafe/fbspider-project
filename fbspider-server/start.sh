#!/bin/bash

# FBSpider 便携版启动脚本（macOS/Linux）

set -e

echo "========================================"
echo "  FBSpider 便携版启动中..."
echo "========================================"
echo ""

# 设置工作目录
cd "$(dirname "$0")"

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python 环境"
    echo "请安装 Python 3.10+ 或从 https://www.python.org/downloads/ 下载"
    echo ""
    exit 1
fi

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version | grep -oE '[0-9]+\.[0-9]+')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo "[警告] Python 版本 $PYTHON_VERSION 可能过低，建议使用 Python 3.10+"
    echo ""
fi

# 首次运行：安装依赖
if [ ! -d "venv" ]; then
    echo "[1/4] 首次运行，正在创建虚拟环境..."
    python3 -m venv venv

    echo "[2/4] 正在安装依赖（使用清华镜像加速）..."
    source venv/bin/activate
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir
    echo ""
    echo "[✓] 依赖安装完成"
    echo ""
else
    source venv/bin/activate
fi

# 检查配置文件
if [ ! -f ".env" ]; then
    echo "[3/4] 首次运行，正在生成配置文件..."
    cp .env.example .env
    echo "[✓] 已从 .env.example 生成 .env 配置文件"
    echo "    请编辑 .env 填入正确的 MONGO_URI 和 SECRET_KEY"
    echo ""

    if command -v nano &> /dev/null; then
        nano .env
    elif command -v vim &> /dev/null; then
        vim .env
    else
        open -e .env
    fi

    echo ""
    echo "配置完成后，请再次运行此脚本"
    exit 0
fi

# 创建日志目录
mkdir -p logs

echo "[4/4] 启动服务..."
echo ""

echo "========================================"
echo "  服务已启动！"
echo "========================================"
echo ""
echo "  访问地址: http://54.179.56.204:7151"
echo "  WebSocket: ws://54.179.56.204:7672"
echo ""
echo "  默认账号: admin / admin123456"
echo ""
echo "  日志目录: logs/"
echo ""
echo "========================================"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

python3 app.py

echo ""
echo "服务已停止"
