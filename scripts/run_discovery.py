"""Step 3 — discover a small list of candidate restaurants via broad web
search (not a directory scrape), then run each through the full pipeline."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import run_for_discovered_list  # noqa: E402

DEFAULT_NEIGHBORHOOD = "Adams Morgan, Washington DC"
DEFAULT_CUISINE = None
DEFAULT_MAX_CANDIDATES = 3  # kept small for this first live test — no caps built yet (Step 5)


async def main() -> None:
    neighborhood = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NEIGHBORHOOD
    cuisine = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CUISINE
    max_candidates = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_MAX_CANDIDATES

    print(f"Discovering up to {max_candidates} candidates for: neighborhood={neighborhood!r}, cuisine={cuisine!r}\n")
    outcome = await run_for_discovered_list(neighborhood, cuisine, max_candidates)

    if outcome.search_likely_failed:
        print(f"SEARCH LIKELY FAILED (not a genuine zero-match result): {outcome.note}\n")
    elif outcome.note:
        print(f"Note: {outcome.note}\n")

    print(f"Found and assessed {len(outcome.results)} restaurant(s):\n")
    for r in outcome.results:
        print(f"- {r.restaurant.name} ({r.restaurant.address})")
        print(f"  safety_level: {r.assessment.safety_level} (confidence: {r.assessment.confidence})")
        print(f"  claims found: {len(r.evidence.claims)}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
