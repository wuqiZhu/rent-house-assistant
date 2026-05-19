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


def generate_listing_id(source, url):
    return hashlib.md5("{}:{}".format(source, url).encode()).hexdigest()


def fetch_page(url, cookies=None, encoding="utf-8"):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    resp.raise_for_status()
    resp.encoding = encoding
    return BeautifulSoup(resp.text, "html.parser")


def parse_relative_time(text):
    text = text.strip()
    now = datetime.now()

    if m := re.search(r"(\d+)\s*分钟前", text):
        return now - timedelta(minutes=int(m.group(1)))
    if m := re.search(r"(\d+)\s*小时前", text):
        return now - timedelta(hours=int(m.group(1)))
    if m := re.search(r"(\d+)\s*天前", text):
        return now - timedelta(days=int(m.group(1)))

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    if m := re.search(r"^(\d{1,2})-(\d{1,2})$", text):
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                result = now.replace(month=month, day=day)
                if result > now:
                    result = result.replace(year=now.year - 1)
                return result
            except ValueError:
                pass

    return None


def parse_listing_item(item, base_url, source_name):
    title_el = (
        item.select_one("p.content__list--item--title a")
        or item.select_one("div.title a")
        or item.select_one("a.title")
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    if not href:
        return None

    if href.startswith("//"):
        detail_url = "https:" + href
    elif href.startswith("/"):
        detail_url = base_url.rstrip("/") + href
    else:
        detail_url = href

    des_el = (
        item.select_one("p.content__list--item--des")
        or item.select_one("div.des")
    )
    des_text = des_el.get_text(" ", strip=True) if des_el else ""
    rooms, area, floor = parse_des_text(des_text)

    price_el = (
        item.select_one("span.content__list--item-price em")
        or item.select_one("div.price em")
        or item.select_one("span.price em")
    )
    price = 0.0
    if price_el:
        try:
            price = float(price_el.get_text(strip=True))
        except ValueError:
            pass

    district = ""
    if des_el:
        location_links = des_el.select("a")
        if location_links:
            district = location_links[0].get_text(strip=True)

    brand_el = (
        item.select_one("p.content__list--item--brand.oneline")
        or item.select_one("div.brand")
    )
    publish_time = None
    if brand_el:
        time_text = brand_el.get_text(strip=True)
        publish_time = parse_relative_time(time_text)

    img_el = item.select_one("img")
    image_url = ""
    if img_el:
        image_url = img_el.get("data-src") or img_el.get("src") or ""
        if image_url.startswith("//"):
            image_url = "https:" + image_url

    from models import HousingListing

    return HousingListing(
        listing_id=generate_listing_id(source_name, detail_url),
        source=source_name,
        title=title,
        price=price,
        area=area,
        rooms=rooms,
        floor=floor,
        district=district,
        url=detail_url,
        images=[image_url] if image_url else [],
        publish_time=publish_time,
    )


def parse_des_text(text):
    parts = [p.strip() for p in re.split(r"[/|·\-]", text) if p.strip()]
    rooms = None
    area = None
    floor = None

    for part in parts:
        if re.search(r"\d+室|\d+房|整租|合租", part):
            rooms = part
        elif re.search(r"\d+\.?\d*\s*㎡", part):
            m = re.search(r"(\d+\.?\d*)\s*㎡", part)
            if m:
                area = float(m.group(1))
        elif re.search(r"楼层|低层|中层|高层|底层", part):
            floor = part

    return rooms, area, floor


class BaseScraper(ABC):
    def __init__(self, request_interval=5.0):
        self.request_interval = request_interval

    @property
    @abstractmethod
    def source_name(self):
        ...

    @abstractmethod
    def fetch_listings(self, city=None):
        ...

    def _throttle(self):
        jitter = random.uniform(0.5, 1.5)
        delay = self.request_interval * jitter
        logger.debug("等待 %.1f 秒...", delay)
        time.sleep(delay)
