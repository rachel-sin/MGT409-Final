"""Step 2: runs one restaurant through all 4 agents in sequence and returns
every stage's output, so the real reasoning can be inspected end to end
(not just the final answer)."""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import date, datetime

from pydantic_ai.exceptions import UsageLimitExceeded

from app.agents.evidence_extractor import evidence_extractor_agent
from app.agents.finder import finder_agent, finder_discovery_agent
from app.agents.ranker import ranker_agent
from app.agents.skeptic import skeptic_agent
from app.harness.audit_log import AgentCallRecord, RunLog, TokenUsage, new_run_log, save_run_log
from app.harness.cache import get_cached, put_cached
from app.harness.discovery_cache import get_cached_discovery, put_cached_discovery
from app.harness.grounding import restaurant_existence_grounded, verify_claims_grounded
from app.harness.input_guard import validate_search_input
from app.models import CandidateBatch, EvidenceBatch, ReviewedBatch, ReviewedClaim, RestaurantCandidate, SafetyAssessment
from app.runtime import (
    AGENT_WALL_CLOCK_TIMEOUT_SECONDS,
    DEFAULT_USAGE_LIMITS,
    DISCOVERY_USAGE_LIMITS,
    DISCOVERY_WALL_CLOCK_TIMEOUT_SECONDS,
    EVIDENCE_USAGE_LIMITS,
    EVIDENCE_WALL_CLOCK_TIMEOUT_SECONDS,
    MAX_CONCURRENT_RESTAURANT_RUNS,
)

RECENCY_WINDOW_DAYS = 183  # ~6 months

# Best-evidence-first display order for a list of results (the app's whole
# premise is ranking by safety evidence, so the order it returns candidates
# in — essentially arbitrary live-search order — was never the right order
# to show them in; see FAILURES.md #16). A credible illness report still
# shows (never filtered out), just last, since it's the worst outcome, not
# the best.
SAFETY_LEVEL_RANK_ORDER = [
    "confirmed_dedicated_gf_prep",
    "accommodates_caution_cross_contamination",
    "unclear_gluten_specific",
    "no_evidence_found",
    "credible_illness_report",
]


class AgentCapExceeded(Exception):
    """Raised when an agent call hits its step/token cap or wall-clock
    timeout. Callers that run multiple restaurants (run_for_discovered_list)
    catch this to skip just the one restaurant rather than crash the batch —
    a minimum-viable version of the brief's "fallback ... with a message to
    the user" requirement, ahead of Step 5's fuller version."""


async def _run_agent(agent, prompt: str, usage_limits=DEFAULT_USAGE_LIMITS, timeout=AGENT_WALL_CLOCK_TIMEOUT_SECONDS):
    try:
        return await asyncio.wait_for(agent.run(prompt, usage_limits=usage_limits), timeout=timeout)
    except UsageLimitExceeded as exc:
        raise AgentCapExceeded(f"Step/token cap exceeded: {exc}") from exc
    except asyncio.TimeoutError as exc:
        raise AgentCapExceeded(f"Wall-clock timeout ({timeout}s) exceeded") from exc


async def _run_agent_logged(
    agent,
    agent_name: str,
    prompt: str,
    run_log: RunLog,
    usage_limits=DEFAULT_USAGE_LIMITS,
    timeout=AGENT_WALL_CLOCK_TIMEOUT_SECONDS,
    extract_sources=None,
):
    """Runs an agent through _run_agent and appends what happened to
    run_log, whether the call succeeds or fails — so a cap/timeout/error is
    itself an audited event, not a silent gap in the log."""
    start = time.monotonic()
    try:
        result = await _run_agent(agent, prompt, usage_limits=usage_limits, timeout=timeout)
    except AgentCapExceeded as exc:
        duration = time.monotonic() - start
        stop_reason = "timeout" if "timeout" in str(exc).lower() else "cap_exceeded"
        run_log.agent_calls.append(
            AgentCallRecord(
                agent_name=agent_name, prompt_preview=prompt[:200], duration_seconds=duration, stop_reason=stop_reason, error=str(exc)
            )
        )
        raise
    except Exception as exc:  # noqa: BLE001
        duration = time.monotonic() - start
        run_log.agent_calls.append(
            AgentCallRecord(
                agent_name=agent_name,
                prompt_preview=prompt[:200],
                duration_seconds=duration,
                stop_reason="error",
                error=f"{type(exc).__name__}: {exc}",
            )
        )
        raise

    duration = time.monotonic() - start
    usage = result.usage
    sources = extract_sources(result.output) if extract_sources else []
    run_log.agent_calls.append(
        AgentCallRecord(
            agent_name=agent_name,
            prompt_preview=prompt[:200],
            tokens=TokenUsage(
                input_tokens=usage.input_tokens or 0,
                cached_input_tokens=usage.cache_read_tokens or 0,
                output_tokens=usage.output_tokens or 0,
            ),
            duration_seconds=duration,
            stop_reason="completed",
            sources=sources,
        )
    )
    return result


