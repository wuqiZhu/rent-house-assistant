import logging
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_venv_lib = Path(__file__).parent / "venv_lib"
if _venv_lib.exists() and str(_venv_lib) not in sys.path:
    sys.path.insert(0, str(_venv_lib))

import yaml

from city_presets import apply_city_preset, list_supported_cities
from database import get_listing_count, init_db, save_listings, get_unnotified_high_score, mark_notified, cleanup_old_listings, get_all_ids
from models import UserPreferences
from notifier import send_dingtalk
from scoring import score_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_preferences(cfg):
    p = cfg.get("preferences", {})
    return UserPreferences(
        budget_min=p.get("budget_min", 0),
        budget_max=p.get("budget_max", 5000),
        area_min=p.get("area_min", 20),
        area_max=p.get("area_max", 100),
        preferred_districts=p.get("preferred_districts", []),
        preferred_subway_stations=p.get("preferred_subway_stations", []),
        max_commute_minutes=p.get("max_commute_minutes", 60),
        workplace_station=p.get("workplace_station"),
        required_facilities=p.get("required_facilities", []),
        preferred_rooms=p.get("preferred_rooms", []),
    )


def run_scrapers(cfg, existing_ids=None, prefs=None):
    if existing_ids is None:
        existing_ids = set()

    import concurrent.futures
    from scrapers.douban import DoubanScraper
    from scrapers.inboyu import InboyuScraper
    from scrapers.baletoo import BaletooScraper
    from scrapers.fang import FangScraper

    all_listings = []
    scraper_cfg = cfg.get("scrapers", {})

    def run_douban():
        if not scraper_cfg.get("douban", {}).get("enabled", False): return []
        db_cfg = scraper_cfg["douban"]
        try:
            cookie = os.environ.get("DOUBAN_COOKIE") or db_cfg.get("cookie", "")
            scraper = DoubanScraper(
                groups=[tuple(g) for g in db_cfg.get("groups", [])],
                cookie=cookie,
                max_pages=db_cfg.get("max_pages", 3),
                exclude_keywords=db_cfg.get("exclude_keywords", ["求租"]),
                include_keywords=db_cfg.get("include_keywords", []),
                prefs=prefs,
            )
            return scraper.fetch_listings(existing_ids=existing_ids)
        except Exception as e:
            logger.error("豆瓣爬虫异常: %s", e)
            return []

    def run_inboyu():
        if not scraper_cfg.get("inboyu", {}).get("enabled", False): return []
        ib_cfg = scraper_cfg["inboyu"]
        try:
            scraper = InboyuScraper(
                city=ib_cfg.get("city", "长春"),
                request_interval=ib_cfg.get("request_interval", 3.0),
            )
            return scraper.fetch_listings(existing_ids=existing_ids)
        except Exception as e:
            logger.error("泊寓爬虫异常: %s", e)
            return []

    def run_baletoo():
        if not scraper_cfg.get("baletoo", {}).get("enabled", False): return []
        bt_cfg = scraper_cfg["baletoo"]
        try:
            scraper = BaletooScraper(
                cities=bt_cfg.get("cities", ["bj"]),
                request_interval=bt_cfg.get("request_interval", 3.0),
            )
            return scraper.fetch_listings(existing_ids=existing_ids)
        except Exception as e:
            logger.error("巴乐兔爬虫异常: %s", e)
            return []

    def run_fang():
        if not scraper_cfg.get("fang", {}).get("enabled", False): return []
        fg_cfg = scraper_cfg["fang"]
        try:
            scraper = FangScraper(
                city=fg_cfg.get("city", "长春"),
                max_pages=fg_cfg.get("max_pages", 3),
                request_interval=fg_cfg.get("request_interval", 5.0),
            )
            return scraper.fetch_listings(existing_ids=existing_ids)
        except Exception as e:
            logger.error("房天下爬虫异常: %s", e)
            return []

    tasks = [run_douban, run_inboyu, run_baletoo, run_fang]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(task) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            try:
                listings = future.result()
                if listings:
                    all_listings.extend(listings)
            except Exception as e:
                logger.error("爬虫执行线程异常: %s", e)

    return all_listings


