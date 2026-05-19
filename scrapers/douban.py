import logging
import os
import re

from models import HousingListing
from scrapers.base import BaseScraper, generate_listing_id

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
        if not self.cookie:
            logger.warning("[豆瓣] 未配置Cookie，跳过豆瓣爬取。请设置 DOUBAN_COOKIE 环境变量")
            return []

        all_listings = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[豆瓣] 未安装playwright，请运行: pip install playwright && playwright install chromium")
            return []

        cookie_list = self._parse_cookie_to_list()

        pw = None
        browser = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN",
                viewport={"width": 1920, "height": 1080},
            )
            context.add_cookies(cookie_list)
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)

            for group_id, group_name in self.groups:
                logger.info("[豆瓣] 开始爬取小组: %s (%s)", group_name, group_id)
                try:
                    listings = self._crawl_group_pw(page, group_id, group_name)
                    all_listings.extend(listings)
                    logger.info("[豆瓣] %s 获取 %d 条", group_name, len(listings))
                except Exception as e:
                    logger.error("[豆瓣] %s 爬取失败: %s", group_name, e)

        except Exception as e:
            logger.error("[豆瓣] Playwright异常: %s", e)
        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass

        logger.info("[豆瓣] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _parse_cookie_to_list(self):
        cookie_list = []
        if not self.cookie:
            return cookie_list
        for pair in self.cookie.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookie_list.append({
                    "name": k.strip(),
                    "value": v.strip().strip('"'),
                    "domain": ".douban.com",
                    "path": "/",
                })
        return cookie_list

    def _crawl_group_pw(self, page, group_id, group_name):
        from bs4 import BeautifulSoup

        listings = []
        for page_num in range(self.max_pages):
            start = page_num * 25
            url = "https://www.douban.com/group/{}/discussion?start={}&type=new".format(
                group_id, start
            )
            logger.info("[豆瓣] %s 第%d页", group_name, page_num + 1)

            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                final_url = page.url
                if "sec.douban.com" in final_url or "login" in final_url:
                    logger.warning("[豆瓣] %s Cookie已过期，需要重新登录", group_name)
                    break

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                table = soup.select_one("table.olt")
                if not table:
                    logger.warning("[豆瓣] %s 未找到帖子列表", group_name)
                    break

                rows = table.select("tr")[1:]
                if not rows:
                    break

                found_any = False
                for row in rows:
                    title_el = row.select_one("td.title a")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    link = title_el.get("href", "")

                    if not self._pass_filter(title):
                        continue

                    price = self._extract_price(title)
                    area = self._extract_area(title)

                    listing = HousingListing(
                        listing_id=generate_listing_id(self.source_name, link),
                        source=self.source_name,
                        title=title,
                        price=price if price else 0,
                        area=area,
                        url=link,
                    )
                    listings.append(listing)
                    found_any = True

                if not found_any and page_num > 0:
                    break

            except Exception as e:
                logger.error("[豆瓣] %s 第%d页失败: %s", group_name, page_num + 1, e)

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