def _is_credible(c: ReviewedClaim) -> bool:
    return not c.is_promotional and not c.is_contradicted


def _is_recent(source_date: str | None, today: date) -> bool:
    if not source_date:
        return False
    try:
        parsed = datetime.strptime(source_date, "%Y-%m-%d").date()
    except ValueError:
        return False  # malformed date from the model — treat as not verifiable, not recent
    return 0 <= (today - parsed).days <= RECENCY_WINDOW_DAYS


TIER1_TOPICS = {"entirely_gluten_free_facility", "dedicated_fryer_or_prep_area"}


def _qualifies_for_tier1(c: ReviewedClaim, today: date) -> bool:
    """A claim qualifies for confirmed_dedicated_gf_prep if it's credible,
    about the right topic, positive, AND fresh enough — where "fresh enough"
    means something different depending on the source: the restaurant's own
    site is current by construction (we just fetched it today), but a
    third-party review describes a past visit that can go stale."""
    if c.claim.topic not in TIER1_TOPICS or c.claim.direction != "positive" or not _is_credible(c):
        return False
    if c.claim.source_type == "own_menu":
        return True
    return _is_recent(c.claim.source_date, today)


def apply_safety_backstops(assessment: SafetyAssessment, reviewed: ReviewedBatch, today: date) -> SafetyAssessment:
    """Code-level enforcement of the two rules that matter most, re-checked
    independently of whatever the Ranker model said. This is the backstop
    referenced in app/agents/ranker.py's docstring — per the project's
    "enforce rules in code, not only in prompts" principle, the Ranker's own
    output is never trusted blindly on these two points."""

    all_claims = reviewed.claims

    # Rule 1 (highest priority): a credible, uncontradicted got-sick claim
    # forces this tier, overriding anything the model picked.
    credible_illness_claims = [
        c for c in all_claims if c.claim.topic == "reviewer_got_sick" and c.claim.direction == "negative" and _is_credible(c)
    ]
    if credible_illness_claims and assessment.safety_level != "credible_illness_report":
        return assessment.model_copy(
            update={
                "safety_level": "credible_illness_report",
                "override_applied": True,
                "override_reason": (
                    "Code-level asymmetric risk rule: found a credible, uncontradicted reviewer_got_sick claim "
                    f"({credible_illness_claims[0].claim.quote!r}), which overrides the model's own tier choice."
                ),
            }
        )

    # Rule 2: tier 1a (confirmed_dedicated_gf_prep) requires a credible,
    # sufficiently-fresh claim — re-verified independently of the model's
    # claim that one exists. An own-site claim needs no date (see
    # _qualifies_for_tier1); a third-party claim does.
    if assessment.safety_level == "confirmed_dedicated_gf_prep":
        qualifying = [c for c in all_claims if _qualifies_for_tier1(c, today)]
        if not qualifying:
            return assessment.model_copy(
                update={
                    "safety_level": "accommodates_caution_cross_contamination",
                    "override_applied": True,
                    "override_reason": (
                        "Code-level check: no credible entirely_gluten_free_facility/dedicated_fryer_or_prep_area "
                        "claim qualified (own-site claims need no date, but no third-party claim was dated within "
                        f"{RECENCY_WINDOW_DAYS} days of {today.isoformat()}), so tier 1a does not qualify."
                    ),
                }
            )

    return assessment


