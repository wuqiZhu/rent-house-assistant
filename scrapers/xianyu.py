import hashlib
import json
import logging
import os
import re
import time

import requests

from models import HousingListing
from scrapers.base import BaseScraper, generate_listing_id

logger = logging.getLogger(__name__)

SEARCH_API = "https://h5api.m.taobao.com/h5/mtop.taobao.idlefish.search/1.0/"
APP_KEY = "12574478"


class XianyuScraper(BaseScraper):

    def __init__(self, cookie="", city="长春", max_pages=5, request_interval=5.0):
        super().__init__(request_interval=request_interval)
        self.cookie = cookie or os.environ.get("XIANYU_COOKIE", "")
        self.city = city
        self.max_pages = max_pages
        self.session = requests.Session()
        self._init_session()

    def _init_session(self):
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Referer": "https://www.goofish.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        if self.cookie:
            for pair in self.cookie.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    self.session.cookies.set(k.strip(), v.strip().strip('"'))

    def _get_token(self):
        m_h5_tk = self.session.cookies.get("m_h5_tk", "")
        if m_h5_tk:
            return m_h5_tk.split("_")[0]
        return ""

    def _generate_sign(self, t, data):
        token = self._get_token()
        raw = "{}&{}&{}&{}".format(token, t, APP_KEY, data)
        return hashlib.md5(raw.encode()).hexdigest()

    @property
    def source_name(self):
        return "xianyu"

    def fetch_listings(self, city=None):
        city = city or self.city
        keyword = "{} 租房".format(city)
        all_listings = []

        if not self.cookie:
            logger.warning("[闲鱼] 未配置Cookie，跳过闲鱼爬取")
            return []

        for page in range(1, self.max_pages + 1):
            logger.info("[闲鱼] 第%d页: 搜索 '%s'", page, keyword)
            try:
                listings = self._search_page(keyword, page)
                all_listings.extend(listings)
                logger.info("[闲鱼] 第%d页获取 %d 条", page, len(listings))
                if not listings:
                    break
            except Exception as e:
                logger.error("[闲鱼] 第%d页失败: %s", page, e)

            self._throttle()

        logger.info("[闲鱼] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _search_page(self, keyword, page):
        t = str(int(time.time() * 1000))
        data_str = json.dumps(
            {"keyword": keyword, "pageNumber": page, "searchFrom": "home"},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        sign = self._generate_sign(t, data_str)

        params = {
            "jsv": "2.7.2",
            "appKey": APP_KEY,
            "t": t,
            "sign": sign,
            "api": "mtop.taobao.idlefish.search",
            "v": "1.0",
            "type": "jsonp",
            "dataType": "jsonp",
            "callback": "mtopjsonp1",
            "data": data_str,
        }

        resp = self.session.get(SEARCH_API, params=params, timeout=30)
        resp.raise_for_status()

        match = re.search(r"mtopjsonp1\((.*)\)", resp.text, re.DOTALL)
        if not match:
            logger.warning("[闲鱼] 响应格式异常")
            return []

        body = json.loads(match.group(1))

        ret_code = body.get("ret", [""])[0] if body.get("ret") else ""
        if "SUCCESS" not in ret_code:
            logger.warning("[闲鱼] API返回错误: %s", ret_code)
            return []

        result_list = body.get("data", {}).get("resultList", [])
        if not result_list:
            return []

        listings = []
        for item in result_list:
            info = item.get("data", {})
            listing = self._parse_item(info)
            if listing:
                listings.append(listing)

        return listings

    def _parse_item(self, info):
        title = info.get("title", "").strip()
        if not title:
            return None

        price_str = info.get("price", "0")
        try:
            price = float(str(price_str).replace(",", ""))
        except (ValueError, TypeError):
            price = 0

        area = None
        area_str = info.get("area", "")
        if area_str:
            m = re.search(r"(\d+(?:\.\d+)?)", str(area_str))
            if m:
                area = float(m.group(1))

        desc = info.get("desc", "") or info.get("detailDesc", "")

        detail_url = info.get("url", "") or info.get("itemUrl", "")
        if not detail_url:
            item_id = info.get("id", "") or info.get("itemId", "")
            detail_url = "https://www.goofish.com/item/{}".format(item_id) if item_id else ""
        elif not detail_url.startswith("http"):
            detail_url = "https://www.goofish.com" + detail_url

        if not detail_url:
            return None

        pic_url = info.get("picUrl", "") or info.get("mainPic", "")
        if pic_url and not pic_url.startswith("http"):
            pic_url = "https:" + pic_url

        return HousingListing(
            listing_id=generate_listing_id(self.source_name, detail_url),
            source=self.source_name,
            title=title,
            price=price,
            area=area,
            url=detail_url,
            description=desc,
            images=[pic_url] if pic_url else [],
        )
