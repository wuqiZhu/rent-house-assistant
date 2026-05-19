import json
import logging

from scrapers.base import BaseScraper, fetch_page, parse_listing_item

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


class LianjiaScraper(BaseScraper):

    def __init__(self, request_interval=5.0, max_pages=20):
        super().__init__(request_interval=request_interval)
        self.max_pages = max_pages

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

        total_pages = self._get_total_pages(base_url)
        pages_to_crawl = min(total_pages, self.max_pages)
        logger.info("[链家-%s] 共 %d 页，本次爬取 %d 页", city, total_pages, pages_to_crawl)

        for page in range(1, pages_to_crawl + 1):
            url = base_url if page == 1 else "{}pg{}/".format(base_url, page)
            logger.info("[链家] 第 %d/%d 页: %s", page, pages_to_crawl, url)

            try:
                soup = fetch_page(url)
                page_listings = self._parse_list_page(soup, url, base_url)
                listings.extend(page_listings)
                logger.info("[链家] 第 %d 页解析到 %d 条", page, len(page_listings))
            except Exception as e:
                logger.error("[链家] 第 %d 页爬取失败: %s", page, e)

            if page < pages_to_crawl:
                self._throttle()

        logger.info("[链家-%s] 爬取完成，共获取 %d 条房源", city, len(listings))
        return listings

    def _get_total_pages(self, base_url):
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
        except Exception as e:
            logger.warning("[链家] 获取总页数失败，使用默认值: %s", e)
        return 1

    def _parse_list_page(self, soup, page_url, base_url):
        listings = []
        items = soup.select("div.content__list--item")
        if not items:
            items = soup.select("div.list-wrap li")
        if not items:
            items = soup.select("ul.house-lst li")

        if not items:
            logger.warning("[链家] 未找到房源列表项: %s", page_url)
            return []

        for item in items:
            listing = parse_listing_item(item, base_url, self.source_name)
            if listing:
                listings.append(listing)

        return listings
