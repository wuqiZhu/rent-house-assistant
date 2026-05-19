import logging
import re

from models import HousingListing
from scrapers.base import BaseScraper, fetch_page, generate_listing_id

logger = logging.getLogger(__name__)

MOFANG_BASE = "https://www.mofang.com"

CITY_MAP = {
    "北京": "beijing", "上海": "shanghai", "广州": "guangzhou",
    "深圳": "shenzhen", "成都": "chengdu", "杭州": "hangzhou",
    "南京": "nanjing", "武汉": "wuhan", "天津": "tianjin",
    "重庆": "chongqing", "长沙": "changsha", "长春": "changchun",
    "苏州": "suzhou", "郑州": "zhengzhou", "西安": "xian",
}


class MofangScraper(BaseScraper):

    def __init__(self, city="长春", request_interval=3.0):
        super().__init__(request_interval=request_interval)
        self.city = city

    @property
    def source_name(self):
        return "mofang"

    def fetch_listings(self, city=None):
        city = city or self.city
        city_code = CITY_MAP.get(city, city)
        logger.info("[魔方公寓] 开始爬取城市: %s (%s)", city, city_code)

        all_listings = []

        try:
            listings = self._crawl_city_page(city_code, city)
            all_listings.extend(listings)
            logger.info("[魔方公寓] %s 获取 %d 条", city, len(listings))
        except Exception as e:
            logger.error("[魔方公寓] %s 爬取失败: %s", city, e)

        logger.info("[魔方公寓] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _crawl_city_page(self, city_code, city_name):
        url = "{}/{}".format(MOFANG_BASE, city_code)
        logger.info("[魔方公寓] 访问: %s", url)

        soup = fetch_page(url)
        listings = []

        cards = soup.select("div.house-item, div.room-item, li.house-item, li.room-item")
        if not cards:
            cards = soup.select("div[class*='house'], div[class*='room'], div[class*='apartment']")

        if not cards:
            logger.info("[魔方公寓] 尝试备用解析方式")
            return self._parse_generic(soup, city_name)

        for card in cards:
            listing = self._parse_card(card, city_name)
            if listing:
                listings.append(listing)

        return listings

    def _parse_generic(self, soup, city_name):
        listings = []

        all_links = soup.select("a[href*='house'], a[href*='room'], a[href*='apartment']")
        for link in all_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or len(title) < 4:
                continue

            if any(kw in title for kw in ["首页", "关于", "登录", "注册", "APP"]):
                continue

            if not href.startswith("http"):
                href = MOFANG_BASE + href

            price = self._extract_price_from_context(link)
            area = self._extract_area_from_text(title)

            listing = HousingListing(
                listing_id=generate_listing_id(self.source_name, href),
                source=self.source_name,
                title=title,
                price=price,
                area=area,
                district=city_name,
                url=href,
            )
            listings.append(listing)

        return listings

    def _parse_card(self, card, city_name):
        title_el = (
            card.select_one("h3, h2, .name, .title, .house-name, .room-name")
            or card.select_one("a")
        )
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if not title or len(title) < 2:
            return None

        link_el = card.select_one("a[href]")
        href = ""
        if link_el:
            href = link_el.get("href", "")
        elif title_el.name == "a":
            href = title_el.get("href", "")

        if href and not href.startswith("http"):
            href = MOFANG_BASE + href

        if not href:
            return None

        price = 0.0
        price_el = card.select_one(".price, span[class*='price'], .money")
        if price_el:
            price_text = price_el.get_text(strip=True)
            m = re.search(r"(\d+(?:\.\d+)?)", price_text)
            if m:
                price = float(m.group(1))

        if price == 0:
            card_text = card.get_text(" ", strip=True)
            price = self._extract_price_from_text(card_text) or 0

        area = None
        area_el = card.select_one(".area, span[class*='area'], .size")
        if area_el:
            m = re.search(r"(\d+(?:\.\d+)?)", area_el.get_text(strip=True))
            if m:
                area = float(m.group(1))

        rooms = None
        rooms_el = card.select_one(".room-type, .type, span[class*='type']")
        if rooms_el:
            rooms = rooms_el.get_text(strip=True)

        address = None
        addr_el = card.select_one(".address, .location, span[class*='address']")
        if addr_el:
            address = addr_el.get_text(strip=True)

        district = city_name
        if address:
            for d in ["朝阳", "南关", "宽城", "二道", "绿园", "净月", "高新"]:
                if d in address:
                    district = d + "区"
                    break

        img_el = card.select_one("img")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-src") or img_el.get("src") or ""
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        return HousingListing(
            listing_id=generate_listing_id(self.source_name, href),
            source=self.source_name,
            title=title,
            price=price,
            area=area,
            rooms=rooms,
            address=address,
            district=district,
            url=href,
            images=[image_url] if image_url else [],
        )

    @staticmethod
    def _extract_price_from_text(text):
        patterns = [
            r"(\d+)\s*元/月",
            r"(\d+)\s*元",
            r"￥\s*(\d+)",
            r"¥\s*(\d+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = float(m.group(1))
                if 300 <= val <= 50000:
                    return val
        return None

    @staticmethod
    def _extract_price_from_context(element):
        parent = element.parent
        if not parent:
            return 0
        text = parent.get_text(" ", strip=True)
        patterns = [r"(\d+)\s*元/月", r"(\d+)\s*元", r"￥\s*(\d+)"]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = float(m.group(1))
                if 300 <= val <= 50000:
                    return val
        return 0

    @staticmethod
    def _extract_area_from_text(text):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|平|平米|平方)", text)
        return float(m.group(1)) if m else None
