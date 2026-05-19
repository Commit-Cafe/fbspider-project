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
    copy .env.example .env >nul
    echo [✓] 已从 .env.example 生成 .env 配置文件
    echo     请编辑 .env 填入正确的 MONGO_URI 和 SECRET_KEY
    echo.
    notepad .env
    echo.
    echo 配置完成后，请再次运行此脚本
    pause
    exit /b 0
)

REM 创建日志目录
if not exist "logs" mkdir logs

echo [4/4] 启动服务...
echo.
echo ========================================
echo   服务已启动！
echo ========================================
echo.
echo   访问地址: http://47.131.62.227:7151
echo   WebSocket: ws://47.131.62.227:7672
echo.
echo   默认账号: admin / admin123456
echo.
echo   日志目录: logs\
echo.
echo ========================================
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

python app.py

echo.
echo 服务已停止
pause
