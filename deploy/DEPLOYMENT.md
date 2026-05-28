# 部署方式说明

## 两种部署方案

### 方案一：Systemd 守护进程（推荐）

使用 systemd 将程序作为后台服务运行，配合内部的 schedule 模块定时执行。

**优点：**
- 程序崩溃自动重启
- 定时执行逻辑在代码内部，更灵活
- 监控方便，状态一目了然

**安装步骤：**

```bash
# 1. 上传服务文件
cp /opt/rent_house_assistant/deploy/rent_house_assistant.service /etc/systemd/system/

# 2. 启用服务
systemctl daemon-reload
systemctl enable rent_house_assistant.service
systemctl start rent_house_assistant.service

# 3. 查看状态
systemctl status rent_house_assistant.service

# 4. 查看日志
journalctl -u rent_house_assistant.service -f
```

**配置说明：**

需要在 config.yaml 中开启定时模式：

```yaml
schedule:
  enabled: true
  morning_hour: 8
  evening_hour: 20
  check_interval_seconds: 60
```

---

### 方案二：Crontab 定时任务

使用传统的 cron 来定时调用程序。

**优点：**
- 简单直接，无需额外依赖
- 无需持续运行后台进程

**安装步骤：**

```bash
# 编辑 crontab
crontab -e

# 添加以下两行（每天 8:00 和 20:00 运行）
0 8 * * * cd /opt/rent_house_assistant && /opt/rent_house_assistant/venv/bin/python main.py >> /var/log/rent_assistant.log 2>&1
0 20 * * * cd /opt/rent_house_assistant && /opt/rent_house_assistant/venv/bin/python main.py >> /var/log/rent_assistant.log 2>&1

# 保存退出

# 查看定时任务
crontab -l
```

**配置说明：**

在 config.yaml 中关闭 schedule 模式：

```yaml
schedule:
  enabled: false
```

---

## 常用管理命令

### Systemd 服务

```bash
# 启动服务
systemctl start rent_house_assistant.service

# 停止服务
systemctl stop rent_house_assistant.service

# 重启服务
systemctl restart rent_house_assistant.service

# 查看状态
systemctl status rent_house_assistant.service

# 查看日志
journalctl -u rent_house_assistant.service -f  # 实时查看
journalctl -u rent_house_assistant.service --since "1 hour ago"  # 最近1小时
```

### Crontab 任务

```bash
# 查看任务
crontab -l

# 编辑任务
crontab -e

# 删除所有任务
crontab -r
```

---

## 监控与日志

### 查看程序日志

```bash
# 实时查看日志
tail -f /var/log/rent_assistant.log

# 查看最近100行
tail -100 /var/log/rent_assistant.log
```

### 警报通知

程序会自动发送以下钉钉通知：

1. **程序崩溃** - 发送异常堆栈信息
2. **每日摘要** - 晚上 20:00~20:10 之间运行时自动发送
3. **高分房源** - 发现符合条件的房源时发送

---

## 切换部署方式

### 从 Systemd 切换到 Crontab

```bash
# 1. 停止并禁用 systemd 服务
systemctl stop rent_house_assistant.service
systemctl disable rent_house_assistant.service

# 2. 修改 config.yaml
schedule:
  enabled: false

# 3. 配置 crontab
crontab -e
# 添加定时任务
```

### 从 Crontab 切换到 Systemd

```bash
# 1. 清除 cron 任务
crontab -e
# 删除相关的两行

# 2. 修改 config.yaml
schedule:
  enabled: true

# 3. 启用 systemd 服务
systemctl daemon-reload
systemctl enable rent_house_assistant.service
systemctl start rent_house_assistant.service
```
