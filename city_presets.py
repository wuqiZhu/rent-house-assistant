import logging

logger = logging.getLogger(__name__)

CITY_PRESETS = {
    "北京": {
        "douban_groups": [
            ("beijingzufang", "北京租房"),
            ("549574", "北京租房2"),
            ("596202", "北京租房3"),
        ],
        "inboyu": "北京",
        "baletoo": ["bj"],
        "fang": "bj",
    },
    "上海": {
        "douban_groups": [
            ("shanghaizufang", "上海租房"),
        ],
        "inboyu": "上海",
        "baletoo": ["sh"],
        "fang": "sh",
    },
    "广州": {
        "douban_groups": [
            ("gzrent", "广州租房"),
        ],
        "inboyu": "广州",
        "baletoo": ["gz"],
        "fang": "gz",
    },
    "深圳": {
        "douban_groups": [
            ("szzufang", "深圳租房"),
        ],
        "inboyu": "深圳",
        "baletoo": ["sz"],
        "fang": "sz",
    },
    "成都": {
        "douban_groups": [
            ("cdzufang", "成都租房"),
        ],
        "inboyu": "成都",
        "baletoo": ["cd"],
        "fang": "cd",
    },
    "杭州": {
        "douban_groups": [
            ("hzzufang", "杭州租房"),
        ],
        "inboyu": "杭州",
        "baletoo": ["hz"],
        "fang": "hz",
    },
    "南京": {
        "douban_groups": [
            ("njzufang", "南京租房"),
        ],
        "inboyu": "南京",
        "baletoo": ["nj"],
        "fang": "nj",
    },
    "武汉": {
        "douban_groups": [
            ("whzufang", "武汉租房"),
        ],
        "inboyu": "武汉",
        "baletoo": ["wh"],
        "fang": "wh",
    },
    "天津": {
        "douban_groups": [
            ("tianjinzufang", "天津租房"),
        ],
        "inboyu": "天津",
        "baletoo": ["tj"],
        "fang": "tj",
    },
    "重庆": {
        "douban_groups": [
            ("cqzufang", "重庆租房"),
        ],
        "inboyu": "重庆",
        "baletoo": ["cq"],
        "fang": "cq",
    },
    "长沙": {
        "douban_groups": [
            ("cszufang", "长沙租房"),
        ],
        "inboyu": "长沙",
        "baletoo": [],
        "fang": "cs",
    },
    "长春": {
        "douban_groups": [
            ("changchun", "长春豆瓣小组"),
        ],
        "inboyu": "长春",
        "baletoo": [],
        "fang": "changchun",
    },
    "厦门": {
        "douban_groups": [],
        "inboyu": "厦门",
        "baletoo": [],
        "fang": "xm",
    },
    "西安": {
        "douban_groups": [
            ("xianzufang", "西安租房"),
        ],
        "inboyu": "西安",
        "baletoo": ["xa"],
        "fang": "xa",
    },
    "郑州": {
        "douban_groups": [
            ("zhengzhouzufang", "郑州租房"),
        ],
        "inboyu": None,
        "baletoo": ["zz"],
        "fang": "zz",
    },
    "大连": {
        "douban_groups": [
            ("dalianzufang", "大连租房"),
        ],
        "inboyu": None,
        "baletoo": ["dl"],
        "fang": "dl",
    },
    "苏州": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": ["suzhou"],
        "fang": None,
    },
    "沈阳": {
        "douban_groups": [
            ("shenyangzufang", "沈阳租房"),
        ],
        "inboyu": None,
        "baletoo": [],
        "fang": "sy",
    },
    "哈尔滨": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "heb",
    },
    "济南": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "jn",
    },
    "青岛": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "qd",
    },
    "昆明": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "km",
    },
    "贵阳": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "gy",
    },
    "合肥": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "hf",
    },
    "福州": {
        "douban_groups": [],
        "inboyu": None,
        "baletoo": [],
        "fang": "fz",
    },
    "佛山": {
        "douban_groups": [],
        "inboyu": "佛山",
        "baletoo": [],
        "fang": None,
    },
}


def apply_city_preset(cfg):
    city = cfg.get("city", "")
    if not city or city not in CITY_PRESETS:
        if city:
            logger.warning("城市 '%s' 不在预设列表中，使用配置文件中的手动设置", city)
            logger.warning("可用城市: %s", ", ".join(CITY_PRESETS.keys()))
        return cfg

    preset = CITY_PRESETS[city]
    scrapers = cfg.setdefault("scrapers", {})
    enabled_count = 0

    if preset["douban_groups"]:
        db = scrapers.setdefault("douban", {})
        db["groups"] = preset["douban_groups"]
        if db.get("enabled", True):
            enabled_count += 1
        logger.info("[城市预设] 豆瓣小组 → %d 个小组", len(preset["douban_groups"]))
    else:
        if scrapers.get("douban", {}).get("enabled"):
            scrapers["douban"]["enabled"] = False
            logger.info("[城市预设] 豆瓣 → %s 暂无租房小组，已自动关闭", city)

    if preset["inboyu"]:
        ib = scrapers.setdefault("inboyu", {})
        ib["city"] = preset["inboyu"]
        if ib.get("enabled", True):
            enabled_count += 1
        logger.info("[城市预设] 泊寓 → %s", preset["inboyu"])
    else:
        if scrapers.get("inboyu", {}).get("enabled"):
            scrapers["inboyu"]["enabled"] = False
            logger.info("[城市预设] 泊寓 → %s 暂无门店，已自动关闭", city)

    if preset["baletoo"]:
        bt = scrapers.setdefault("baletoo", {})
        bt["cities"] = preset["baletoo"]
        if bt.get("enabled", True):
            enabled_count += 1
        logger.info("[城市预设] 巴乐兔 → %s", ",".join(preset["baletoo"]))
    else:
        if scrapers.get("baletoo", {}).get("enabled"):
            scrapers["baletoo"]["enabled"] = False
            logger.info("[城市预设] 巴乐兔 → %s 暂无数据，已自动关闭", city)

    if preset["fang"]:
        fg = scrapers.setdefault("fang", {})
        fg["city"] = city
        if fg.get("enabled", True):
            enabled_count += 1
        logger.info("[城市预设] 房天下 → %s", preset["fang"])
    else:
        if scrapers.get("fang", {}).get("enabled"):
            scrapers["fang"]["enabled"] = False
            logger.info("[城市预设] 房天下 → %s 暂无数据，已自动关闭", city)

    logger.info("[城市预设] %s: %d 个爬虫已启用", city, enabled_count)
    return cfg


def list_supported_cities():
    result = {}
    for city, preset in CITY_PRESETS.items():
        platforms = []
        if preset["douban_groups"]:
            platforms.append("豆瓣")
        if preset["inboyu"]:
            platforms.append("泊寓")
        if preset["baletoo"]:
            platforms.append("巴乐兔")
        if preset["fang"]:
            platforms.append("房天下")
        if platforms:
            result[city] = platforms
    return result
