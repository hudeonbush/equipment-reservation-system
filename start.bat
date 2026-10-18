@echo off
REM 实验设备预约系统 - Windows 启动脚本
cd /d "%~dp0backend"
IF NOT EXIST "venv\Scripts\python.exe" (
    echo 未检测到虚拟环境，正在创建并安装依赖...
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt
)
echo 启动服务，浏览器访问 http://127.0.0.1:8000
venv\Scripts\python.exe main.py
pause
