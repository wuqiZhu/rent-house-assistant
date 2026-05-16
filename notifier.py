import hashlib
import hmac
import base64
import logging
import time
import urllib.parse

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
        listings_text += (
            "**{}. [{}]({})**\n"
            "   - 💰 租金：**{}元/月**\n"
            "   - 📐 面积：{}㎡\n"
            "   - 📍 区域：{}\n"
            "   - ⭐ 评分：**{}分**\n"
            "   - 🔗 来源：{}\n\n"
        ).format(
            i,
            item.get("title", "")[:30],
            item.get("url", ""),
            item.get("price", 0),
            item.get("area", "未知"),
            item.get("district", "未知"),
            item.get("score", 0),
            item.get("source", "未知"),
        )

    markdown_text = TEMPLATE.format(listings_text=listings_text)

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "🏠 发现{}套高分房源".format(len(listings)),
            "text": markdown_text,
        },
    }

    try:
        result = _post(webhook_url, payload, secret)
        if result.get("errcode") == 0:
            logger.info("钉钉通知发送成功，共 %d 条房源", len(listings))
            return True
        else:
            logger.error("钉钉通知发送失败: %s", result)
            return False
    except Exception as e:
        logger.error("钉钉通知发送异常: %s", e)
        return False


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