def main():
    logger.info("=" * 60)
    logger.info("租房助手启动")
    logger.info("=" * 60)

    try:
        cfg = load_config()
        cfg = apply_city_preset(cfg)
        prefs = build_preferences(cfg)
        init_db()

        cleanup_old_listings(days=30)

        existing_count = get_listing_count()
        city = cfg.get("city", "未设置")
        logger.info("数据库已有 %d 条房源 | 当前城市: %s", existing_count, city)
        logger.info("当前偏好: 预算 %d-%d元 | 区域 %s | 工作站: %s",
                    prefs.budget_min, prefs.budget_max,
                    ",".join(prefs.preferred_districts) or "不限",
                    prefs.workplace_station or "未设置")

        logger.info("")
        logger.info("Step 1: 抓取房源数据 (并发模式)...")
        existing_ids = get_all_ids()
        logger.info("已加载 %d 条已有房源 ID 到内存布隆池用于急速去重", len(existing_ids))
        all_listings = run_scrapers(cfg, existing_ids=existing_ids, prefs=prefs)
        logger.info("共抓取 %d 条新房源", len(all_listings))

        if not all_listings:
            logger.warning("未抓取到任何房源")
            return

        logger.info("")
        logger.info("Step 2: 评分排序...")
        scored = score_all(all_listings, prefs)

        logger.info("")
        logger.info("Step 3: 入库去重...")
        new_count = save_listings(scored)
        logger.info("新增 %d 条房源入库（跳过 %d 条已存在）", new_count, len(scored) - new_count)

        source_counts = {}
        for l in scored:
            source_counts[l.source] = source_counts.get(l.source, 0) + 1
        logger.info("数据来源: %s", " | ".join("{}: {}条".format(k, v) for k, v in source_counts.items()))

        logger.info("")
        logger.info("=" * 60)
        logger.info("本次抓取结果（按评分排序）")
        logger.info("=" * 60)
        for i, listing in enumerate(scored[:15], 1):
            logger.info(
                "  #%d  [%s分] %s",
                i,
                "{:.1f}".format(listing.score) if listing.score else "?",
                listing.title[:45],
            )
            logger.info(
                "       %s元/月 | %s㎡ | %s | %s",
                "{:.0f}".format(listing.price) if listing.price else "?",
                listing.area or "?",
                listing.rooms or "-",
                listing.district or "-",
            )

        min_score = cfg.get("scoring", {}).get("min_score_to_notify", 80)
        high_score = get_unnotified_high_score(min_score=min_score)
        logger.info("")
        logger.info("--- 高分房源（>=%d分，未通知）: %d 条 ---", min_score, len(high_score))
        for item in high_score[:5]:
            logger.info("  [%s分] %s | %s元/月", item["score"], item["title"][:40], item["price"])

        if high_score:
            logger.info("")
            logger.info("Step 4: 发送钉钉通知...")
            notif_cfg = cfg.get("notification", {})
            webhook = os.environ.get("DINGTALK_WEBHOOK") or notif_cfg.get("dingtalk_webhook", "")
            secret = os.environ.get("DINGTALK_SECRET") or notif_cfg.get("dingtalk_secret", "")
            if webhook:
                success = send_dingtalk(webhook, high_score, secret=secret)
                if success:
                    mark_notified([item["id"] for item in high_score])
                    logger.info("已标记 %d 条为已通知", len(high_score))
            else:
                logger.warning("未配置钉钉Webhook，跳过通知")

        total = get_listing_count()
        logger.info("")
        logger.info("=" * 60)
        logger.info("运行完成！数据库共 %d 条房源", total)
        logger.info("=" * 60)

    except Exception as e:
        logger.error("运行异常: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
