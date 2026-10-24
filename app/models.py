"""Shared structured I/O types passed between the agents (5 total: two
Finder modes — confirm-one and discover-many — plus Evidence Extractor,
Skeptic, and Ranker; a single-restaurant evaluation touches 4 of the 5).
Every claim the system makes carries a verbatim quote and a source URL
back to where it came from, per the brief's core requirement.
"""

from typing import Literal

from pydantic import BaseModel, Field

ClaimTopic = Literal[
    # A mixed kitchen that keeps one fryer/prep area separate for GF items —
    # NOT the same as the whole place being gluten-free (see below).
    "dedicated_fryer_or_prep_area",
    # The entire establishment is gluten-free — no wheat/gluten-containing
    # ingredients on premises at all (e.g. a dedicated GF bakery). This is a
    # STRONGER signal than dedicated_fryer_or_prep_area, which implies a
    # mixed kitchen with only one separated area.
    "entirely_gluten_free_facility",
    "staff_cross_contamination_knowledge",
    "reviewer_got_sick",
    "reviewer_was_fine",
    "other",
]

ClaimDirection = Literal["positive", "negative", "neutral"]

SourceType = Literal["own_menu", "third_party_aggregator"]


class RestaurantCandidate(BaseModel):
    """Output of the Finder agent: one restaurant, confirmed to exist."""

    name: str
    address: str = Field(
        description="ONLY the literal street address (e.g. '123 Main St NW, Washington, DC 20001'). "
        "Never a sentence, caveat, or explanation of what you did or didn't find — if no precise street "
        "address is confirmable, this restaurant should not be included at all."
    )
    neighborhood: str | None = None
    cuisine: str | None = None
    existence_source_url: str = Field(description="URL of a fetched page that shows this name and address together")
    multiple_locations_note: str | None = Field(
        default=None,
        description="Set ONLY if this name matches a chain/brand with more than one DC location and no "
        "neighborhood/cuisine hint was given to disambiguate — plain-English note telling the user which "
        "location was picked and that others exist (e.g. 'BIBIBOP has multiple DC locations; this is the "
        "Dupont Circle one — add a neighborhood to pick a different one.'). Leave null for a single-location "
        "restaurant, or when a hint already disambiguated which location to use.",
    )


class CandidateBatch(BaseModel):
    """Output of the Finder agent's discovery mode: a list of candidate
    restaurants found via a broad web search, not a single named lookup."""

    candidates: list[RestaurantCandidate]
    note: str | None = Field(default=None, description="e.g. explain if fewer candidates were found than expected")


class EvidenceClaim(BaseModel):
    """One claim found by the Evidence Extractor agent. `quote` must be a
    verbatim substring of text actually fetched from `source_url` — this is
    enforced in code (Step 5's source-grounding check), not just by prompt."""

    quote: str = Field(description="Verbatim quote from the source, not a paraphrase")
    source_url: str
    source_type: SourceType = Field(
        description="own_menu if from the restaurant's own site; third_party_aggregator for Yelp/Google/"
        "FindMeGlutenFree/TripAdvisor/blogs/Reddit/etc"
    )
    source_date: str | None = Field(
        default=None,
        description="Publish/post date of the source page as YYYY-MM-DD, if the page shows one. "
        "Never guessed — null if no date is actually visible on the page.",
    )
    topic: ClaimTopic
    direction: ClaimDirection


class EvidenceBatch(BaseModel):
    """Output of the Evidence Extractor agent for one restaurant."""

    claims: list[EvidenceClaim]
    note: str | None = Field(default=None, description="e.g. explain why evidence is thin, if it is")


class ReviewedClaim(BaseModel):
    """One EvidenceClaim after the Skeptic agent's review."""

    claim: EvidenceClaim
    is_promotional: bool = Field(description="True if the quote reads like marketing copy rather than a real account")
    is_contradicted: bool = Field(description="True if another claim in the same batch directly contradicts this one")
    skeptic_note: str = Field(description="One sentence explaining the flags above, or why there are none")


class ReviewedBatch(BaseModel):
    """Output of the Skeptic agent for one restaurant."""

    claims: list[ReviewedClaim]


SafetyLevel = Literal[
    # 1a — confirmed dedicated GF fryer/prep, from a credible source dated within 6 months of the search
    "confirmed_dedicated_gf_prep",
    # 1b — accommodates GF, but no recent/credible confirmation of a dedicated setup
    "accommodates_caution_cross_contamination",
    # 2 — accommodates allergies generally, nothing gluten-specific found
    "unclear_gluten_specific",
    # 3 — effectively nothing found either way
    "no_evidence_found",
    # 4 — most severe; overrides 1a/1b/2 whenever a credible got-sick claim exists
    "credible_illness_report",
]
ConfidenceLevel = Literal["low", "medium", "high"]


class SafetyAssessment(BaseModel):
    """Final output of the Ranker agent for one restaurant."""

    restaurant: RestaurantCandidate
    safety_level: SafetyLevel
    confidence: ConfidenceLevel
    supporting_claims: list[ReviewedClaim] = Field(
        description="EVERY credible, non-promotional reviewed claim with direction='positive' — not a curated "
        "highlight reel. If the own-site evidence and a third-party source (e.g. a review aggregator) both "
        "corroborate the same fact, include both; dropping a real corroborating source hides evidence from the "
        "user, even if it wasn't needed to reach the tier."
    )
    contradicting_claims: list[ReviewedClaim] = Field(
        description="EVERY credible, non-promotional reviewed claim with direction='negative' — same completeness "
        "requirement as supporting_claims."
    )
    short_summary: str = Field(
        description="ONE short, plain-English sentence for a results-list card — no internal rule names, no tier "
        "identifiers (e.g. never write 'accommodates_caution_cross_contamination'), no jargon like 'recency "
        "requirement'. Just what a diner needs to know at a glance."
    )
    rationale: str = Field(
        description="Fuller plain-language explanation for a detail page, must mention the tier rules if they "
        "changed the outcome — but still never use the raw tier identifier string, describe it in words instead"
    )
    override_applied: bool = Field(
        default=False, description="Set by code (not the model) if a backstop rule changed safety_level after the fact"
    )
    override_reason: str | None = Field(default=None, description="Set by code when override_applied is True")
