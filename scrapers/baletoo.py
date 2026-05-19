import logging
import re
import warnings

from models import HousingListing
from scrapers.base import BaseScraper, generate_listing_id

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

CITY_MAP = {
    "上海": "sh", "北京": "bj", "深圳": "sz", "杭州": "hz",
    "南京": "nj", "苏州": "suzhou", "广州": "gz", "成都": "cd",
    "大连": "dl", "天津": "tj", "重庆": "cq", "武汉": "wh",
    "西安": "xa", "郑州": "zz",
}


class BaletooScraper(BaseScraper):

    def __init__(self, cities=None, request_interval=3.0):
        super().__init__(request_interval=request_interval)
        self.cities = cities or ["bj"]

    @property
    def source_name(self):
        return "baletoo"

    def fetch_listings(self, city=None):
        all_listings = []

        for city_code in self.cities:
            city_cn = next((k for k, v in CITY_MAP.items() if v == city_code), city_code)
            logger.info("[巴乐兔] 开始爬取城市: %s (%s)", city_cn, city_code)

            try:
                listings = self._crawl_city(city_code, city_cn)
                all_listings.extend(listings)
                logger.info("[巴乐兔] %s 获取 %d 条房源", city_cn, len(listings))
            except Exception as e:
                logger.error("[巴乐兔] %s 爬取失败: %s", city_cn, e)

        logger.info("[巴乐兔] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _crawl_city(self, city_code, city_name):
        url = "http://{}.baletu.com/".format(city_code)
        logger.info("[巴乐兔] 访问: %s", url)

        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                timeout=15,
            )
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error("[巴乐兔] 请求失败: %s", e)
            return []

        listings = []
        links = soup.select("a[href*='house']")

        for a in links:
            href = a.get("href", "")
            text = a.get_text(strip=True)

            if "/house/" not in href or not text or len(text) < 3:
                continue

            id_match = re.search(r'/house/(\d+)\.html', href)
            if not id_match:
                continue

            house_id = id_match.group(1)

            if not href.startswith("http"):
                href = "http://{}{}".format(city_code + ".baletu.com", href) if href.startswith("//") else "http://{}{}".format(city_code + ".baletu.com", href)

            parent = a.parent
            parent_text = parent.get_text(" ", strip=True) if parent else ""

            price = 0.0
            price_match = re.search(r'(\d+)\s*元', parent_text)
            if price_match:
                price = float(price_match.group(1))

            area = None
            area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|平米|m2)', parent_text)
            if area_match:
                area = float(area_match.group(1))

            listing = HousingListing(
                listing_id=generate_listing_id(self.source_name, href),
                source=self.source_name,
                title=text,
                price=price,
                area=area,
                district=city_name,
                url=href,
            )
            listings.append(listing)

        return listings
