"""Step 6 — builds the ~20-restaurant cached dataset by running the real
live pipeline (discovery + full 4-agent evaluation) across several DC
neighborhoods, relying on app.harness.cache's live/cached switch to persist
each result to data/cached_restaurants.json as it goes. Safe to re-run:
restaurants already cached (and not expired) are skipped automatically."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.cache import all_cached  # noqa: E402
from app.pipeline import run_for_discovered_list  # noqa: E402

# A spread of real DC neighborhoods, no cuisine filter, to get diversity
# without hand-picking specific restaurants (keeps this an honest sample,
# not cherry-picked to make the system look good).
NEIGHBORHOODS = [
    # New neighborhoods first, to reach the target with fresh coverage
    # before re-trying ones already attempted in a prior run.
    "Shaw, Washington DC",
    "Navy Yard, Washington DC",
    "Foggy Bottom, Washington DC",
    "Petworth, Washington DC",
    "Cleveland Park, Washington DC",
    "Mount Vernon Triangle, Washington DC",
    "U Street, Washington DC",
    "Chinatown, Washington DC",
    "Capitol Hill, Washington DC",
]

CANDIDATES_PER_NEIGHBORHOOD = 3
TARGET_TOTAL = 20


async def main() -> None:
    for neighborhood in NEIGHBORHOODS:
        current_count = len(all_cached())
        if current_count >= TARGET_TOTAL:
            print(f"Already have {current_count} cached restaurants (target {TARGET_TOTAL}) — stopping.")
            break

        print(f"\n=== {neighborhood} (currently {current_count} cached) ===")
        outcome = await run_for_discovered_list(neighborhood, None, CANDIDATES_PER_NEIGHBORHOOD)
        if outcome.search_likely_failed:
            print(f"  search failed for this neighborhood: {outcome.note}")
            continue
        for r in outcome.results:
            print(f"  - {r.restaurant.name}: {r.assessment.safety_level} (confidence: {r.assessment.confidence})")

    final_count = len(all_cached())
    print(f"\n=== Done. {final_count} restaurant(s) now in data/cached_restaurants.json ===")
    for name, entry in all_cached().items():
        print(f"- {entry.restaurant.name}: {entry.assessment.safety_level}")


if __name__ == "__main__":
    asyncio.run(main())
