import logging
import os
import re

from models import HousingListing
from scrapers.base import BaseScraper, fetch_page, generate_listing_id

logger = logging.getLogger(__name__)

DEFAULT_GROUPS = [
    ("beijingzufang", "北京租房"),
    ("549574", "北京租房2"),
    ("596202", "北京租房3"),
    ("26926", "北京租房豆瓣"),
    ("hdzufang", "北京海淀租房"),
]


class DoubanScraper(BaseScraper):

    def __init__(
        self,
        groups=None,
        cookie="",
        max_pages=10,
        exclude_keywords=None,
        include_keywords=None,
        request_interval=6.0,
    ):
        super().__init__(request_interval=request_interval)
        self.groups = groups or DEFAULT_GROUPS
        self.cookie = cookie or os.environ.get("DOUBAN_COOKIE", "")
        self.max_pages = max_pages
        self.exclude_keywords = exclude_keywords or ["求租", "合租找室友"]
        self.include_keywords = include_keywords or []

    @property
    def source_name(self):
        return "douban"

    def fetch_listings(self, city=None):
        all_listings = []
        cookies = self._parse_cookie()

        for group_id, group_name in self.groups:
            logger.info("[豆瓣] 开始爬取小组: %s (%s)", group_name, group_id)
            try:
                listings = self._crawl_group(group_id, group_name, cookies)
                all_listings.extend(listings)
                logger.info("[豆瓣] %s 获取 %d 条", group_name, len(listings))
            except Exception as e:
                logger.error("[豆瓣] %s 爬取失败: %s", group_name, e)

        logger.info("[豆瓣] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _parse_cookie(self):
        cookies = {}
        if not self.cookie:
            return cookies
        for pair in self.cookie.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def _crawl_group(self, group_id, group_name, cookies):
        listings = []
        for page in range(self.max_pages):
            start = page * 25
            url = "https://www.douban.com/group/{}/discussion?start={}&type=new".format(
                group_id, start
            )
            logger.info("[豆瓣] %s 第%d页", group_name, page + 1)

            try:
                soup = fetch_page(url, cookies=cookies)

                table = soup.select_one("table.olt")
                if not table:
                    logger.warning("[豆瓣] %s 未找到帖子列表，可能Cookie过期", group_name)
                    break

                rows = table.select("tr")[1:]
                if not rows:
                    break

                found_any = False
                for row in rows:
                    title_el = row.select_one("td.title a")
                    time_el = row.select_one("td.td-time")

                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    link = title_el.get("href", "")

                    pub_time_str = ""
                    if time_el:
                        pub_time_str = time_el.get("title", "") or time_el.get_text(strip=True)

                    if not self._pass_filter(title):
                        continue

                    price = self._extract_price(title)
                    area = self._extract_area(title)

                    listing = HousingListing(
                        listing_id=generate_listing_id(link),
                        source=self.source_name,
                        title=title,
                        price=price if price else 0,
                        area=area,
                        url=link,
                    )
                    listings.append(listing)
                    found_any = True

                if not found_any and page > 0:
                    break

            except Exception as e:
                logger.error("[豆瓣] %s 第%d页失败: %s", group_name, page + 1, e)

            self._throttle()

        return listings

    def _pass_filter(self, title):
        for kw in self.exclude_keywords:
            if kw in title:
                return False
        if self.include_keywords:
            return any(kw in title for kw in self.include_keywords)
        return True

    @staticmethod
    def _extract_price(title):
        patterns = [
            r"(\d+)\s*元/月",
            r"(\d+)\s*元",
            r"租金[：:]?\s*(\d+)",
            r"(\d{3,5})\s*(?:块|元)",
        ]
        for pat in patterns:
            m = re.search(pat, title)
            if m:
                val = float(m.group(1))
                if 300 <= val <= 50000:
                    return val

        numbers = re.findall(r"\b(\d{3,5})\b", title)
        for n in numbers:
            val = int(n)
            if 500 <= val <= 20000:
                return float(val)
        return None

    @staticmethod
    def _extract_area(title):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|平|平米|平方)", title)
        return float(m.group(1)) if m else None
