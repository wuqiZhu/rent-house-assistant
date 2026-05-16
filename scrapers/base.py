import hashlib
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def generate_listing_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def fetch_page(url: str, cookies: dict = None, encoding: str = "utf-8") -> BeautifulSoup:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    resp.encoding = encoding
    return BeautifulSoup(resp.text, "html.parser")


def parse_relative_time(text: str):
    text = text.strip()
    now = datetime.now()
    if m := re.search(r"(\d+)\s*分钟前", text):
        return now - timedelta(minutes=int(m.group(1)))
    if m := re.search(r"(\d+)\s*小时前", text):
        return now - timedelta(hours=int(m.group(1)))
    if m := re.search(r"(\d+)\s*天前", text):
        return now - timedelta(days=int(m.group(1)))
    if m := re.search(r"(\d+)-(\d+)", text):
        try:
            return now.replace(month=int(m.group(1)), day=int(m.group(2)))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


class BaseScraper(ABC):
    def __init__(self, request_interval: float = 5.0):
        self.request_interval = request_interval

    @property
    @abstractmethod
    def source_name(self) -> str:
        ...

    @abstractmethod
    def fetch_listings(self, city: str = None):
        ...

    def _throttle(self):
        jitter = random.uniform(0.5, 1.5)
        delay = self.request_interval * jitter
        logger.debug(f"等待 {delay:.1f} 秒...")
        time.sleep(delay)
