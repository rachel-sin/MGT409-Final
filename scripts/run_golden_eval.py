"""Step 6 — golden-set accuracy check. Compares the system's actual cached
tier for each of the 10 golden-set restaurants against an independent human
label (data/golden_set.json), read directly from the real cached dataset —
no new live calls, no re-running the pipeline just for this check."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.cache import all_cached  # noqa: E402

GOLDEN_SET_PATH = Path(__file__).resolve().parents[1] / "data" / "golden_set.json"


def main() -> None:
    golden = json.loads(GOLDEN_SET_PATH.read_text())["entries"]
    cached = all_cached()

    correct = 0
    total = 0
    print(f"{'Restaurant':<40} {'Golden label':<35} {'System tier':<35} {'Match'}")
    print("-" * 120)
    for entry in golden:
        name = entry["name"]
        golden_label = entry["label"]
        cached_entry = cached.get(name.strip().lower())
        if cached_entry is None:
            print(f"{name:<40} {golden_label:<35} {'NOT IN CACHE':<35} SKIP")
            continue
        system_tier = cached_entry.assessment.safety_level
        is_match = system_tier == golden_label
        total += 1
        correct += int(is_match)
        print(f"{name:<40} {golden_label:<35} {system_tier:<35} {'YES' if is_match else 'NO'}")

    print("-" * 120)
    accuracy = correct / total if total else 0.0
    print(f"\nAccuracy: {correct}/{total} = {accuracy:.0%}")

    mismatches = [
        e for e in golden if (c := cached.get(e["name"].strip().lower())) and c.assessment.safety_level != e["label"]
    ]
    if mismatches:
        print("\nMismatches (worth discussing honestly in the report):")
        for e in mismatches:
            c = cached[e["name"].strip().lower()]
            print(f"- {e['name']}: golden={e['label']!r} vs system={c.assessment.safety_level!r}")
            print(f"  golden reasoning: {e['reasoning']}")


if __name__ == "__main__":
    main()
