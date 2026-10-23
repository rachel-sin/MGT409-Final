"""Per-restaurant cache with 30-day expiry, and the live/cached switch.
Backs the brief's cached dataset: ~20 real DC restaurants, built from real
live runs, stored as plain JSON (no database — matches the "simple to run"
constraint). Also closes the Step 5 "fallback to cached data if live search
fails or a cap is hit" requirement: a cache hit means zero new tokens spent
and zero risk of a live-search hiccup for that restaurant.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from app.models import EvidenceBatch, ReviewedBatch, RestaurantCandidate, SafetyAssessment

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cached_restaurants.json"
CACHE_EXPIRY_DAYS = 30


class CachedRestaurant(BaseModel):
    restaurant: RestaurantCandidate
    evidence: EvidenceBatch
    reviewed: ReviewedBatch
    assessment: SafetyAssessment
    cached_at: str  # ISO timestamp


def _slug(name: str) -> str:
    return name.strip().lower()


def _load_raw() -> dict:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text())


def _save_raw(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2))


def get_cached(name: str) -> CachedRestaurant | None:
    """Returns a cached entry if one exists and isn't older than
    CACHE_EXPIRY_DAYS, else None (cache miss, expired, or never cached)."""
    data = _load_raw()
    entry = data.get(_slug(name))
    if entry is None:
        return None
    cached = CachedRestaurant.model_validate(entry)
    cached_at = datetime.fromisoformat(cached.cached_at)
    if datetime.now(timezone.utc) - cached_at > timedelta(days=CACHE_EXPIRY_DAYS):
        return None
    return cached


def put_cached(
    restaurant: RestaurantCandidate, evidence: EvidenceBatch, reviewed: ReviewedBatch, assessment: SafetyAssessment
) -> None:
    data = _load_raw()
    entry = CachedRestaurant(
        restaurant=restaurant,
        evidence=evidence,
        reviewed=reviewed,
        assessment=assessment,
        cached_at=datetime.now(timezone.utc).isoformat(),
    )
    data[_slug(restaurant.name)] = json.loads(entry.model_dump_json())
    _save_raw(data)


def all_cached() -> dict[str, CachedRestaurant]:
    return {k: CachedRestaurant.model_validate(v) for k, v in _load_raw().items()}
