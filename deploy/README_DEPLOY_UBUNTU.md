# 部署说明 — Ubuntu

以下为在 Ubuntu/阿里云服务器上部署 `rent_house_assistant` 的推荐步骤。

1. 登录服务器并克隆或拷贝代码至 `/home/youruser/rent_house`。

2. 进入项目并创建虚拟环境、安装依赖：

```bash
cd /home/youruser/rent_house/rent_house_assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

3. 配置 `config.yaml`：
- 把 `scrapers.douban.cookie` 写入有效 Cookie（首次运行必要）。
- 在 `notification` 中写入 `dingtalk_webhook` 和 `dingtalk_secret`，或设置为环境变量 `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`。

4. 测试运行：

```bash
source .venv/bin/activate
python main.py
```

5. 使用 systemd 长期运行（编辑服务文件中的 `User` / `WorkingDirectory` / `ExecStart` 路径）：

```bash
sudo cp deploy/rent_house_assistant.service /etc/systemd/system/rent_house_assistant.service
sudo systemctl daemon-reload
sudo systemctl enable rent_house_assistant.service
sudo systemctl start rent_house_assistant.service
sudo journalctl -u rent_house_assistant.service -f
```

6. 可选：使用 crontab 做周期触发（如果不想用 systemd）：

编辑 `crontab -e` 并添加：

```cron
# 每 30 分钟运行一次（请改为你的 python 虚拟环境路径）
*/30 * * * * cd /home/youruser/rent_house/rent_house_assistant && /home/youruser/rent_house/rent_house_assistant/.venv/bin/python main.py >> /var/log/rent_house_assistant.log 2>&1
```

7. 权限与备份建议：
- 将 `config.yaml` 权限改为 600：`chmod 600 config.yaml`。
- 定期备份 `rent_assistant.db`（例如每日复制到 `/home/youruser/backup/`）。

8. 常见问题排查：
- 若 Playwright 无法在无头模式下运行，请安装系统依赖：

```bash
sudo apt-get update
sudo apt-get install -y libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0
```

如果你希望，我可以帮助你把 `rent_house_assistant.service` 中的 `youruser` 和路径替换为你的真实用户名和部署路径。