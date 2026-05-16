import logging
import os
import sys
from pathlib import Path

import yaml

from database import get_listing_count, init_db, save_listings, get_unnotified_high_score, mark_notified
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


def run_scrapers(cfg):
    from scrapers.lianjia import LianjiaScraper
    from scrapers.beike import BeikeScraper
    from scrapers.douban import DoubanScraper

    all_listings = []
    scraper_cfg = cfg.get("scrapers", {})

    if scraper_cfg.get("lianjia", {}).get("enabled", False):
        lj_cfg = scraper_cfg["lianjia"]
        scraper = LianjiaScraper(
            request_interval=lj_cfg.get("request_interval", 5.0),
            max_pages=lj_cfg.get("max_pages", 3),
        )
        listings = scraper.fetch_listings(city=lj_cfg.get("city", "beijing"))
        all_listings.extend(listings)

    if scraper_cfg.get("beike", {}).get("enabled", False):
        bk_cfg = scraper_cfg["beike"]
        scraper = BeikeScraper(
            request_interval=bk_cfg.get("request_interval", 5.0),
            max_pages=bk_cfg.get("max_pages", 3),
        )
        listings = scraper.fetch_listings(city=bk_cfg.get("city", "beijing"))
        all_listings.extend(listings)

    if scraper_cfg.get("douban", {}).get("enabled", False):
        db_cfg = scraper_cfg["douban"]
        cookie = os.environ.get("DOUBAN_COOKIE") or db_cfg.get("cookie", "")
        scraper = DoubanScraper(
            groups=[tuple(g) for g in db_cfg.get("groups", [])],
            cookie=cookie,
            max_pages=db_cfg.get("max_pages", 3),
            exclude_keywords=db_cfg.get("exclude_keywords", ["求租"]),
            include_keywords=db_cfg.get("include_keywords", []),
        )
        listings = scraper.fetch_listings()
        all_listings.extend(listings)

    return all_listings


def main():
    logger.info("=" * 60)
    logger.info("租房助手 - 第四轮：定时运行 + 钉钉推送")
    logger.info("=" * 60)

    cfg = load_config()
    prefs = build_preferences(cfg)
    init_db()

    existing_count = get_listing_count()
    logger.info("数据库已有 %d 条房源", existing_count)
    logger.info("当前偏好: 预算 %d-%d元 | 区域 %s | 工作站: %s",
                prefs.budget_min, prefs.budget_max,
                ",".join(prefs.preferred_districts) or "不限",
                prefs.workplace_station or "未设置")

    logger.info("")
    logger.info("Step 1: 抓取房源数据...")
    all_listings = run_scrapers(cfg)
    logger.info("共抓取 %d 条房源", len(all_listings))

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
            f"{listing.score:.1f}" if listing.score else "?",
            listing.title[:45],
        )
        logger.info(
            "       %s元/月 | %s㎡ | %s | %s",
            f"{listing.price:.0f}" if listing.price else "?",
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


if __name__ == "__main__":
    main()