# Absolutist safety language the brief explicitly forbids — checked in code,
# not just by prompt instruction, since a prompt rule is exactly what a
# prompt-injection attack targets. Matched case-insensitively, as whole
# phrases rather than single words, to avoid false positives on legitimate
# text like "not entirely gluten-free".
BANNED_ABSOLUTE_PHRASES = [
    "100% safe",
    "completely safe",
    "totally safe",
    "guaranteed safe",
    "always safe",
    "perfectly safe",
    "entirely safe",
    "fully safe",
    "risk-free",
    "no risk",
]


def apply_output_scanner(assessment: SafetyAssessment) -> SafetyAssessment:
    """Code-level backstop blocking absolutist safety language, independent
    of whether the Ranker's prompt was followed — including if the prompt
    itself was compromised by injected instructions in fetched text (see
    the prompt-injection test). Scans both user-facing text fields."""
    found = []
    updates = {}
    for field in ("short_summary", "rationale"):
        text = getattr(assessment, field)
        lowered = text.lower()
        hit_phrases = [p for p in BANNED_ABSOLUTE_PHRASES if p in lowered]
        if hit_phrases:
            found.extend(hit_phrases)
            redacted = text
            for phrase in hit_phrases:
                # Case-insensitive replace, preserving the rest of the sentence.
                redacted = re.sub(re.escape(phrase), "evidence suggests accommodation (not a guarantee)", redacted, flags=re.IGNORECASE)
            updates[field] = redacted

    if not found:
        return assessment

    updates["override_applied"] = True
    existing_reason = assessment.override_reason
    scanner_reason = f"Code-level output scanner: redacted absolutist safety language ({', '.join(sorted(set(found)))})."
    updates["override_reason"] = f"{existing_reason} {scanner_reason}" if existing_reason else scanner_reason
    return assessment.model_copy(update=updates)


def _candidate_sources(out: RestaurantCandidate) -> list[str]:
    return [out.existence_source_url]


def _candidate_batch_sources(out: CandidateBatch) -> list[str]:
    return sorted({c.existence_source_url for c in out.candidates})


def _evidence_sources(out: EvidenceBatch) -> list[str]:
    return sorted({c.source_url for c in out.claims})


def _reviewed_sources(out: ReviewedBatch) -> list[str]:
    return sorted({c.claim.source_url for c in out.claims})


def _assessment_sources(out: SafetyAssessment) -> list[str]:
    return sorted({c.claim.source_url for c in (out.supporting_claims + out.contradicting_claims)})


# A genuine broad search takes meaningfully longer than this; an empty
# result that came back faster almost certainly means the web search tool
# itself didn't fire this call, not that nothing exists — see HARNESS.md's
# "live search reliability" entry.
SEARCH_FAILURE_DURATION_THRESHOLD_SECONDS = 3.0


@dataclass
class DiscoveryOutcome:
    batch: CandidateBatch
    run_log: RunLog
    search_likely_failed: bool  # True = looks like live search itself failed, not "genuinely no matches"


def _looks_like_real_address(address: str) -> bool:
    """Code-level backstop, not just a prompt instruction: a real street
    address always contains a digit (a street number) and isn't a long
    prose sentence. Catches the model writing an explanation into the
    address field instead of a real address or omitting the restaurant
    (see FAILURES.md's address-field entry)."""
    return bool(re.search(r"\d", address)) and len(address) < 80


