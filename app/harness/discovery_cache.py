"""Cache for discovery's candidate list, keyed by (neighborhood, cuisine).

Without this, repeating the exact same neighborhood/cuisine search hits a
fresh, unseeded live web search every time — the Finder discovery agent can
legitimately return a different set (or ordering) of candidates for an
identical query, since nothing pins it to the same real-world search results
twice (see FAILURES.md #14: a real tester re-ran a search and got a
different restaurant list, which looked like a bug but was really just
unseeded live search). A short TTL (much shorter than the 30-day per-
restaurant cache in app/harness/cache.py) keeps repeat searches stable within
a session/demo while still refreshing discovery itself periodically."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from app.models import CandidateBatch

DISCOVERY_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "discovery_cache.json"
DISCOVERY_CACHE_EXPIRY_HOURS = 24


class CachedDiscovery(BaseModel):
    batch: CandidateBatch
    search_likely_failed: bool
    cached_at: str  # ISO timestamp


def _key(neighborhood: str | None, cuisine: str | None) -> str:
    return f"{(neighborhood or '').strip().lower()}|{(cuisine or '').strip().lower()}"


def _load_raw() -> dict:
    if not DISCOVERY_CACHE_PATH.exists():
        return {}
    return json.loads(DISCOVERY_CACHE_PATH.read_text())


def _save_raw(data: dict) -> None:
    DISCOVERY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERY_CACHE_PATH.write_text(json.dumps(data, indent=2))


def get_cached_discovery(neighborhood: str | None, cuisine: str | None) -> CachedDiscovery | None:
    data = _load_raw()
    entry = data.get(_key(neighborhood, cuisine))
    if entry is None:
        return None
    cached = CachedDiscovery.model_validate(entry)
    cached_at = datetime.fromisoformat(cached.cached_at)
    if datetime.now(timezone.utc) - cached_at > timedelta(hours=DISCOVERY_CACHE_EXPIRY_HOURS):
        return None
    return cached


def put_cached_discovery(
    neighborhood: str | None, cuisine: str | None, batch: CandidateBatch, search_likely_failed: bool
) -> None:
    data = _load_raw()
    entry = CachedDiscovery(batch=batch, search_likely_failed=search_likely_failed, cached_at=datetime.now(timezone.utc).isoformat())
    data[_key(neighborhood, cuisine)] = json.loads(entry.model_dump_json())
    _save_raw(data)
