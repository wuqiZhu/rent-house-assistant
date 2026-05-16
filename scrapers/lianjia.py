import json
import logging
import re
from typing import Optional

from models import HousingListing
from scrapers.base import BaseScraper, fetch_page, generate_listing_id, parse_relative_time

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
    "dalian": "https://dl.lianjia.com/zufang/",
    "dongguan": "https://dg.lianjia.com/zufang/",
    "foshan": "https://fs.lianjia.com/zufang/",
    "hefei": "https://hf.lianjia.com/zufang/",
    "huizhou": "https://hui.lianjia.com/zufang/",
    "jinan": "https://jn.lianjia.com/zufang/",
    "langfang": "https://lf.lianjia.com/zufang/",
    "qingdao": "https://qd.lianjia.com/zufang/",
    "suzhou": "https://su.lianjia.com/zufang/",
    "shijiazhuang": "https://sjz.lianjia.com/zufang/",
    "shenyang": "https://sy.lianjia.com/zufang/",
    "wuxi": "https://wx.lianjia.com/zufang/",
    "xiamen": "https://xm.lianjia.com/zufang/",
    "xian": "https://xa.lianjia.com/zufang/",
    "yantai": "https://yt.lianjia.com/zufang/",
    "zhengzhou": "https://zz.lianjia.com/zufang/",
    "zhongshan": "https://zs.lianjia.com/zufang/",
    "zhuhai": "https://zh.lianjia.com/zufang/",
}


class LianjiaScraper(BaseScraper):

    def __init__(self, request_interval: float = 5.0, max_pages: int = 20):
        super().__init__(request_interval=request_interval)
        self.max_pages = max_pages

    @property
    def source_name(self) -> str:
        return "lianjia"

    def fetch_listings(self, city: str = "beijing"):
        base_url = LIANJIA_CITIES.get(city)
        if not base_url:
            logger.error(f"不支持的城市: {city}，可选: {list(LIANJIA_CITIES.keys())}")
            return []

        logger.info(f"[链家-{city}] 开始爬取: {base_url}")
        listings = []

        total_pages = self._get_total_pages(base_url)
        pages_to_crawl = min(total_pages, self.max_pages)
        logger.info(f"[链家-{city}] 共 {total_pages} 页，本次爬取 {pages_to_crawl} 页")

        for page in range(1, pages_to_crawl + 1):
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}pg{page}/"

            logger.info(f"[链家] 第 {page}/{pages_to_crawl} 页: {url}")

            try:
                soup = fetch_page(url)
                page_listings = self._parse_list_page(soup, url)
                listings.extend(page_listings)
                logger.info(f"[链家] 第 {page} 页解析到 {len(page_listings)} 条")
            except Exception as e:
                logger.error(f"[链家] 第 {page} 页爬取失败: {e}")

            if page < pages_to_crawl:
                self._throttle()

        logger.info(f"[链家-{city}] 爬取完成，共获取 {len(listings)} 条房源")
        return listings

    def _get_total_pages(self, base_url: str) -> int:
        try:
            soup = fetch_page(base_url)

            page_box = soup.select_one("div.page-box")
            if page_box:
                page_data_str = page_box.get("page-data")
                if page_data_str:
                    page_data = json.loads(page_data_str)
                    total = page_data.get("totalPage", 1)
                    if total:
                        return int(total)

            paginator = soup.select("div.content__pg div.pg-left")
            if not paginator:
                paginator = soup.select("div.paginator a")
            if paginator:
                last_page = 1
                for a in paginator:
                    text = a.get_text(strip=True)
                    if text.isdigit():
                        last_page = max(last_page, int(text))
                return last_page

        except Exception as e:
            logger.warning(f"[链家] 获取总页数失败，使用默认值: {e}")

        return 1

    def _parse_list_page(self, soup, page_url: str):
        listings = []

        items = soup.select("div.content__list--item")
        if not items:
            items = soup.select("div.list-wrap li")
        if not items:
            items = soup.select("ul.house-lst li")

        if not items:
            logger.warning(f"[链家] 未找到房源列表项，页面结构可能已变: {page_url}")
            self._debug_page_structure(soup)
            return []

        for item in items:
            try:
                listing = self._parse_item(item)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.debug(f"[链家] 解析单条房源失败: {e}")

        return listings

    def _parse_item(self, item) -> Optional[HousingListing]:
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
            detail_url = "https://bj.lianjia.com" + href
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

    def _parse_des(self, text: str):
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

    def _debug_page_structure(self, soup):
        if logger.isEnabledFor(logging.DEBUG):
            divs_with_class = soup.select("div[class]")[:10]
            for div in divs_with_class:
                cls = div.get("class", [])
                logger.debug(f"  div.{cls}")
