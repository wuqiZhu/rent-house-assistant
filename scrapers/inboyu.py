import logging
import re

from models import HousingListing
from scrapers.base import BaseScraper, generate_listing_id

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
            from playwright.sync_api import sync_playwright
            return self._fetch_with_playwright(url, city, existing_ids)
        except ImportError:
            logger.error("[泊寓] 未安装playwright，请运行: pip install playwright && playwright install chromium")
            return []
        except Exception as e:
            logger.error("[泊寓] %s 爬取失败: %s", city, e)
            return []

    def _fetch_with_playwright(self, url, city_name, existing_ids):
        from playwright.sync_api import sync_playwright

        listings = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                window.chrome = {runtime: {}};
            """)

            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector("a[href*='house-type/detail'], a[href*='detail']", timeout=15000)
                except Exception as e:
                    logger.warning("[泊寓] 等待房源列表超时，可能是被验证码拦截/数据为空，正在截图排查...")
                    try:
                        page.screenshot(path="inboyu_error.png")
                        logger.info("[泊寓] 错误现场已截图保存为 inboyu_error.png，请查看。")
                    except Exception:
                        pass
                page.wait_for_timeout(2000)

                html = page.content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                links = soup.select("a[href*='house-type/detail']")
                if not links:
                    links = soup.select("a[href*='detail']")
                    
                if links and len(links) > 0:
                    logger.info("[泊寓] 成功获取 %d 个候选连接节点...", len(links))

                for i, link in enumerate(links):
                    link_text = link.get_text(" ", strip=True)
                    logger.debug(f"[泊寓] 链接{i}: {link_text[:80]}")
                    listing = self._parse_link(link, city_name)
                    if listing:
                        if listing.listing_id in existing_ids:
                            continue
                        listings.append(listing)
                
                # 如果没抓到任何数据，截个图看看实际画面
                if len(listings) == 0:
                    logger.warning("[泊寓] 抓取总数为 0，截取一张 inboyu_zero.png 用于排查数据是否被隐藏")
                    try:
                        page.screenshot(path="inboyu_zero.png")
                    except:
                        pass

            except Exception as e:
                logger.error("[泊寓] Playwright 抓取失败: %s", e)
            finally:
                browser.close()

        logger.info("[泊寓] %s 获取 %d 条房源", city_name, len(listings))
        return listings

    def _parse_link(self, link, city_name):
        href = link.get("href", "")
        text = link.get_text(" ", strip=True)

        if not href or not text:
            return None

        if not href.startswith("http"):
            href = INBOYU_BASE + href

        logger.debug(f"[泊寓解析] 原始文本: {text}")

        title_match = re.search(r"(泊寓[^\d]*?店)", text)
        if not title_match:
            title_match = re.search(r"([^\d]+?)(?:\d+个户型)", text)
        if not title_match:
            title_match = re.search(r"([^\d]*?泊寓[^\d]*?)", text)
        title = title_match.group(1).strip() if title_match else text[:30]
        logger.debug(f"[泊寓解析] 标题: {title}")

        if not title or len(title) < 3:
            logger.warning(f"[泊寓解析] 标题过短，跳过")
            return None

        rooms_match = re.search(r"(\d+)个户型", text)
        rooms = rooms_match.group(1) if rooms_match else ""
        logger.debug(f"[泊寓解析] 户型数: {rooms}")

        address = ""
        addr_match = re.search(r"户型(.+?)(?:\d+\.?\d*\s*元)", text)
        if addr_match:
            address = addr_match.group(1).strip()
        logger.debug(f"[泊寓解析] 地址: {address}")

        price = 0.0
        price_match = re.search(r"(\d+(?:\.\d+)?)\s*元/月(?:起)?", text)
        if not price_match:
            price_match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*\d+(?:\.\d+)?\s*元/月", text)
        if price_match:
            price = float(price_match.group(1))
        logger.debug(f"[泊寓解析] 价格: {price}")

        area = None
        area_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|平米|m2|m\s*2)", text)
        if area_match:
            area = float(area_match.group(1))
        logger.debug(f"[泊寓解析] 面积: {area}")

        district = city_name
        if address:
            for d in ["朝阳区", "海淀区", "丰台区", "大兴区", "顺义区",
                      "通州区", "房山区", "门头沟区", "石景山区", "昌平区",
                      "平谷区", "怀柔区", "密云区", "延庆区", "东城区", "西城区",
                      "南关区", "宽城区", "二道区", "绿园区",
                       "净月区", "高新区", "经开区", "汽车区"]:
                if d in address:
                    district = d
                    break
        logger.debug(f"[泊寓解析] 区域: {district}")

        listing_id = generate_listing_id(self.source_name, href)

        logger.debug(f"[泊寓解析] 解析成功: {title} | {price}元 | {area}㎡ | {district}")

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
