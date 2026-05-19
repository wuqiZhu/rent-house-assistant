import logging

from models import HousingListing, UserPreferences

logger = logging.getLogger(__name__)

WEIGHT_PRICE = 30
WEIGHT_AREA = 20
WEIGHT_LOCATION = 20
WEIGHT_COMMUTE = 15
WEIGHT_FACILITIES = 15


def score_listing(listing, prefs):
    total = 0.0
    total += _score_price(listing.price, prefs)
    total += _score_area(listing.area, prefs)
    total += _score_location(listing, prefs)
    total += _score_commute(listing, prefs)
    total += _score_facilities(listing, prefs)
    return round(min(total, 100), 1)


def _score_price(price, prefs):
    if price <= 0:
        return 0

    budget_min = prefs.budget_min
    budget_max = prefs.budget_max
    budget_mid = (budget_min + budget_max) / 2

    if budget_min <= price <= budget_max:
        distance = abs(price - budget_mid) / (budget_max - budget_min + 1) * 2
        return WEIGHT_PRICE * (1 - distance * 0.3)

    if price < budget_min:
        ratio = price / budget_min
        if ratio >= 0.7:
            return WEIGHT_PRICE * 0.85
        return WEIGHT_PRICE * ratio

    over_ratio = (price - budget_max) / budget_max
    if over_ratio <= 0.1:
        return WEIGHT_PRICE * 0.6
    if over_ratio <= 0.3:
        return WEIGHT_PRICE * 0.3
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


def score_all(listings, prefs):
    for listing in listings:
        listing.score = score_listing(listing, prefs)
    listings.sort(key=lambda x: x.score or 0, reverse=True)
    return listings