async def _discover_once(neighborhood, cuisine, max_candidates, run_log, exclude_names=None) -> tuple[CandidateBatch, bool]:
    # Title-cased, trimmed input — cheap mitigation for an observed pattern
    # where an all-lowercase, informally-phrased query made the model skip
    # invoking web search entirely (see HARNESS.md's "live search
    # reliability" entry). Doesn't fully explain the variance, but costs
    # nothing and removed the failure in testing.
    neighborhood = neighborhood.strip().title() if neighborhood else neighborhood
    cuisine = cuisine.strip().title() if cuisine else cuisine

    prompt = f"Find up to {max_candidates} candidate GF-friendly restaurants in Washington, DC."
    if neighborhood:
        prompt += f"\nNeighborhood: {neighborhood}"
    if cuisine:
        prompt += f"\nCuisine: {cuisine}"
    if exclude_names:
        prompt += f"\nAlready shown, find DIFFERENT restaurants (do not repeat these): {', '.join(exclude_names)}"

    result = await _run_agent_logged(
        finder_discovery_agent,
        "finder_discovery",
        prompt,
        run_log,
        usage_limits=DISCOVERY_USAGE_LIMITS,
        timeout=DISCOVERY_WALL_CLOCK_TIMEOUT_SECONDS,
        extract_sources=_candidate_batch_sources,
    )
    batch = result.output
    last_call = run_log.agent_calls[-1]

    format_valid = [c for c in batch.candidates if _looks_like_real_address(c.address)]
    format_dropped = [c for c in batch.candidates if c not in format_valid]

    # Existence check: independently re-fetch each candidate's own
    # existence_source_url and verify the name+address actually appear
    # there — never trust the Finder's own claim that it confirmed this.
    # Fetches run concurrently (blocking HTTP in threads) since there can be
    # several candidates and we don't want to serialize real network calls.
    existence_results = await asyncio.gather(*(asyncio.to_thread(restaurant_existence_grounded, c) for c in format_valid))
    valid_candidates = [c for c, ok in zip(format_valid, existence_results) if ok]
    existence_dropped = [c for c, ok in zip(format_valid, existence_results) if not ok]

    dropped = format_dropped + existence_dropped
    if dropped:
        note_parts = []
        if format_dropped:
            note_parts.append(
                "Dropped (no confirmable street address): " + ", ".join(c.name for c in format_dropped)
            )
        if existence_dropped:
            note_parts.append(
                "Dropped (existence not re-confirmed on its own source page): "
                + ", ".join(c.name for c in existence_dropped)
            )
        dropped_note = " ".join(note_parts)
        batch = batch.model_copy(
            update={
                "candidates": valid_candidates,
                "note": f"{batch.note} {dropped_note}" if batch.note else dropped_note,
            }
        )

    looks_like_search_failure = not batch.candidates and last_call.duration_seconds < SEARCH_FAILURE_DURATION_THRESHOLD_SECONDS
    return batch, looks_like_search_failure


async def discover_candidates(
    neighborhood: str | None = None, cuisine: str | None = None, max_candidates: int = 5, exclude_names: list[str] | None = None
) -> DiscoveryOutcome:
    # max_candidates is a stopgap bound on this first test, ahead of Step 5's
    # real per-run/per-session caps — not a substitute for those.
    subject = f"discovery: neighborhood={neighborhood!r} cuisine={cuisine!r} exclude={exclude_names!r}"
    run_log = new_run_log(subject)

    # The discovery-level cache (FAILURES.md #14) only applies to the base
    # query — a "show more" request with an exclude list is a deliberate
    # ask for different results, so it always goes live rather than
    # replaying the same cached candidate list.
    if not exclude_names:
        cached = get_cached_discovery(neighborhood, cuisine)
        if cached is not None:
            # Repeating the same neighborhood/cuisine search within the TTL
            # reuses the same candidate list instead of re-querying live
            # search — live search is unseeded, so an identical query can
            # otherwise return a different set of restaurants each time.
            run_log.overall_stop_reason = "cached"
            save_run_log(run_log)
            return DiscoveryOutcome(batch=cached.batch, run_log=run_log, search_likely_failed=cached.search_likely_failed)

    try:
        batch, looks_like_search_failure = await _discover_once(neighborhood, cuisine, max_candidates, run_log, exclude_names)
        if looks_like_search_failure:
            # One retry — a fast, empty result usually means the web search
            # tool didn't fire this call, not that nothing exists.
            batch, still_failing = await _discover_once(neighborhood, cuisine, max_candidates, run_log, exclude_names)
            if still_failing:
                batch = batch.model_copy(
                    update={
                        "note": (
                            "Live web search appears to be unavailable right now (this is not a result saying no "
                            "restaurants match — the search itself didn't return results twice in a row). "
                            "Please try again shortly."
                        )
                    }
                )
            looks_like_search_failure = still_failing
    except AgentCapExceeded:
        run_log.overall_stop_reason = run_log.agent_calls[-1].stop_reason
        save_run_log(run_log)
        raise
    except Exception:  # noqa: BLE001
        run_log.overall_stop_reason = "error"
        save_run_log(run_log)
        raise

    save_run_log(run_log)
    if not looks_like_search_failure and not exclude_names:
        # Don't cache a likely search failure — that's not a real "no
        # matches" answer worth pinning for the next 24 hours. Don't cache
        # an exclude-list ("show more") result under the base query's key
        # either — it would poison the base search with a partial list.
        put_cached_discovery(neighborhood, cuisine, batch, looks_like_search_failure)
    return DiscoveryOutcome(batch=batch, run_log=run_log, search_likely_failed=looks_like_search_failure)


