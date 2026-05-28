import logging
import os
import sys
import time
import traceback
from datetime import datetime
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
from notifier import send_dingtalk, send_dingtalk_raw_markdown
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


def send_alert_async(message):
    """发送钉钉警报（异步封装，避免阻塞主流程）"""
    try:
        send_dingtalk_raw_markdown(message)
    except Exception as e:
        logger.error("发送警报失败: %s", e)


def send_alert(title, content, emoji="⚠️"):
    """发送钉钉警报"""
    markdown_text = f"### {emoji} {title}\n\n{content}\n\n> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    send_alert_async(markdown_text)


def send_daily_summary(total_scraped, new_added, high_score_count):
    """发送每日摘要"""
    content = f"""
- 今日探测房源: **{total_scraped}** 套
- 新增入库: **{new_added}** 套
- 高分房源: **{high_score_count}** 套
    """.strip()
    send_alert("今日任务汇报", content, emoji="📊")


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
        if not scraper_cfg.get("douban", {}).get("enabled", False):
            return []
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
        if not scraper_cfg.get("inboyu", {}).get("enabled", False):
            return []
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
        if not scraper_cfg.get("baletoo", {}).get("enabled", False):
            return []
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
        if not scraper_cfg.get("fang", {}).get("enabled", False):
            return []
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


def execute_once(cfg, send_summary_if_needed=True):
    """执行一次完整的抓取流程"""
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("租房助手启动")
    logger.info("=" * 60)

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
    total_scraped = len(all_listings)
    logger.info("共抓取 %d 条新房源", total_scraped)

    new_added = 0
    high_score_count = 0

    if all_listings:
        logger.info("")
        logger.info("Step 2: 评分排序...")
        scored = score_all(all_listings, prefs)

        logger.info("")
        logger.info("Step 3: 入库去重...")
        new_added = save_listings(scored)
        logger.info("新增 %d 条房源入库（跳过 %d 条已存在）", new_added, len(scored) - new_added)

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
        high_score_count = len(high_score)
        logger.info("")
        logger.info("--- 高分房源（>=%d分，未通知）: %d 条 ---", min_score, high_score_count)
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
                    logger.info("已标记 %d 条为已通知", high_score_count)
            else:
                logger.warning("未配置钉钉Webhook，跳过通知")

    total = get_listing_count()
    logger.info("")
    logger.info("=" * 60)
    logger.info("运行完成！数据库共 %d 条房源", total)
    logger.info("耗时 %.1f 秒", time.time() - start_time)
    logger.info("=" * 60)

    # 判断是否需要发送每日摘要
    if send_summary_if_needed:
        now = datetime.now()
        # 如果是 20:00~20:10 之间，发送每日摘要
        if now.hour == 20 and now.minute <= 10:
            logger.info("触发每日摘要发送...")
            send_daily_summary(total_scraped, new_added, high_score_count)

    return total_scraped, new_added, high_score_count


def run_scheduled_mode(cfg):
    """定时任务模式"""
    try:
        import schedule
    except ImportError:
        logger.error("未安装 schedule 库，请运行: pip install schedule")
        sys.exit(1)

    sched_cfg = cfg.get("schedule", {})
    morning_hour = sched_cfg.get("morning_hour", 8)
    evening_hour = sched_cfg.get("evening_hour", 20)
    check_interval = sched_cfg.get("check_interval_seconds", 60)

    logger.info("=" * 60)
    logger.info("定时任务模式已启动")
    logger.info(f"早上 {morning_hour:02d}:00 执行一次")
    logger.info(f"晚上 {evening_hour:02d}:00 执行一次")
    logger.info(f"检查间隔: {check_interval} 秒")
    logger.info("=" * 60)

    def job_wrapper():
        try:
            execute_once(cfg, send_summary_if_needed=True)
        except Exception as e:
            logger.error("定时任务执行异常: %s", e, exc_info=True)
            send_alert(
                "任务运行崩溃",
                f"异常信息: {str(e)}",
                emoji="🚨"
            )

    # 注册定时任务
    schedule.every().day.at(f"{morning_hour:02d}:00").do(job_wrapper)
    schedule.every().day.at(f"{evening_hour:02d}:00").do(job_wrapper)

    # 主循环
    while True:
        try:
            schedule.run_pending()
            time.sleep(check_interval)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")
            break
        except Exception as e:
            logger.error("主循环异常: %s", e, exc_info=True)
            send_alert(
                "守护进程异常",
                f"异常信息: {str(e)}",
                emoji="🚨"
            )
            time.sleep(10)


def main():
    try:
        cfg = load_config()
    except Exception as e:
        logger.error("配置文件加载失败: %s", e, exc_info=True)
        send_alert(
            "配置文件加载失败",
            f"请检查 config.yaml 文件是否存在且格式正确\n异常: {str(e)}",
            emoji="🚨"
        )
        sys.exit(1)

    # 判断是否使用定时模式
    use_schedule = cfg.get("schedule", {}).get("enabled", False)

    try:
        if use_schedule:
            run_scheduled_mode(cfg)
        else:
            execute_once(cfg, send_summary_if_needed=True)
    except Exception as e:
        logger.error("程序运行崩溃: %s", e, exc_info=True)
        error_detail = traceback.format_exc()
        send_alert(
            "租房助手运行崩溃",
            f"异常信息:\n```\n{error_detail}\n```",
            emoji="🚨"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
