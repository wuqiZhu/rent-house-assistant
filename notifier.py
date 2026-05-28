import hashlib
import hmac
import base64
import logging
import time
import urllib.parse
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

TEMPLATE = """\
### 🏠 发现高分房源

{listings_text}

> 评分仅供参考，请点击链接查看详情
"""


def _sign_url(webhook_url, secret):
    timestamp = str(round(time.time() * 1000))
    string_to_sign = "{}\n{}".format(timestamp, secret)
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return "{}&timestamp={}&sign={}".format(webhook_url, timestamp, sign)


def _post(webhook_url, payload, secret=""):
    url = _sign_url(webhook_url, secret) if secret else webhook_url
    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    return resp.json()


def send_dingtalk(webhook_url, listings, secret=""):
    if not listings:
        logger.info("无高分房源，跳过通知")
        return True

    listings_text = ""
    for i, item in enumerate(listings[:10], 1):
        listings_text += f"{i}. [{item['title']}]({item['url']})\n"
        listings_text += f"   - 💰 价格: **{item['price']}**元 | 📐 面积: {item['area'] or '?'}㎡\n"
        listings_text += f"   - 📍 区域: {item['district'] or '?'} | 🚇 地铁: {item['subway_station'] or '?'}\n"
        listings_text += f"   - ⭐️ 评分: **{item['score']:.1f}**分 | 🏷️ 来源: {item['source']}\n\n"

    text = TEMPLATE.format(listings_text=listings_text)
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": "租房小助手通知", "text": text},
    }
    
    try:
        ret = _post(webhook_url, payload, secret)
        if ret.get("errcode") == 0:
            logger.info("钉钉通知发送成功，共 %d 条房源", len(listings))
            return True
        else:
            logger.error("钉钉通知发送失败: %s", ret)
            return False
    except Exception as e:
        logger.error("发送钉钉通知发生异常: %s", e)
        return False


def get_global_notification_config():
    """获取根目录下的钉钉配置(用于无上下文情况下的错误推送)"""
    import yaml
    import os
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                info = data.get("notification", {})
                webhook = os.getenv("DINGTALK_WEBHOOK") or info.get("dingtalk_webhook", "")
                secret = os.getenv("DINGTALK_SECRET") or info.get("dingtalk_secret", "")
                return webhook, secret
        except Exception:
            pass
    return os.getenv("DINGTALK_WEBHOOK"), os.getenv("DINGTALK_SECRET")


def send_dingtalk_raw_markdown(markdown_text):
    """直接发送一段原生 markdown 文本(用于发送二维码等警报)"""
    webhook, secret = get_global_notification_config()
    if not webhook:
        logger.warning("未配置 Dingtalk Webhook，跳过报警通知")
        return False

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": "租房小助手警报", "text": markdown_text},
    }
    try:
        ret = _post(webhook, payload, secret)
        if ret.get("errcode") == 0:
            logger.info("钉钉警报发送成功")
            return True
        logger.error("钉钉警报发送失败: %s", ret)
        return False
    except Exception as e:
        logger.error("钉钉警报异常: %s", e)
        return False

def upload_image_to_smms(file_path):
    """上传本地图片到 SM.MS 图床，返回可访问网址"""
    url = "https://sm.ms/api/v2/upload"
    headers = {
        # 最好去 sm.ms 申请一个免费token放在这，为了演示我们用不需要账户的轻量图床或公共API
        # 由于smms现在的v2 api强制要求Authorization，所以我们切到一个免验的公共图床API：
    }
    # 替换为 telegra.ph 等公共图床上传方式或第三方无鉴权API
    # 此处我们用一个开源免鉴权图床 (如 imgur 的匿名上传，或直接使用基于 ooxx 的公共服务)
    try:
        with open(file_path, "rb") as f:
            files = {"file": f}
            # 使用免费无限速公共图床 picui
            # 这里找个免签接口示例
            resp = requests.post("https://picui.cn/api/v1/upload", files=files, data={"permission": "1"}, timeout=15)
            data = resp.json()
            if data.get("status"):
                return data["data"]["links"]["url"]
            else:
                logger.error("图床上传失败:%s", data)
    except Exception as e:
        logger.error("图床上传异常:%s", e)
    return ""

def send_test(webhook_url, secret=""):
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "✅ 租房助手测试通知",
            "text": "### ✅ 租房助手通知测试\n\n钉钉通知配置成功！\n\n> 后续将自动推送高分房源",
        },
    }
    try:
        result = _post(webhook_url, payload, secret)
        if result.get("errcode") == 0:
            logger.info("测试通知发送成功")
            return True
        else:
            logger.error("测试通知发送失败: %s", result)
            return False
    except Exception as e:
        logger.error("测试通知发送异常: %s", e)
        return False