@dataclass
class PipelineResult:
    restaurant: RestaurantCandidate
    evidence: EvidenceBatch
    reviewed: ReviewedBatch
    assessment: SafetyAssessment
    run_log: RunLog
    cached_at: str | None = None  # set when this result came from the cache, not a live run


async def run_for_restaurant(name: str, hint: str | None = None) -> PipelineResult:
    run_log = new_run_log(name)
    finder_prompt = f"Restaurant name: {name}"
    if hint:
        finder_prompt += f"\nHint (neighborhood/cuisine): {hint}"
    try:
        finder_result = await _run_agent_logged(
            finder_agent, "finder", finder_prompt, run_log, extract_sources=_candidate_sources
        )
        restaurant = finder_result.output
        return await _run_evidence_to_assessment(restaurant, run_log)
    except Exception:
        run_log.overall_stop_reason = run_log.agent_calls[-1].stop_reason if run_log.agent_calls else "error"
        save_run_log(run_log)
        raise


@dataclass
class DiscoveredListResult:
    results: list[PipelineResult]
    note: str | None  # the discovery agent's own explanation — why empty, or caveats, if any
    search_likely_failed: bool  # True = show an error state, not a plain "no matches" empty state
    input_rejected: bool = False  # True = the input guard blocked this before any agent ran


async def run_for_discovered_list(
    neighborhood: str | None = None, cuisine: str | None = None, max_candidates: int = 5, exclude_names: list[str] | None = None
) -> DiscoveredListResult:
    """Step 3: discover candidates, then run each through evidence/skeptic/
    ranker. Reuses Finder's discovery output directly rather than re-running
    the single-restaurant Finder again for each candidate — discovery already
    confirmed existence/address. exclude_names supports the "show more"
    action: the same search, but asking discovery for different restaurants
    than the ones already shown."""
    rejection = validate_search_input(neighborhood, cuisine)
    if rejection:
        return DiscoveredListResult(results=[], note=rejection, search_likely_failed=False, input_rejected=True)

    try:
        outcome = await discover_candidates(neighborhood, cuisine, max_candidates, exclude_names)
    except AgentCapExceeded as exc:
        print(f"Discovery failed: {exc}. Returning no results rather than crashing.")
        return DiscoveredListResult(results=[], note=f"Discovery hit a cost/time limit: {exc}", search_likely_failed=True)
    except Exception as exc:  # noqa: BLE001
        print(f"Discovery failed: provider/model error ({type(exc).__name__}): {exc}. Returning no results.")
        return DiscoveredListResult(
            results=[], note=f"Discovery failed ({type(exc).__name__}): {exc}", search_likely_failed=True
        )

    # Run candidates concurrently (bounded by a semaphore), not one at a
    # time — these are independent restaurants, so there's no reason to make
    # a user wait for restaurant 1 to finish before even starting restaurant
    # 2. This doesn't change total token spend (same number of calls either
    # way), only wall-clock time; the semaphore bounds peak request rate
    # against the provider rather than firing everything at once unbounded.
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_RESTAURANT_RUNS)

    async def _run_one(restaurant: RestaurantCandidate) -> PipelineResult | None:
        async with semaphore:
            run_log = new_run_log(restaurant.name)
            try:
                return await _run_evidence_to_assessment(restaurant, run_log)
            except AgentCapExceeded as exc:
                print(f"Skipping {restaurant.name}: {exc}")
                return None
            except Exception as exc:  # noqa: BLE001
                # Covers upstream model/provider errors (rate limits, content-filter
                # rejections, network errors, etc.) — same pattern as HW4's
                # backend/main.py: one restaurant hitting a provider hiccup
                # degrades to a skip, not a crash of the whole batch.
                print(f"Skipping {restaurant.name}: provider/model error ({type(exc).__name__}): {exc}")
                return None

    outcomes = await asyncio.gather(*(_run_one(r) for r in outcome.batch.candidates))
    results = [r for r in outcomes if r is not None]
    results.sort(key=lambda r: SAFETY_LEVEL_RANK_ORDER.index(r.assessment.safety_level))
    return DiscoveredListResult(results=results, note=outcome.batch.note, search_likely_failed=outcome.search_likely_failed)


