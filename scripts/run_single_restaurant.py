"""Step 2 — run one restaurant through all 4 agents end to end and print
every stage's output so it can be inspected, not just the final answer."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import run_for_restaurant  # noqa: E402

DEFAULT_RESTAURANT = "Surfside"
DEFAULT_HINT = "Georgetown, Washington DC — tacos"


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESTAURANT
    hint = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HINT

    print(f"Running pipeline for: {name} ({hint})\n")
    result = await run_for_restaurant(name, hint)

    print("=== Finder ===")
    print(result.restaurant.model_dump_json(indent=2))

    print("\n=== Evidence Extractor ===")
    print(result.evidence.model_dump_json(indent=2))

    print("\n=== Skeptic ===")
    print(result.reviewed.model_dump_json(indent=2))

    print("\n=== Ranker (final) ===")
    print(result.assessment.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
