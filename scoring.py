import logging

from models import HousingListing, UserPreferences

logger = logging.getLogger(__name__)

WEIGHT_PRICE = 30
WEIGHT_AREA = 15
WEIGHT_LOCATION = 20
WEIGHT_COMMUTE = 15
WEIGHT_FACILITIES = 10
WEIGHT_QUIET = 10

QUIET_KEYWORDS = [
    "安静", "低噪", "不临街", "远离马路", "小区内", "独栋",
    "隔音", "隔音好", "噪音小", "噪声小", "环境安静",
    "不吵", "清静", "远离高速", "远离铁路", "中间楼层",
]

DEAL_KEYWORDS = [
    "优惠", "特价", "降价", "性价比", "便宜", "低价",
    "急租", "甩租", "亏本", "补贴", "免中介费", "无中介",
]


def score_listing(listing, prefs):
    total = 0.0
    total += _score_price(listing.price, prefs)
    total += _score_area(listing.area, prefs)
    total += _score_location(listing, prefs)
    total += _score_commute(listing, prefs)
    total += _score_facilities(listing, prefs)
    total += _score_quiet(listing)
    return round(min(total, 100), 1)


def _score_price(price, prefs):
    if price <= 0:
        return 0

    budget_min = prefs.budget_min
    budget_max = prefs.budget_max

    if price <= budget_min:
        return WEIGHT_PRICE

    if price <= budget_max:
        ratio = (price - budget_min) / (budget_max - budget_min + 1)
        return WEIGHT_PRICE * (1 - ratio * 0.4)

    over_ratio = (price - budget_max) / budget_max
    if over_ratio <= 0.1:
        return WEIGHT_PRICE * 0.5
    if over_ratio <= 0.3:
        return WEIGHT_PRICE * 0.25
    return max(0, WEIGHT_PRICE * 0.1)


def _score_area(area, prefs):
    if area is None or area <= 0:
        return WEIGHT_AREA * 0.25

    if prefs.area_min <= area <= prefs.area_max:
        mid = (prefs.area_min + prefs.area_max) / 2
        distance = abs(area - mid) / (prefs.area_max - prefs.area_min + 1) * 2
        return WEIGHT_AREA * (1 - distance * 0.2)

    if area < prefs.area_min:
        ratio = area / prefs.area_min
        return WEIGHT_AREA * ratio * 0.7

    over_ratio = (area - prefs.area_max) / prefs.area_max
    if over_ratio <= 0.5:
        return WEIGHT_AREA * 0.8
    return WEIGHT_AREA * 0.6


def _score_location(listing, prefs):
    score = 0.0
    has_config = False

    if prefs.preferred_districts:
        has_config = True
        if listing.district:
            for d in prefs.preferred_districts:
                if d in listing.district or listing.district in d:
                    score += WEIGHT_LOCATION * 0.5
                    break

    if prefs.preferred_subway_stations:
        has_config = True
        text = "{} {} {}".format(
            listing.title or "", listing.address or "", listing.subway_station or ""
        )
        for station in prefs.preferred_subway_stations:
            if station in text:
                score += WEIGHT_LOCATION * 0.5
                break

    if not has_config:
        return WEIGHT_LOCATION * 0.6

    return min(score, WEIGHT_LOCATION)


def _score_commute(listing, prefs):
    if not prefs.workplace_station or not prefs.max_commute_minutes:
        return WEIGHT_COMMUTE * 0.5

    text = "{} {} {}".format(
        listing.title or "", listing.address or "", listing.subway_station or ""
    )

    if prefs.workplace_station in text:
        return WEIGHT_COMMUTE

    if prefs.preferred_subway_stations:
        for station in prefs.preferred_subway_stations:
            if station in text:
                return WEIGHT_COMMUTE * 0.8

    return WEIGHT_COMMUTE * 0.4


def _score_facilities(listing, prefs):
    if not prefs.required_facilities:
        return WEIGHT_FACILITIES * 0.7

    text = "{} {}".format(listing.title or "", listing.description or "")
    matched = sum(1 for f in prefs.required_facilities if f in text)
    ratio = matched / len(prefs.required_facilities)

    if ratio >= 0.8:
        return WEIGHT_FACILITIES
    if ratio >= 0.5:
        return WEIGHT_FACILITIES * 0.7
    if ratio > 0:
        return WEIGHT_FACILITIES * 0.4
    return WEIGHT_FACILITIES * 0.2


def _score_quiet(listing):
    text = "{} {} {}".format(
        listing.title or "", listing.description or "", listing.address or ""
    )

    quiet_hits = sum(1 for kw in QUIET_KEYWORDS if kw in text)
    deal_hits = sum(1 for kw in DEAL_KEYWORDS if kw in text)

    score = 0.0

    if quiet_hits >= 2:
        score += WEIGHT_QUIET * 0.7
    elif quiet_hits >= 1:
        score += WEIGHT_QUIET * 0.4

    if deal_hits >= 1:
        score += WEIGHT_QUIET * 0.3

    return min(score, WEIGHT_QUIET)


def score_all(listings, prefs):
    for listing in listings:
        listing.score = score_listing(listing, prefs)
    listings.sort(key=lambda x: x.score or 0, reverse=True)
    return listings
