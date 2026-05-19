import json
import logging
import random
import time

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, parse_listing_item

logger = logging.getLogger(__name__)

LIANJIA_CITIES = {
    "beijing": "https://bj.lianjia.com/zufang/",
    "shanghai": "https://sh.lianjia.com/zufang/",
    "guangzhou": "https://gz.lianjia.com/zufang/",
    "shenzhen": "https://sz.lianjia.com/zufang/",
    "chengdu": "https://cd.lianjia.com/zufang/",
    "hangzhou": "https://hz.lianjia.com/zufang/",
    "nanjing": "https://nj.lianjia.com/zufang/",
    "wuhan": "https://wh.lianjia.com/zufang/",
    "tianjin": "https://tj.lianjia.com/zufang/",
    "chongqing": "https://cq.lianjia.com/zufang/",
    "changsha": "https://cs.lianjia.com/zufang/",
    "changchun": "https://cc.lianjia.com/zufang/",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class LianjiaScraper(BaseScraper):

    def __init__(self, request_interval=8.0, max_pages=20):
        super().__init__(request_interval=request_interval)
        self.max_pages = max_pages
        self.session = requests.Session()
        self._init_session()

    def _init_session(self):
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

    def _fetch_page(self, url, max_retries=3):
        for attempt in range(max_retries):
            try:
                self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                resp.encoding = "utf-8"

                soup = BeautifulSoup(resp.text, "html.parser")
                title = soup.title.string if soup.title else ""

                if "CAPTCHA" in title or "captcha" in title.lower():
                    logger.warning("[链家] 触发验证码，等待后重试 (尝试 %d/%d)", attempt + 1, max_retries)
                    time.sleep(random.uniform(10, 20))
                    continue

                return soup
            except Exception as e:
                logger.error("[链家] 请求失败 (尝试 %d/%d): %s", attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 10))

        return None

    @property
    def source_name(self):
        return "lianjia"

    def fetch_listings(self, city="beijing"):
        base_url = LIANJIA_CITIES.get(city)
        if not base_url:
            logger.error("不支持的城市: %s", city)
            return []

        logger.info("[链家-%s] 开始爬取: %s", city, base_url)
        listings = []

        try:
            self._fetch_page(base_url.rstrip("/"))
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            logger.warning("[链家] 访问首页失败: %s", e)

        total_pages = self._get_total_pages(base_url)
        pages_to_crawl = min(total_pages, self.max_pages)
        logger.info("[链家-%s] 共 %d 页，本次爬取 %d 页", city, total_pages, pages_to_crawl)

        for page in range(1, pages_to_crawl + 1):
            url = base_url if page == 1 else "{}pg{}/".format(base_url, page)
            logger.info("[链家] 第 %d/%d 页: %s", page, pages_to_crawl, url)

            try:
                soup = self._fetch_page(url)
                if not soup:
                    logger.error("[链家] 第 %d 页获取失败，跳过", page)
                    continue

                page_listings = self._parse_list_page(soup, url, base_url)
                listings.extend(page_listings)
                logger.info("[链家] 第 %d 页解析到 %d 条", page, len(page_listings))

                if not page_listings:
                    logger.info("[链家] 第 %d 页无数据，停止爬取", page)
                    break
            except Exception as e:
                logger.error("[链家] 第 %d 页爬取失败: %s", page, e)

            if page < pages_to_crawl:
                delay = self.request_interval + random.uniform(2, 5)
                time.sleep(delay)

        logger.info("[链家-%s] 爬取完成，共获取 %d 条房源", city, len(listings))
        return listings

    def _get_total_pages(self, base_url):
        try:
            soup = self._fetch_page(base_url)
            if not soup:
                return 1
            page_box = soup.select_one("div.page-box")
            if page_box:
                page_data_str = page_box.get("page-data")
                if page_data_str:
                    page_data = json.loads(page_data_str)
                    total = page_data.get("totalPage", 1)
                    if total:
                        return int(total)
        except Exception as e:
            logger.warning("[链家] 获取总页数失败，使用默认值: %s", e)
        return 1

    def _parse_list_page(self, soup, page_url, base_url):
        listings = []
        items = soup.select("div.content__list--item")
        if not items:
            items = soup.select("div.content__list--item--main")
        if not items:
            items = soup.select("div.list-wrap li")
        if not items:
            items = soup.select("ul.house-lst li")

        if not items:
            logger.warning("[链家] 未找到房源列表项: %s", page_url)
            logger.debug("[链家] 页面标题: %s", soup.title.string if soup.title else "无")
            return []

        for item in items:
            listing = parse_listing_item(item, base_url, self.source_name)
            if listing:
                listings.append(listing)

        return listings
