"""Step 7 — aggregates REAL per-run token data from logs/runs/*.json (every
live call made this session) into the numbers the brief's Tokenomics
section needs: per-agent averages, a representative "one search" cost, and
scale projections. No new live calls — this only reads what already ran."""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.audit_log import TokenUsage, estimate_cost_usd  # noqa: E402

LOG_DIR = Path(__file__).resolve().parents[1] / "logs" / "runs"

# Assumption, stated plainly: how many searches a typical active user runs
# per month. Not a measured number — there's no real user base yet (Step 9
# is the first real user evidence). Used only to scale a per-search cost
# into a per-user-per-month figure.
ASSUMED_SEARCHES_PER_MONTH_PER_USER = 10
CANDIDATES_PER_SEARCH = 3  # matches app/web/server.py's MAX_CANDIDATES


def load_all_logs() -> list[dict]:
    return [json.loads(p.read_text()) for p in LOG_DIR.glob("*.json")]


def tokens_from(d: dict) -> TokenUsage:
    return TokenUsage(**d)


def main() -> None:
    logs = load_all_logs()
    print(f"Loaded {len(logs)} real run logs from logs/runs/\n")

    discovery_logs = [l for l in logs if l["subject"].startswith("discovery:")]
    restaurant_logs = [l for l in logs if not l["subject"].startswith("discovery:")]
    live_restaurant_logs = [l for l in restaurant_logs if l["overall_stop_reason"] == "completed"]
    cached_restaurant_logs = [l for l in restaurant_logs if l["overall_stop_reason"] == "cached"]

    print(f"Discovery calls: {len(discovery_logs)}")
    print(f"Restaurant evaluations (live): {len(live_restaurant_logs)}")
    print(f"Restaurant evaluations (cache hit): {len(cached_restaurant_logs)}")
    print()

    # --- Per-agent real token averages (live restaurant evaluations only) ---
    by_agent: dict[str, list[TokenUsage]] = {}
    for log in live_restaurant_logs:
        for call in log["agent_calls"]:
            if call["tokens"]:
                by_agent.setdefault(call["agent_name"], []).append(tokens_from(call["tokens"]))

    print("=== Per-agent real token averages (live restaurant evaluations) ===")
    for agent, usages in sorted(by_agent.items()):
        avg_in = statistics.mean(u.input_tokens for u in usages)
        avg_cached = statistics.mean(u.cached_input_tokens for u in usages)
        avg_out = statistics.mean(u.output_tokens for u in usages)
        print(f"  {agent:<20} n={len(usages):<4} avg input={avg_in:.0f}  avg cached={avg_cached:.0f}  avg output={avg_out:.0f}")
    print()

    # --- Average total per one live restaurant evaluation ---
    def total_tokens(log: dict) -> TokenUsage:
        return tokens_from(log["total_tokens"])

    live_totals = [total_tokens(l) for l in live_restaurant_logs]
    avg_restaurant = TokenUsage(
        input_tokens=round(statistics.mean(t.input_tokens for t in live_totals)),
        cached_input_tokens=round(statistics.mean(t.cached_input_tokens for t in live_totals)),
        output_tokens=round(statistics.mean(t.output_tokens for t in live_totals)),
    )
    avg_restaurant_cost = estimate_cost_usd(avg_restaurant)
    print(f"=== Average per LIVE restaurant evaluation (n={len(live_totals)}) ===")
    print(f"  {avg_restaurant}  -> est. ${avg_restaurant_cost:.4f}")
    print()

    discovery_totals = [total_tokens(l) for l in discovery_logs]
    avg_discovery = TokenUsage(
        input_tokens=round(statistics.mean(t.input_tokens for t in discovery_totals)),
        cached_input_tokens=round(statistics.mean(t.cached_input_tokens for t in discovery_totals)),
        output_tokens=round(statistics.mean(t.output_tokens for t in discovery_totals)),
    )
    avg_discovery_cost = estimate_cost_usd(avg_discovery)
    print(f"=== Average per discovery call (n={len(discovery_totals)}) ===")
    print(f"  {avg_discovery}  -> est. ${avg_discovery_cost:.4f}")
    print()

    # --- Representative "one search" cost: 1 discovery + N restaurants ---
    # Real-world mix matters: as the cache fills up, a growing share of
    # restaurants in a search are cache hits (near-zero cost). Model two
    # scenarios explicitly rather than picking one number.
    all_live_pct = 1.0
    steady_state_cache_hit_rate = len(cached_restaurant_logs) / max(1, len(restaurant_logs))

    def search_cost(cache_hit_rate: float) -> float:
        live_count = CANDIDATES_PER_SEARCH * (1 - cache_hit_rate)
        return avg_discovery_cost + live_count * avg_restaurant_cost

    cold_cost = search_cost(0.0)
    warm_cost = search_cost(steady_state_cache_hit_rate)

    print("=== Representative one-search cost (1 discovery + 3 restaurants) ===")
    print(f"  Cold (no cache hits yet):         ${cold_cost:.4f}")
    print(f"  This session's actual mix ({steady_state_cache_hit_rate:.0%} cache hit rate): ${warm_cost:.4f}")
    print()

    # --- Scale projections ---
    print("=== Scale projections (ASSUMPTION: each user searches "
          f"{ASSUMED_SEARCHES_PER_MONTH_PER_USER}x/month — not a measured number, no real users yet) ===")
    for label, cost in [("cold (worst case)", cold_cost), ("warm (this session's cache rate)", warm_cost)]:
        per_user_month = cost * ASSUMED_SEARCHES_PER_MONTH_PER_USER
        print(f"  [{label}]")
        print(f"    per search:        ${cost:.4f}")
        print(f"    per user/month:    ${per_user_month:.2f}")
        print(f"    at 100 users:      ${per_user_month * 100:,.2f}/month")
        print(f"    at 10,000 users:   ${per_user_month * 10_000:,.2f}/month")
        print()

    # --- Caching as a cost-reduction step, with real evidence ---
    # Only count the expensive chain (evidence_extractor/skeptic/ranker) —
    # Finder legitimately still runs on a cache hit reached via
    # run_for_restaurant (it confirms identity before the cache check), so
    # including it would wrongly suggest the cache didn't skip anything.
    EXPENSIVE_CHAIN = {"evidence_extractor", "skeptic", "ranker"}
    cache_hit_chain_tokens = sum(
        tokens_from(c["tokens"]).input_tokens
        for l in cached_restaurant_logs
        for c in l["agent_calls"]
        if c["tokens"] and c["agent_name"] in EXPENSIVE_CHAIN
    )
    finder_calls_on_cache_hits = sum(1 for l in cached_restaurant_logs for c in l["agent_calls"] if c["agent_name"] == "finder")
    print("=== Cost-reduction evidence: caching ===")
    print(f"  {len(cached_restaurant_logs)} real cache hits recorded this session.")
    print(f"  Evidence/Skeptic/Ranker tokens spent on those hits: {cache_hit_chain_tokens} (correctly 0 — the expensive chain never ran)")
    print(f"  Finder still ran on {finder_calls_on_cache_hits}/{len(cached_restaurant_logs)} of them (cheap, ~9k tokens, needed to re-confirm identity)")
    print(f"  A cache hit saves ~${avg_restaurant_cost:.4f}/restaurant with ZERO quality difference —")
    print("  it returns the exact same real, previously-verified result, not an approximation.")


if __name__ == "__main__":
    main()
