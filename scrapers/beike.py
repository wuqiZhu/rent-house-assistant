import logging
import random
import time

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, parse_listing_item

logger = logging.getLogger(__name__)

BEIKE_CITIES = {
    "beijing": "https://bj.zu.ke.com",
    "shanghai": "https://sh.zu.ke.com",
    "guangzhou": "https://gz.zu.ke.com",
    "shenzhen": "https://sz.zu.ke.com",
    "chengdu": "https://cd.zu.ke.com",
    "hangzhou": "https://hz.zu.ke.com",
    "nanjing": "https://nj.zu.ke.com",
    "wuhan": "https://wh.zu.ke.com",
    "tianjin": "https://tj.zu.ke.com",
    "chongqing": "https://cq.zu.ke.com",
    "changchun": "https://cc.zu.ke.com",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


class BeikeScraper(BaseScraper):

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
                    logger.warning("[贝壳] 触发验证码，等待后重试 (尝试 %d/%d)", attempt + 1, max_retries)
                    time.sleep(random.uniform(10, 20))
                    continue

                return soup
            except Exception as e:
                logger.error("[贝壳] 请求失败 (尝试 %d/%d): %s", attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 10))

        return None

    @property
    def source_name(self):
        return "beike"

    def fetch_listings(self, city="beijing"):
        base_url = BEIKE_CITIES.get(city)
        if not base_url:
            logger.error("不支持的城市: %s", city)
            return []

        logger.info("[贝壳-%s] 开始爬取: %s", city, base_url)
        listings = []

        try:
            self._fetch_page(base_url)
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            logger.warning("[贝壳] 访问首页失败: %s", e)

        for page in range(1, self.max_pages + 1):
            url = base_url + "/zufang/" if page == 1 else "{}/zufang/pg{}/".format(base_url, page)
            logger.info("[贝壳] 第 %d 页: %s", page, url)

            try:
                soup = self._fetch_page(url)
                if not soup:
                    logger.error("[贝壳] 第 %d 页获取失败，跳过", page)
                    continue

                page_listings = self._parse_list_page(soup, url, base_url)
                listings.extend(page_listings)
                logger.info("[贝壳] 第 %d 页解析到 %d 条", page, len(page_listings))

                if not page_listings:
                    logger.info("[贝壳] 第 %d 页无数据，停止爬取", page)
                    break
            except Exception as e:
                logger.error("[贝壳] 第 %d 页爬取失败: %s", page, e)

            if page < self.max_pages:
                delay = self.request_interval + random.uniform(2, 5)
                logger.debug("[贝壳] 等待 %.1f 秒...", delay)
                time.sleep(delay)

        logger.info("[贝壳-%s] 爬取完成，共获取 %d 条房源", city, len(listings))
        return listings

    def _parse_list_page(self, soup, page_url, base_url):
        listings = []
        items = soup.select("div.content__list--item")

        if not items:
            items = soup.select("div.content__list--item--main")

        if not items:
            items = soup.select("div.list-wrap li")

        if not items:
            logger.warning("[贝壳] 未找到房源列表项: %s", page_url)
            logger.debug("[贝壳] 页面标题: %s", soup.title.string if soup.title else "无")
            return []

        for item in items:
            listing = parse_listing_item(item, base_url, self.source_name)
            if listing:
                listings.append(listing)

        return listings
