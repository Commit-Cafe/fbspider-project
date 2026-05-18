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

    # 生成随机密钥
    SECRET_KEY=$(openssl rand -hex 32)

    cat > .env << EOF
# FBSpider 单用户版配置
# 自动生成于 $(date)

# 数据库配置（使用 SQLite）
MONGO_URI=sqlite:///fbspider.db
MONGO_DB=fbspider

# 安全密钥（自动生成）
SECRET_KEY=$SECRET_KEY

# 服务器配置
CORS_ORIGINS=http://localhost:7150,http://127.0.0.1:7150

# 可选配置（OpenClaw 回调）
ACCOUNT_DSL_CALLBACK_URL=
ACCOUNT_DSL_CALLBACK_SECRET=
ACCOUNT_DSL_CALLBACK_ENABLED=0
EOF

    echo "[✓] 配置文件已生成：.env"
    echo ""
fi

# 创建日志目录
mkdir -p logs

# 启动 WebSocket 服务
echo "[4/4] 启动服务..."
echo ""

python3 ws_relay.py > logs/ws_relay.log 2>&1 &
WS_PID=$!

# 等待 WebSocket 服务启动
sleep 2

# 检查 WebSocket 服务是否启动成功
if ! kill -0 $WS_PID 2>/dev/null; then
    echo "[错误] WebSocket 服务启动失败，请查看 logs/ws_relay.log"
    exit 1
fi

# 启动 HTTP 服务
echo "========================================"
echo "  服务已启动！"
echo "========================================"
echo ""
echo "  访问地址: http://localhost:7150"
echo "  WebSocket: ws://localhost:7671"
echo ""
echo "  默认账号: admin"
echo "  默认密码: 首次启动会在日志中显示"
echo ""
echo "  日志目录: logs/"
echo "  数据库文件: fbspider.db"
echo ""
echo "========================================"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

# 捕获退出信号
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $WS_PID 2>/dev/null || true
    echo "服务已停止"
    exit 0
}

trap cleanup INT TERM

# 启动主服务（前台运行）
python3 app.py

# 清理
cleanup
