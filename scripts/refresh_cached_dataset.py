"""Re-runs the full live pipeline for every restaurant already in the cached
dataset, overwriting each entry — used after a prompt/logic fix (like the
Skeptic's is_promotional definition, FAILURES.md #14) to re-evaluate the
existing dataset under the corrected rules rather than leaving stale
pre-fix verdicts in place. Prints before/after tiers so any tier change is
visible and can be checked against data/golden_set.json afterward."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.audit_log import new_run_log  # noqa: E402
from app.harness.cache import all_cached, put_cached  # noqa: E402
from app.pipeline import _run_evidence_to_assessment  # noqa: E402


async def main() -> None:
    before = all_cached()
    print(f"Refreshing {len(before)} cached restaurant(s)...\n")

    changed = []
    for slug, entry in before.items():
        old_tier = entry.assessment.safety_level
        run_log = new_run_log(f"refresh: {entry.restaurant.name}")
        try:
            result = await _run_evidence_to_assessment(entry.restaurant, run_log, use_cache=False)
        except Exception as exc:  # noqa: BLE001
            print(f"- {entry.restaurant.name}: FAILED to refresh ({type(exc).__name__}: {exc}) — kept old entry")
            continue
        new_tier = result.assessment.safety_level
        marker = "CHANGED" if new_tier != old_tier else "same"
        print(f"- {entry.restaurant.name}: {old_tier} -> {new_tier}  [{marker}]")
        # use_cache=False above was only to force a fresh run (bypassing the
        # cache check); persist the refreshed result ourselves.
        put_cached(result.restaurant, result.evidence, result.reviewed, result.assessment)
        if new_tier != old_tier:
            changed.append((entry.restaurant.name, old_tier, new_tier))

    print(f"\n=== Done. {len(changed)} restaurant(s) changed tier. ===")
    for name, old, new in changed:
        print(f"- {name}: {old} -> {new}")


if __name__ == "__main__":
    asyncio.run(main())