async def _run_evidence_to_assessment(
    restaurant: RestaurantCandidate, run_log: RunLog, use_cache: bool = True
) -> PipelineResult:
    if use_cache:
        cached = get_cached(restaurant.name)
        if cached is not None:
            run_log.overall_stop_reason = "cached"
            run_log.final_safety_level = cached.assessment.safety_level
            run_log.final_confidence = cached.assessment.confidence
            run_log.override_applied = cached.assessment.override_applied
            save_run_log(run_log)
            return PipelineResult(
                restaurant=cached.restaurant,
                evidence=cached.evidence,
                reviewed=cached.reviewed,
                assessment=cached.assessment,
                run_log=run_log,
                cached_at=cached.cached_at,
            )

    try:
        evidence_prompt = (
            f"Restaurant: {restaurant.name}\n"
            f"Address: {restaurant.address}\n"
            "Find celiac-safety evidence for this specific restaurant."
        )
        evidence_result = await _run_agent_logged(
            evidence_extractor_agent,
            "evidence_extractor",
            evidence_prompt,
            run_log,
            usage_limits=EVIDENCE_USAGE_LIMITS,
            timeout=EVIDENCE_WALL_CLOCK_TIMEOUT_SECONDS,
            extract_sources=_evidence_sources,
        )
        evidence = evidence_result.output

        # Source grounding: independently re-fetch each claimed source and
        # verify the quote actually appears there — never trust the model's
        # own account of what a page said. Run in a thread since these are
        # blocking HTTP calls and we don't want to stall the event loop
        # (this pipeline runs multiple restaurants concurrently).
        grounded_claims, dropped_claims = await asyncio.to_thread(verify_claims_grounded, evidence.claims)
        if dropped_claims:
            dropped_note = f"Dropped {len(dropped_claims)} claim(s) that failed source-grounding verification."
            evidence = evidence.model_copy(
                update={
                    "claims": grounded_claims,
                    "note": f"{evidence.note} {dropped_note}" if evidence.note else dropped_note,
                }
            )

        skeptic_prompt = (
            f"Restaurant: {restaurant.name}\n"
            f"Claims to review (JSON):\n{evidence.model_dump_json(indent=2)}"
        )
        skeptic_result = await _run_agent_logged(
            skeptic_agent, "skeptic", skeptic_prompt, run_log, extract_sources=_reviewed_sources
        )
        reviewed = skeptic_result.output

        today = date.today()
        ranker_prompt = (
            f"Today's date: {today.isoformat()}\n"
            f"Restaurant (JSON): {restaurant.model_dump_json(indent=2)}\n"
            f"Reviewed claims (JSON): {reviewed.model_dump_json(indent=2)}"
        )
        ranker_result = await _run_agent_logged(
            ranker_agent, "ranker", ranker_prompt, run_log, extract_sources=_assessment_sources
        )
        assessment = apply_safety_backstops(ranker_result.output, reviewed, today)
        assessment = apply_output_scanner(assessment)

        run_log.final_safety_level = assessment.safety_level
        run_log.final_confidence = assessment.confidence
        run_log.override_applied = assessment.override_applied
        save_run_log(run_log)

        if use_cache:
            put_cached(restaurant, evidence, reviewed, assessment)

        return PipelineResult(restaurant=restaurant, evidence=evidence, reviewed=reviewed, assessment=assessment, run_log=run_log)
    except Exception:
        run_log.overall_stop_reason = run_log.agent_calls[-1].stop_reason if run_log.agent_calls else "error"
        save_run_log(run_log)
        raise
