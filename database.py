import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from models import HousingListing

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "rent_assistant.db"
DB_LOCK = threading.Lock()

CREATE_LISTINGS_SQL = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL,
    area REAL,
    rooms TEXT,
    floor TEXT,
    address TEXT,
    district TEXT,
    subway_station TEXT,
    url TEXT NOT NULL,
    description TEXT,
    images TEXT,
    publish_time TEXT,
    crawl_time TEXT,
    score REAL,
    is_notified INTEGER DEFAULT 0
)
"""

CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_score_notified ON listings(score, is_notified)",
    "CREATE INDEX IF NOT EXISTS idx_source ON listings(source)",
    "CREATE INDEX IF NOT EXISTS idx_crawl_time ON listings(crawl_time)",
]

ALLOWED_ORDER_BY = {
    "score DESC", "score ASC",
    "price DESC", "price ASC",
    "crawl_time DESC", "crawl_time ASC",
    "area DESC", "area ASC",
}


@contextmanager
def get_db(db_path=None):
    conn = sqlite3.connect(db_path or str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path=None):
    with get_db(db_path) as conn:
        conn.execute(CREATE_LISTINGS_SQL)
        for sql in CREATE_INDEX_SQL:
            conn.execute(sql)
        conn.commit()
    logger.info("数据库初始化完成: %s", db_path or DB_PATH)


def save_listing(conn, listing):
    conn.execute(
        """INSERT OR IGNORE INTO listings
        (id, source, title, price, area, rooms, floor, address, district,
         subway_station, url, description, images, publish_time, crawl_time, score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            listing.listing_id,
            listing.source,
            listing.title,
            listing.price,
            listing.area,
            listing.rooms,
            listing.floor,
            listing.address,
            listing.district,
            listing.subway_station,
            listing.url,
            listing.description,
            ",".join(listing.images),
            listing.publish_time.isoformat() if listing.publish_time else None,
            listing.crawl_time.isoformat(),
            listing.score,
        ),
    )


def save_listings(listings, db_path=None):
    with DB_LOCK:
        with get_db(db_path) as conn:
            before = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            for listing in listings:
                save_listing(conn, listing)
            conn.commit()
            after = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        return after - before


def get_unnotified_high_score(min_score=80, db_path=None):
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE score >= ? AND is_notified = 0 ORDER BY score DESC",
            (min_score,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_notified(listing_ids, db_path=None):
    with get_db(db_path) as conn:
        conn.executemany(
            "UPDATE listings SET is_notified = 1 WHERE id = ?",
            [(lid,) for lid in listing_ids],
        )
        conn.commit()


def get_all_listings(order_by="score DESC", db_path=None):
    if order_by not in ALLOWED_ORDER_BY:
        order_by = "score DESC"
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM listings ORDER BY {}".format(order_by)
        ).fetchall()
        return [dict(row) for row in rows]


def get_listing_count(db_path=None):
    with get_db(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM listings").fetchone()
        return row[0]


def get_all_ids(db_path=None):
    """获取数据库中所有房源ID，用于爬虫前置去重"""
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT id FROM listings").fetchall()
        return {row[0] for row in rows}


def cleanup_old_listings(days=30, db_path=None):
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM listings WHERE crawl_time < datetime('now', ?)",
            ("{} days".format(-days),),
        )
        conn.commit()
        deleted = cursor.rowcount
    if deleted > 0:
        logger.info("清理了 %d 条超过 %d 天的旧数据", deleted, days)
    return deleted
