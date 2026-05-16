import json
import logging
import re

from models import HousingListing
from scrapers.base import BaseScraper, fetch_page, generate_listing_id, parse_relative_time

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


class BeikeScraper(BaseScraper):

    def __init__(self, request_interval=5.0, max_pages=20):
        super().__init__(request_interval=request_interval)
        self.max_pages = max_pages

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

        for page in range(1, self.max_pages + 1):
            if page == 1:
                url = base_url + "/zufang/"
            else:
                url = base_url + "/zufang/pg{}/".format(page)

            logger.info("[贝壳] 第 %d 页: %s", page, url)

            try:
                soup = fetch_page(url)
                page_listings = self._parse_list_page(soup, base_url)
                listings.extend(page_listings)
                logger.info("[贝壳] 第 %d 页解析到 %d 条", page, len(page_listings))

                if not page_listings:
                    break

            except Exception as e:
                logger.error("[贝壳] 第 %d 页爬取失败: %s", page, e)

            if page < self.max_pages:
                self._throttle()

        logger.info("[贝壳-%s] 爬取完成，共获取 %d 条房源", city, len(listings))
        return listings

    def _parse_list_page(self, soup, base_url):
        listings = []

        items = soup.select("div.content__list--item")
        if not items:
            items = soup.select("div.list-wrap li")

        if not items:
            logger.warning("[贝壳] 未找到房源列表项")
            return []

        for item in items:
            try:
                listing = self._parse_item(item, base_url)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.debug("[贝壳] 解析单条房源失败: %s", e)

        return listings

    def _parse_item(self, item, base_url):
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
            detail_url = base_url + href
        else:
            detail_url = href

        des_el = (
            item.select_one("p.content__list--item--des")
            or item.select_one("div.des")
        )
        des_text = des_el.get_text(" ", strip=True) if des_el else ""
        rooms, area, floor = self._parse_des(des_text)

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

        return HousingListing(
            listing_id=generate_listing_id(detail_url),
            source=self.source_name,
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

    def _parse_des(self, text):
        parts = [p.strip() for p in re.split(r"[/\-|·]", text) if p.strip()]
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
