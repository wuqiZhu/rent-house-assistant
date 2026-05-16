import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from models import HousingListing

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "rent_assistant.db"

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
        conn.commit()
    logger.info("数据库初始化完成: %s", db_path or DB_PATH)


def save_listing(conn, listing):
    existing = conn.execute(
        "SELECT id FROM listings WHERE id = ?", (listing.listing_id,)
    ).fetchone()

    if existing:
        return False

    conn.execute(
        """INSERT INTO listings
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
    return True


def save_listings(listings, db_path=None):
    new_count = 0
    with get_db(db_path) as conn:
        for listing in listings:
            if save_listing(conn, listing):
                new_count += 1
        conn.commit()
    return new_count


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
    with get_db(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM listings ORDER BY {order_by}"
        ).fetchall()
        return [dict(row) for row in rows]


def get_listing_count(db_path=None):
    with get_db(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM listings").fetchone()
        return row[0]
