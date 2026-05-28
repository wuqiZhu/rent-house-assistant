import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "rent_assistant.db"


def view_listings(order_by="score DESC", limit=30, min_price=0, max_price=99999):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    query = """
        SELECT * FROM listings 
        WHERE price > 0 AND price >= ? AND price <= ?
        ORDER BY {}
        LIMIT ?
    """.format(order_by)

    rows = conn.execute(query, (min_price, max_price, limit)).fetchall()
    conn.close()

    if not rows:
        print("没有找到符合条件的房源")
        return

    print("=" * 80)
    print("  租房助手 - 房源列表")
    print("=" * 80)
    print()

    for i, row in enumerate(rows, 1):
        score = row["score"] if row["score"] else 0
        price = row["price"] if row["price"] else 0
        area = row["area"] if row["area"] else "?"
        title = row["title"][:40] if row["title"] else ""
        district = row["district"] if row["district"] else "-"
        source = row["source"] if row["source"] else "?"
        url = row["url"] if row["url"] else ""

        print("#{} [{}分] {} | {}元/月 | {}㎡ | {} | {}".format(
            i, score, title, price, area, district, source
        ))
        if url:
            print("   链接: {}".format(url))
        print()

    print("=" * 80)
    print("共 {} 条房源".format(len(rows)))
    print("=" * 80)


def main():
    order_by = "score DESC"
    limit = 30
    min_price = 0
    max_price = 99999

    for arg in sys.argv[1:]:
        if arg.startswith("--sort="):
            sort_field = arg.split("=")[1]
            if sort_field in ["score", "price", "area", "crawl_time"]:
                order_by = "{} DESC".format(sort_field)
        elif arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        elif arg.startswith("--min-price="):
            min_price = float(arg.split("=")[1])
        elif arg.startswith("--max-price="):
            max_price = float(arg.split("=")[1])
        elif arg == "--help":
            print("用法: python view_listings.py [选项]")
            print()
            print("选项:")
            print("  --sort=字段      排序字段: score/price/area/crawl_time (默认: score)")
            print("  --limit=数量     显示数量 (默认: 30)")
            print("  --min-price=金额 最低价格 (默认: 0)")
            print("  --max-price=金额 最高价格 (默认: 99999)")
            print("  --help           显示帮助")
            print()
            print("示例:")
            print("  python view_listings.py                     # 按评分排序，显示30条")
            print("  python view_listings.py --sort=price        # 按价格从低到高")
            print("  python view_listings.py --max-price=1000    # 只看1000元以下")
            print("  python view_listings.py --limit=50          # 显示50条")
            return

    view_listings(order_by, limit, min_price, max_price)


if __name__ == "__main__":
    main()
