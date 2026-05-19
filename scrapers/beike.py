import logging

from scrapers.base import BaseScraper, fetch_page, parse_listing_item

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
            url = base_url + "/zufang/" if page == 1 else "{}/zufang/pg{}/".format(base_url, page)
            logger.info("[贝壳] 第 %d 页: %s", page, url)

            try:
                soup = fetch_page(url)
                page_listings = self._parse_list_page(soup, url, base_url)
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

    def _parse_list_page(self, soup, page_url, base_url):
        listings = []
        items = soup.select("div.content__list--item")
        if not items:
            items = soup.select("div.list-wrap li")

        if not items:
            logger.warning("[贝壳] 未找到房源列表项: %s", page_url)
            return []

        for item in items:
            listing = parse_listing_item(item, base_url, self.source_name)
            if listing:
                listings.append(listing)

        return listings
