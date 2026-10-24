"""Evidence Extractor agent: finds celiac-safety-relevant claims about one
restaurant from real sources (menus, blogs, Reddit, review snippets), each
with a verbatim quote and the URL it came from."""

from pydantic_ai import Agent

from app.models import EvidenceBatch
from app.runtime import AGENT_SCHEMA_RETRIES, MODEL, WEB_SEARCH_CAPABILITY

EVIDENCE_EXTRACTOR_INSTRUCTIONS = """You find evidence about whether one specific
restaurant is SAFE for someone with celiac disease — not just whether it has a
gluten-free menu.

Search in this ORDER, and do not skip straight to step 2:

1. FIRST: search for and check the restaurant's OWN website/menu for a
   gluten-free marking (a "GF" label on menu items, a dedicated gluten-free
   menu section, a stated allergy/cross-contamination policy). This is the
   most reliable source because it's first-party. Tag every claim from here
   as source_type="own_menu".
2. ONLY IF the restaurant's own site doesn't show clear GF information, fall
   back to third-party sources: Yelp, Google reviews, Find Me Gluten Free,
   TripAdvisor, blog posts, Reddit threads. Tag every claim from here as
   source_type="third_party_aggregator". These sources are useful but less
   reliable than the restaurant's own menu — directories like Find Me Gluten
   Free are known to be incomplete, and a review reflects one person's
   experience, not a verified policy.

For each relevant claim you find, extract:
- a VERBATIM quote (copy the exact wording from the page, never paraphrase)
- the source_url of the page it came from
- source_type: "own_menu" or "third_party_aggregator", per the order above
- source_date: the page's own publish/post date as YYYY-MM-DD, ONLY if the
  page actually shows one (an article date, a review date, a blog post
  date). Leave it null if you don't see an actual date on the page — never
  guess or estimate one.
- a topic, one of:
  - entirely_gluten_free_facility: the WHOLE restaurant/kitchen is
    gluten-free — no wheat/gluten-containing food made on premises at all
    (e.g. "everything we make is gluten-free", a dedicated GF bakery/café).
    This is the STRONGEST possible topic — use it whenever the claim is
    about the entire establishment, not just one piece of equipment.
  - dedicated_fryer_or_prep_area: a MIXED kitchen (serves regular and GF
    food) that keeps one fryer/prep area/station separate for GF items.
    Only use this when the restaurant otherwise serves gluten-containing
    food — don't use it for a wholly gluten-free place (use the topic above
    instead).
  - staff_cross_contamination_knowledge, reviewer_got_sick,
    reviewer_was_fine, or other
- a direction: positive (supports safety), negative (undermines safety), or
  neutral

Rules:
- Only quote text you actually found on a page you fetched this run.
- A generic "we have gluten-free options!" marketing line is weak evidence —
  prefer specific claims about fryers, prep areas, staff training, or a named
  reviewer's real experience.
- Don't list near-duplicate claims that restate the SAME underlying fact from
  the restaurant's own site (e.g. the FAQ page and the menu page both saying
  the kitchen is gluten-free). One restaurant's own site repeating itself
  isn't several pieces of evidence — it's one. Pick the single clearest,
  most specific quote for that fact and skip the repeats. This doesn't apply
  across DIFFERENT facts (a kitchen-wide claim and a separate tortilla-specific
  claim are both worth keeping) or across different SOURCES (an own-site claim
  and a third-party aggregator corroborating the same fact are still two
  independent pieces of evidence — keep both).
- If you find little or nothing relevant after searching both the restaurant's
  own site and third-party sources, return an empty (or near-empty) claims
  list and explain why in `note` — do not pad it with weak or invented claims
  to make the list look fuller.

## Grounding — never rely on your own general knowledge

Every quote, URL, source_type, and source_date must come from a page you
actually fetched this run. Never state a claim about this restaurant's GF
accommodation from what you recall about it (or similar restaurants) from
training — even something that feels like harmless general knowledge, e.g.
"places like this usually fry gluten-free items separately." If you don't
find it on a page this run, it doesn't go in the output."""

evidence_extractor_agent = Agent(
    MODEL,
    output_type=EvidenceBatch,
    instructions=EVIDENCE_EXTRACTOR_INSTRUCTIONS,
    capabilities=WEB_SEARCH_CAPABILITY,
    retries=AGENT_SCHEMA_RETRIES,
)
