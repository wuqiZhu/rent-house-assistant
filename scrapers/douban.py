import logging
import os
import re
import yaml
from pathlib import Path

from models import HousingListing
from scrapers.base import BaseScraper, generate_listing_id
from notifier import upload_image_to_smms, send_dingtalk_raw_markdown

logger = logging.getLogger(__name__)

DEFAULT_GROUPS = [
    ("beijingzufang", "北京租房"),
    ("549574", "北京租房2"),
    ("596202", "北京租房3"),
    ("26926", "北京租房豆瓣"),
    ("hdzufang", "北京海淀租房"),
]


class DoubanScraper(BaseScraper):

    def __init__(
        self,
        groups=None,
        cookie="",
        max_pages=10,
        exclude_keywords=None,
        include_keywords=None,
        request_interval=6.0,
        max_detail_fetches=50,
        prefs=None,
    ):
        super().__init__(request_interval=request_interval)
        self.groups = groups or DEFAULT_GROUPS
        self.cookie = cookie or os.environ.get("DOUBAN_COOKIE", "")
        self.max_pages = max_pages
        self.exclude_keywords = exclude_keywords or ["求租", "合租找室友"]
        self.include_keywords = include_keywords or []
        self.max_detail_fetches = max_detail_fetches
        self._detail_fetch_count = 0
        self.prefs = prefs

    @property
    def source_name(self):
        return "douban"

    def fetch_listings(self, city=None, existing_ids=None):
        if existing_ids is None:
            existing_ids = set()

        if not self.cookie:
            logger.warning("[豆瓣] 未配置Cookie，跳过豆瓣爬取。请设置 DOUBAN_COOKIE 环境变量")
            return []

        self._detail_fetch_count = 0
        all_listings = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[豆瓣] 未安装playwright，请运行: pip install playwright && playwright install chromium")
            return []

        cookie_list = self._parse_cookie_to_list()

        pw = None
        browser = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN",
                viewport={"width": 1920, "height": 1080},
            )
            context.add_cookies(cookie_list)
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)

            for group_id, group_name in self.groups:
                logger.info("[豆瓣] 开始爬取小组: %s (%s)", group_name, group_id)
                try:
                    listings = self._crawl_group_pw(page, group_id, group_name, existing_ids)
                    all_listings.extend(listings)
                    logger.info("[豆瓣] %s 获取 %d 条", group_name, len(listings))
                except Exception as e:
                    logger.error("[豆瓣] %s 爬取失败: %s", group_name, e)

        except Exception as e:
            logger.error("[豆瓣] Playwright异常: %s", e)
        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass

        logger.info("[豆瓣] 共获取 %d 条房源", len(all_listings))
        return all_listings

    def _parse_cookie_to_list(self):
        cookie_list = []
        if not self.cookie:
            return cookie_list
        for pair in self.cookie.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookie_list.append({
                    "name": k.strip(),
                    "value": v.strip().strip('"'),
                    "domain": ".douban.com",
                    "path": "/",
                })
        return cookie_list

    def _crawl_group_pw(self, page, group_id, group_name, existing_ids):
        from bs4 import BeautifulSoup

        listings = []
        for page_num in range(self.max_pages):
            start = page_num * 25
            url = "https://www.douban.com/group/{}/discussion?start={}&type=new".format(
                group_id, start
            )
            logger.info("[豆瓣] %s 第%d页", group_name, page_num + 1)

            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                final_url = page.url
                if "sec.douban.com" in final_url or "login" in final_url:
                    logger.warning("[豆瓣] %s Cookie已过期，触发自动续期流程", group_name)
                    self._handle_cookie_renewal(page)
                    # 重新刷新当前页尝试
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    html = page.content()
                else:
                    html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                table = soup.select_one("table.olt")
                if not table:
                    # 有些豆瓣新版页面或者被封控会导致没有 table.olt，尝试新的排版或留底排查
                    logger.warning("[豆瓣] %s 未找到帖子列表 (table.olt)，可能是排版更新或者需要权限", group_name)
                    try:
                        page.screenshot(path=f"douban_error_{group_id}.png")
                    except:
                        pass
                    break

                rows = table.select("tr")[1:]
                if not rows:
                    break

                found_any = False
                for row in rows:
                    title_el = row.select_one("td.title a")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    link = title_el.get("href", "")

                    if not self._pass_filter(title):
                        continue
                        
                    # 前置去重校验
                    listing_id = generate_listing_id(self.source_name, link)
                    if listing_id in existing_ids:
                        continue

                    # Fallback deep fetch content if price or area is missing from title
                    price = self._extract_price(title)
                    area = self._extract_area(title)
                    rooms = self._extract_rooms(title)
                    
                    # 前置初筛判定：若缺价格/面积等，是否值得进入详情页深挖？
                    should_deep_fetch = False
                    if (not price or not area or not rooms) and self._detail_fetch_count < self.max_detail_fetches:
                        if self.prefs:
                            # 预打分
                            dummy_listing = HousingListing(
                                listing_id=listing_id, source=self.source_name, title=title, 
                                price=1, area=1, url=link, district="", address=""
                            )
                            from scoring import _score_location, _score_quiet, WEIGHT_LOCATION
                            loc_score = _score_location(dummy_listing, self.prefs)
                            quiet_score = _score_quiet(dummy_listing)
                            
                            # 如果地理位置命中了偏好 (loc_score > 默认低分) 或者有极好的关键字，才深挖
                            if loc_score > WEIGHT_LOCATION * 0.6 or quiet_score > 0:
                                should_deep_fetch = True
                            else:
                                logger.info(f"[豆瓣] 跳过详情页深挖(初筛落选): {title[:15]}...")
                        else:
                            # 没有提供偏好则直接判定可以深挖
                            should_deep_fetch = True

                    desc_text = ""
                    if should_deep_fetch:
                        self._detail_fetch_count += 1
                        logger.info(f"[豆瓣] 标题缺信息，初筛命中，进入详情页({self._detail_fetch_count}/{self.max_detail_fetches}): {title[:15]}...")
                        try:
                            # 详情页防频繁请求风控，进入详情之后稍作等待然后退回/不退回直接新建tab也可以，但新建更稳
                            detail_page = page.context.new_page()
                            detail_page.goto(link, timeout=20000, wait_until="domcontentloaded")
                            detail_page.wait_for_timeout(2000)
                            
                            content_el = detail_page.locator("#link-report .topic-content")
                            if content_el.count() > 0:
                                desc_text = content_el.inner_text()
                                
                                # 在正文中再次寻找
                                if not price:
                                    price = self._extract_price(desc_text)
                                if not area:
                                    area = self._extract_area(desc_text)
                                if not rooms:
                                    rooms = self._extract_rooms(desc_text)
                            
                            detail_page.close()
                        except Exception as e:
                            logger.error(f"[豆瓣] 爬取详情页失败: {e}")
                            try:
                                detail_page.close()
                            except:
                                pass

                    listing = HousingListing(
                        listing_id=listing_id,
                        source=self.source_name,
                        title=title,
                        price=price if price else 0,
                        area=area,
                        rooms=rooms,
                        url=link,
                        description=desc_text[:200] if desc_text else None
                    )
                    listings.append(listing)
                    found_any = True

                if not found_any and page_num > 0:
                    break

            except Exception as e:
                logger.error("[豆瓣] %s 第%d页失败: %s", group_name, page_num + 1, e)

            self._throttle()

        return listings

    def _handle_cookie_renewal(self, page):
        """自动续约 Cookie 的交互式修复流程"""
        try:
            # 找到二维码元素
            qr_element = page.locator(".qcode-img")
            if qr_element.count() == 0:
                 # 可能处于普通账号密码输入页面，尝试切换到扫码页面(如果需要的话，或者报错退出)
                 logger.error("[豆瓣] 未在登录页面找到二维码元素")
                 return
            
            qr_path = "douban_qr.png"
            qr_element.screenshot(path=qr_path)
            logger.info("[豆瓣] 已生成登录二维码图片: %s", qr_path)
            
            # 借助 SM.MS 等 API 转换为公开 URL
            qr_url = upload_image_to_smms(qr_path)
            if qr_url:
                text = f"### ⚠️ 豆瓣 Cookie 已过期\n\n请在 **3 分钟内** 打开豆瓣 App 扫码登录续期:\n\n![二维码]({qr_url})"
                send_dingtalk_raw_markdown(text)
            else:
                logger.error("[豆瓣] 无法上传二维码到图床")
                return

            logger.info("[豆瓣] 正在等待扫码 (最长3分钟)...")
            import time
            wait_time = 0
            timeout = 180
            while wait_time < timeout:
                page.wait_for_timeout(3000)
                wait_time += 3
                # 检查URL是否已经跳离登录页
                if "sec.douban.com" not in page.url and "login" not in page.url and "accounts.douban.com" not in page.url:
                    logger.info("[豆瓣] 🎉 扫码成功！正在提取新 Cookie...")
                    # 扫码成功后，豆瓣会通过 JS 重定向回主页面，拿到新的 cookies
                    new_cookies = page.context.cookies()
                    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in new_cookies])
                    self.cookie = cookie_str
                    self._update_cookie_in_config(cookie_str)
                    return
            
            logger.error("[豆瓣] 扫码超时")
            
        except Exception as e:
            logger.error("[豆瓣] 自动续期出错: %s", e)

    def _update_cookie_in_config(self, cookie_str):
        """将新获取的Cookie回写到config.yaml"""
        config_path = Path(__file__).parent.parent / "config.yaml"
        if not config_path.exists():
            return
            
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                
            if "scrapers" in data and "douban" in data["scrapers"]:
                data["scrapers"]["douban"]["cookie"] = cookie_str
                
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
                
            logger.info("[豆瓣] 配置文件已更新新 Cookie")
        except Exception as e:
            logger.error("[豆瓣] 回写 config.yaml 失败: %s", e)

    def _pass_filter(self, title):
        for kw in self.exclude_keywords:
            if kw in title:
                return False
        if self.include_keywords:
            return any(kw in title for kw in self.include_keywords)
        return True

    @staticmethod
    def _extract_price(title):
        patterns = [
            r"(\d+)\s*元/月",
            r"(\d+)\s*元",
            r"租金[：:]?\s*(\d+)",
            r"(\d{3,5})\s*(?:块|元)",
        ]
        for pat in patterns:
            m = re.search(pat, title)
            if m:
                val = float(m.group(1))
                if 300 <= val <= 50000:
                    return val

        numbers = re.findall(r"\b(\d{3,5})\b", title)
        for n in numbers:
            val = int(n)
            if 500 <= val <= 20000:
                return float(val)
        return None

    @staticmethod
    def _extract_area(title):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|平|平米|平方)", title)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_rooms(title):
        m = re.search(r"([1-9一二三四五六七八九]室[0-9零一二三四五六七八九]厅|[1-9一二三四五六七八九]居室)", title)
        return m.group(1) if m else None
