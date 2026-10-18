#!/bin/bash
# 实验设备预约系统 - Linux/macOS 启动脚本
set -e
cd "$(dirname "$0")/backend"
if [ ! -x "venv/bin/python" ]; then
    echo "未检测到虚拟环境，正在创建并安装依赖..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
fi
echo "启动服务，浏览器访问 http://127.0.0.1:8000"
venv/bin/python main.py
