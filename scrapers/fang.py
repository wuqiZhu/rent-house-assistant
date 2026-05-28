import logging
import re
import time

from models import HousingListing
from scrapers.base import BaseScraper, generate_listing_id

logger = logging.getLogger(__name__)

FANG_CITY_MAP = {
    "北京": "", "上海": "sh", "广州": "gz", "深圳": "sz",
    "成都": "cd", "杭州": "hz", "南京": "nj", "武汉": "wh",
    "天津": "tj", "重庆": "cq", "长沙": "cs", "长春": "changchun",
    "厦门": "xm", "西安": "xa", "郑州": "zz", "大连": "dl",
    "沈阳": "sy", "哈尔滨": "heb", "济南": "jn", "青岛": "qd",
    "昆明": "km", "贵阳": "gy", "合肥": "hf", "福州": "fz",
}

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
]

STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
    window.chrome = {runtime: {}};
"""


class FangScraper(BaseScraper):

    def __init__(self, city="长春", max_pages=3, request_interval=5.0):
        super().__init__(request_interval=request_interval)
        self.city = city
        self.max_pages = max_pages

    @property
    def source_name(self):
        return "fang"

    def fetch_listings(self, city=None, existing_ids=None):
        if existing_ids is None:
            existing_ids = set()
        city = city or self.city
        city_code = FANG_CITY_MAP.get(city, city)
        logger.info("[房天下] 开始爬取城市: %s (%s)", city, city_code)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[房天下] 未安装playwright，请运行: pip install playwright && playwright install chromium")
            return []

        pw = None
        browser = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True, args=STEALTH_ARGS)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            page.add_init_script(STEALTH_JS)

            all_listings = []
            seen_ids = set()

            if city_code:
                base_url = "https://{}.zu.fang.com".format(city_code)
            else:
                base_url = "https://zu.fang.com"

            for page_num in range(1, self.max_pages + 1):
                if page_num == 1:
                    url = "{}/".format(base_url)
                else:
                    url = "{}/house/i3{}/".format(base_url, page_num)

                logger.info("[房天下] 第%d页: %s", page_num, url)

                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    final_url = page.url
                    if "check" in final_url.lower():
                        logger.warning("[房天下] 触发验证页面，请在30秒内手动滑动验证码！")
                        page.wait_for_timeout(30000)
                        if "check" in page.url.lower():
                            logger.warning("[房天下] 验证超时未通过，停止翻页")
                            break

                    html = page.content()
                    listings = self._parse_html(html, city, existing_ids, base_url)

                    new_count = 0
                    for l in listings:
                        if l.listing_id not in seen_ids:
                            seen_ids.add(l.listing_id)
                            all_listings.append(l)
                            new_count += 1

                    logger.info("[房天下] 第%d页: %d 条房源（新增 %d）", page_num, len(listings), new_count)

                    if new_count == 0:
                        logger.info("[房天下] 无新增房源，停止翻页")
                        break

                except Exception as e:
                    logger.error("[房天下] 第%d页失败: %s", page_num, e)
                    break

                self._throttle()

            logger.info("[房天下] %s 共获取 %d 条房源", city, len(all_listings))
            return all_listings

        except Exception as e:
            logger.error("[房天下] %s 爬取失败: %s", city, e)
            return []
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

    def _parse_html(self, html, city_name, existing_ids, base_url=""):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        listings = []

        items = soup.select("dl.list")
        if not items:
            items = soup.select("dl")
            items = [dl for dl in items if dl.select("a")]

        for item in items:
            listing = self._parse_item(item, city_name, base_url)
            if listing:
                if listing.listing_id in existing_ids:
                    continue
                listings.append(listing)

        return listings

    def _parse_item(self, item, city_name, base_url=""):
        text = item.get_text(" ", strip=True)

        if not text or len(text) < 10:
            return None

        price_match = re.search(r'(\d+(?:\.\d+)?)\s*元/月', text)
        if not price_match:
            price_match = re.search(r'(\d+(?:\.\d+)?)\s*元', text)
        if not price_match:
            return None

        price = float(price_match.group(1))
        if price < 100 or price > 50000:
            return None

        title = ""
        title_el = item.select_one("a")
        if title_el:
            title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            title = text[:50]

        href = ""
        if title_el:
            href = title_el.get("href", "")
        if href and not href.startswith("http"):
            if href.startswith("//"):
                href = "https:" + href
            elif base_url:
                href = base_url.rstrip("/") + href

        rooms = None
        rooms_match = re.search(r'(\d+室\d+厅)', text)
        if rooms_match:
            rooms = rooms_match.group(1)

        area = None
        area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|平米|m2)', text)
        if area_match:
            area = float(area_match.group(1))

        district = city_name
        district_match = re.search(r'(南关|经开|宽城|二道|绿园|高新|朝阳|汽开|净月|双阳|九台|合隆|朝阳|海淀|丰台|浦东|徐汇)', text)
        if district_match:
            district = district_match.group(1)

        address = ""
        addr_match = re.search(r'(?:南关|经开|宽城|二道|绿园|高新|朝阳|汽开|净月)\s*[-\s]\s*(.+?)(?:\d+\s*元)', text)
        if addr_match:
            address = addr_match.group(1).strip()

        listing_id = generate_listing_id(self.source_name, href or title)

        return HousingListing(
            listing_id=listing_id,
            source=self.source_name,
            title=title,
            price=price,
            area=area,
            rooms=rooms,
            address=address,
            district=district,
            url=href,
        )
