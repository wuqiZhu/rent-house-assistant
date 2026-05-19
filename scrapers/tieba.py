import logging
import re

from models import HousingListing
from scrapers.base import BaseScraper, fetch_page, generate_listing_id

logger = logging.getLogger(__name__)

DEFAULT_BARS = [
    "长春租房",
    "长春租房吧",
]


class TiebaScraper(BaseScraper):

    def __init__(
        self,
        bars=None,
        max_pages=10,
        exclude_keywords=None,
        include_keywords=None,
        request_interval=3.0,
    ):
        super().__init__(request_interval=request_interval)
        self.bars = bars or DEFAULT_BARS
        self.max_pages = max_pages
        self.exclude_keywords = exclude_keywords or ["求租", "合租找室友"]
        self.include_keywords = include_keywords or []

    @property
    def source_name(self):
        return "tieba"

    def fetch_listings(self, city=None):
        all_listings = []

        for bar_name in self.bars:
            logger.info("[贴吧] 开始爬取贴吧: %s", bar_name)
            try:
                listings = self._crawl_bar(bar_name)
                all_listings.extend(listings)
                logger.info("[贴吧] %s 获取 %d 条", bar_name, len(listings))
            except Exception as e:
                logger.error("[贴吧] %s 爬取失败: %s", bar_name, e)

        logger.info("[贴吧] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _crawl_bar(self, bar_name):
        listings = []
        for page in range(self.max_pages):
            pn = page * 50
            url = "https://tieba.baidu.com/f?kw={}&ie=utf-8&pn={}".format(
                bar_name, pn
            )
            logger.info("[贴吧] %s 第%d页", bar_name, page + 1)

            try:
                soup = fetch_page(url, encoding="utf-8")
                thread_list = soup.select_one("#thread_list")
                if not thread_list:
                    logger.warning("[贴吧] %s 未找到帖子列表", bar_name)
                    break

                threads = thread_list.select("li.j_thread_list")
                if not threads:
                    break

                found_any = False
                for thread in threads:
                    title_el = thread.select_one("a.j_th_tit")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    if not href:
                        continue

                    if not self._pass_filter(title):
                        continue

                    detail_url = "https://tieba.baidu.com" + href

                    author_el = thread.select_one("span.tb_icon_author")
                    author = author_el.get_text(strip=True) if author_el else ""

                    reply_el = thread.select_one("span.threadlist_rep_num")
                    reply_count = 0
                    if reply_el:
                        try:
                            reply_count = int(reply_el.get_text(strip=True))
                        except ValueError:
                            pass

                    price = self._extract_price(title)
                    area = self._extract_area(title)
                    district = self._extract_district(title)

                    listing = HousingListing(
                        listing_id=generate_listing_id(self.source_name, detail_url),
                        source=self.source_name,
                        title=title,
                        price=price if price else 0,
                        area=area,
                        district=district,
                        url=detail_url,
                    )
                    listings.append(listing)
                    found_any = True

                if not found_any and page > 0:
                    break

            except Exception as e:
                logger.error("[贴吧] %s 第%d页失败: %s", bar_name, page + 1, e)

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
    def _extract_price(text):
        patterns = [
            r"(\d+)\s*元/月",
            r"(\d+)\s*元",
            r"租金[：:]?\s*(\d+)",
            r"(\d{3,5})\s*(?:块|元)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = float(m.group(1))
                if 300 <= val <= 50000:
                    return val

        numbers = re.findall(r"\b(\d{3,5})\b", text)
        for n in numbers:
            val = int(n)
            if 500 <= val <= 20000:
                return float(val)
        return None

    @staticmethod
    def _extract_area(text):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|平|平米|平方)", text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_district(text):
        districts = [
            "朝阳区", "南关区", "宽城区", "二道区", "绿园区",
            "双阳区", "九台区", "榆树市", "德惠市", "农安县",
            "净月区", "高新区", "经开区", "汽车区",
        ]
        for d in districts:
            if d in text:
                return d
        return None
