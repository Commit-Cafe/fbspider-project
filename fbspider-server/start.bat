@echo off
chcp 65001 >nul
title FBSpider Server

echo ========================================
echo   FBSpider 便携版启动中...
echo ========================================
echo.

REM 设置工作目录
cd /d "%~dp0"

REM 检查 Python 环境
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境
    echo 请安装 Python 3.10+ 或从 https://www.python.org/downloads/ 下载
    echo.
    pause
    exit /b 1
)

REM 检查 Python 版本
python --version | findstr /R "3\.[0-9][0-9]" >nul
if %errorlevel% neq 0 (
    echo [警告] Python 版本可能过低，建议使用 Python 3.10+
    echo.
)

REM 首次运行：安装依赖
if not exist "venv" (
    echo [1/4] 首次运行，正在创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )

    echo [2/4] 正在安装依赖（使用清华镜像加速）...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo.
    echo [✓] 依赖安装完成
    echo.
) else (
    call venv\Scripts\activate.bat
)

REM 检查配置文件
if not exist ".env" (
    echo [3/4] 首次运行，正在生成配置文件...
    (
        echo # FBSpider 单用户版配置
        echo # 自动生成于 %date% %time%
        echo.
        echo # 数据库配置（使用 SQLite）
        echo MONGO_URI=sqlite:///fbspider.db
        echo MONGO_DB=fbspider
        echo.
        echo # 安全密钥（自动生成）
        echo SECRET_KEY=%RANDOM%%RANDOM%%RANDOM%%RANDOM%
        echo.
        echo # 服务器配置
        echo CORS_ORIGINS=http://localhost:7150,http://127.0.0.1:7150
        echo.
        echo # 可选配置（OpenClaw 回调）
        echo ACCOUNT_DSL_CALLBACK_URL=
        echo ACCOUNT_DSL_CALLBACK_SECRET=
        echo ACCOUNT_DSL_CALLBACK_ENABLED=0
    ) > .env
    echo [✓] 配置文件已生成：.env
    echo.
)

REM 创建日志目录
if not exist "logs" mkdir logs

REM 启动 WebSocket 服务
echo [4/4] 启动服务...
echo.
start /B python ws_relay.py > logs\ws_relay.log 2>&1

REM 等待 WebSocket 服务启动
timeout /t 2 /nobreak >nul

REM 启动 HTTP 服务
echo ========================================
echo   服务已启动！
echo ========================================
echo.
echo   访问地址: http://localhost:7150
echo   WebSocket: ws://localhost:7671
echo.
echo   默认账号: admin
echo   默认密码: 首次启动会在日志中显示
echo.
echo   日志目录: logs\
echo   数据库文件: fbspider.db
echo.
echo ========================================
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

REM 启动主服务（前台运行）
python app.py

REM 清理：停止 WebSocket 服务
echo.
echo 正在停止服务...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq ws_relay*" >nul 2>&1

echo 服务已停止
pause
