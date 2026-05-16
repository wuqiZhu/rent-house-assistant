import logging

from models import HousingListing, UserPreferences

logger = logging.getLogger(__name__)


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

    if budget_min <= price <= budget_max:
        mid = (budget_min + budget_max) / 2
        distance = abs(price - mid) / (budget_max - budget_min + 1) * 2
        return 30 * (1 - distance * 0.3)
    elif price < budget_min:
        return 20
    else:
        over = (price - budget_max) / budget_max
        return max(0, 30 - over * 100)


def _score_area(area, prefs):
    if area is None or area <= 0:
        return 5

    if prefs.area_min <= area <= prefs.area_max:
        return 20
    elif area < prefs.area_min:
        ratio = area / prefs.area_min
        return 20 * ratio
    else:
        return 18


def _score_location(listing, prefs):
    score = 0.0

    if prefs.preferred_districts and listing.district:
        if listing.district in prefs.preferred_districts:
            score += 10

    if prefs.preferred_subway_stations:
        text = "{} {} {}".format(
            listing.title or "", listing.address or "", listing.subway_station or ""
        )
        for station in prefs.preferred_subway_stations:
            if station in text:
                score += 10
                break

    if not prefs.preferred_districts and not prefs.preferred_subway_stations:
        score = 12

    return min(score, 20)


def _score_commute(listing, prefs):
    if not prefs.workplace_station or not prefs.max_commute_minutes:
        return 7

    text = "{} {} {}".format(
        listing.title or "", listing.address or "", listing.subway_station or ""
    )
    if prefs.workplace_station in text:
        return 15

    if prefs.preferred_subway_stations:
        for station in prefs.preferred_subway_stations:
            if station in text:
                return 12

    return 7


def _score_facilities(listing, prefs):
    if not prefs.required_facilities:
        return 10

    text = "{} {}".format(listing.title or "", listing.description or "")
    matched = sum(1 for f in prefs.required_facilities if f in text)
    ratio = matched / len(prefs.required_facilities)
    return 15 * ratio


def score_all(listings, prefs):
    for listing in listings:
        listing.score = score_listing(listing, prefs)
    listings.sort(key=lambda x: x.score or 0, reverse=True)
    return listings
