from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class HousingListing:
    listing_id: str = ""
    source: str = ""
    title: str = ""
    price: float = 0.0
    area: Optional[float] = None
    rooms: Optional[str] = None
    floor: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None
    subway_station: Optional[str] = None
    url: str = ""
    description: Optional[str] = None
    images: list = field(default_factory=list)
    publish_time: Optional[datetime] = None
    crawl_time: datetime = field(default_factory=datetime.now)
    score: Optional[float] = None

    def summary(self) -> str:
        parts = [
            f"[{self.source}]",
            self.title[:40] if self.title else "",
            f"{self.price}元/月" if self.price else "价格未知",
        ]
        if self.area:
            parts.append(f"{self.area}㎡")
        if self.rooms:
            parts.append(self.rooms)
        if self.district:
            parts.append(self.district)
        return " | ".join(p for p in parts if p)


@dataclass
class UserPreferences:
    budget_min: float = 0
    budget_max: float = 5000
    area_min: float = 20
    area_max: float = 100
    preferred_districts: list = field(default_factory=list)
    preferred_subway_stations: list = field(default_factory=list)
    max_commute_minutes: int = 60
    workplace_station: Optional[str] = None
    required_facilities: list = field(default_factory=list)
    preferred_rooms: list = field(default_factory=list)
