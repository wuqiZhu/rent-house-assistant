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
echo "[1/6] 安装系统依赖..."
if command -v apt-get &> /dev/null; then
    apt-get update
    apt-get install -y python3 python3-pip python3-venv git
elif command -v yum &> /dev/null; then
    yum update -y
    yum install -y python3 python3-pip git
else
    echo "不支持的包管理器，请手动安装 Python3 和 Git"
    exit 1
fi

# 2. 克隆代码
echo "[2/6] 克隆代码..."
if [ -d "$APP_DIR" ]; then
    echo "目录已存在，更新代码..."
    cd $APP_DIR
    git pull
else
    git clone $REPO_URL $APP_DIR
    cd $APP_DIR
fi

# 3. 创建虚拟环境
echo "[3/6] 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 4. 安装依赖
echo "[4/6] 安装 Python 依赖..."
pip install -r requirements.txt

# 5. 创建配置文件
echo "[5/6] 创建配置文件..."
if [ ! -f "config.yaml" ]; then
    cp config.yaml.example config.yaml
    echo "请编辑 $APP_DIR/config.yaml 填入你的配置"
fi

# 6. 创建定时任务
echo "[6/6] 设置定时任务..."
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
