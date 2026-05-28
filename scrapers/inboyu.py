import logging
import re

from models import HousingListing
from scrapers.base import BaseScraper, fetch_page, generate_listing_id

logger = logging.getLogger(__name__)

INBOYU_BASE = "https://www.inboyu.com"

CITY_MAP = {
    "北京": "beijing", "上海": "shanghai", "广州": "guangzhou",
    "深圳": "shenzhen", "成都": "chengdu", "杭州": "hangzhou",
    "南京": "nanjing", "武汉": "wuhan", "天津": "tianjin",
    "重庆": "chongqing", "长沙": "changsha", "长春": "changchun",
    "厦门": "xiamen", "西安": "xian", "佛山": "foshan",
}


class InboyuScraper(BaseScraper):

    def __init__(self, city="长春", request_interval=3.0):
        super().__init__(request_interval=request_interval)
        self.city = city

    @property
    def source_name(self):
        return "inboyu"

    def fetch_listings(self, city=None, existing_ids=None):
        if existing_ids is None:
            existing_ids = set()
        city = city or self.city
        city_code = CITY_MAP.get(city, city)
        logger.info("[泊寓] 开始爬取城市: %s (%s)", city, city_code)

        url = "{}/{}/house-type/list".format(INBOYU_BASE, city_code)
        logger.info("[泊寓] 访问: %s", url)

        try:
            soup = fetch_page(url)
            listings = self._parse_list_page(soup, city, existing_ids)
            logger.info("[泊寓] %s 获取 %d 条房源", city, len(listings))
            return listings
        except Exception as e:
            logger.error("[泊寓] %s 爬取失败: %s", city, e)
            return []

    def _parse_list_page(self, soup, city_name, existing_ids):
        listings = []

        links = soup.select("a[href*='house-type/detail']")
        if not links:
            links = soup.select("a[href*='detail']")

        for link in links:
            listing = self._parse_link(link, city_name)
            if listing:
                if listing.listing_id in existing_ids:
                    continue
                listings.append(listing)

        return listings

    def _parse_link(self, link, city_name):
        href = link.get("href", "")
        text = link.get_text(" ", strip=True)

        if not href or not text:
            return None

        if not href.startswith("http"):
            href = INBOYU_BASE + href

        title_match = re.search(r"(泊寓[^\d]*?店)", text)
        if not title_match:
            title_match = re.search(r"([^\d]+?)(?:\d+个户型)", text)
        title = title_match.group(1).strip() if title_match else text[:30]

        if not title or len(title) < 3:
            return None

        rooms_match = re.search(r"(\d+)个户型", text)
        rooms = rooms_match.group(1) if rooms_match else ""

        address = ""
        addr_match = re.search(r"户型(.+?)(?:\d+\.?\d*元)", text)
        if addr_match:
            address = addr_match.group(1).strip()

        price = 0.0
        price_match = re.search(r"(\d+(?:\.\d+)?)\s*元/月", text)
        if price_match:
            price = float(price_match.group(1))

        area = None
        area_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|平米|m2)", text)
        if area_match:
            area = float(area_match.group(1))

        district = city_name
        if address:
            for d in ["朝阳区", "南关区", "宽城区", "二道区", "绿园区",
                       "净月区", "高新区", "经开区", "汽车区"]:
                if d in address:
                    district = d
                    break

        listing_id = generate_listing_id(self.source_name, href)

        return HousingListing(
            listing_id=listing_id,
            source=self.source_name,
            title=title,
            price=price,
            area=area,
            rooms=rooms + "个户型" if rooms else None,
            address=address,
            district=district,
            url=href,
        )
