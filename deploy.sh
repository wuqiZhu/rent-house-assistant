#!/bin/bash
# 租房助手 - 阿里云一键部署脚本
# 使用方法: chmod +x deploy.sh && ./deploy.sh

set -e

APP_NAME="rent_house_assistant"
APP_DIR="/opt/$APP_NAME"
REPO_URL="https://github.com/wuqiZhu/rent-house-assistant.git"

echo "=========================================="
echo "  租房助手 - 阿里云部署脚本"
echo "=========================================="

# 1. 安装系统依赖
echo "[1/7] 安装系统依赖..."
if command -v apt-get &> /dev/null; then
    apt-get update
    apt-get install -y python3 python3-pip python3-venv git \
        libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 \
        libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2 libatspi2.0-0
elif command -v yum &> /dev/null; then
    yum update -y
    yum install -y python3 python3-pip git \
        nss atk at-spi2-atk cups-libs libdrm libXcomposite libXdamage \
        libXrandr mesa-libgbm pango alsa-lib
else
    echo "不支持的包管理器，请手动安装 Python3 和 Git"
    exit 1
fi

# 2. 克隆代码
echo "[2/7] 克隆代码..."
if [ -d "$APP_DIR" ]; then
    echo "目录已存在，更新代码..."
    cd $APP_DIR
    git pull
else
    git clone $REPO_URL $APP_DIR
    cd $APP_DIR
fi

# 3. 创建虚拟环境
echo "[3/7] 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 4. 安装依赖
echo "[4/7] 安装 Python 依赖..."
pip install -r requirements.txt

# 5. 安装 Playwright 浏览器
echo "[5/7] 安装 Playwright 浏览器..."
playwright install chromium --with-deps

# 6. 创建配置文件
echo "[6/7] 创建配置文件..."
if [ ! -f "config.yaml" ]; then
    cp config.yaml.example config.yaml
    echo "请编辑 $APP_DIR/config.yaml 填入你的配置"
fi

# 7. 创建定时任务
echo "[7/7] 设置定时任务..."
CRON_CMD="cd $APP_DIR && $APP_DIR/venv/bin/python main.py >> /var/log/rent_assistant.log 2>&1"

# 添加定时任务（每天 8:00 和 20:00 运行）
(crontab -l 2>/dev/null | grep -v "$APP_NAME"; echo "0 8 * * * $CRON_CMD"; echo "0 20 * * * $CRON_CMD") | crontab -

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "下一步操作："
echo "1. 编辑配置文件: nano $APP_DIR/config.yaml"
echo "2. 测试运行: cd $APP_DIR && source venv/bin/activate && python main.py"
echo "3. 查看日志: tail -f /var/log/rent_assistant.log"
echo "4. 查看定时任务: crontab -l"
echo ""
