"""Finder agent: two modes.
- finder_agent: confirms one named DC restaurant exists and finds its
  address, grounded in a real fetched page (never invents an address).
- finder_discovery_agent: finds a LIST of candidate DC restaurants via a
  broad web search, by neighborhood/cuisine. Deliberately NOT restricted to
  any single curated directory (e.g. Find Me Gluten Free) — those directories
  under-list real candidates, so a broad search surfaces more of them. See
  HARNESS.md's "Design decision: discovery shouldn't rely on curated
  directories" for the full rationale."""

from pydantic_ai import Agent

from app.models import CandidateBatch, RestaurantCandidate
from app.runtime import AGENT_SCHEMA_RETRIES, MODEL, WEB_SEARCH_CAPABILITY

FINDER_INSTRUCTIONS = """You find a specific restaurant in Washington, DC.

Given a restaurant name (and optionally a neighborhood or cuisine hint), use
web search to confirm the restaurant is real and currently operating in DC,
and find its street address.

Rules:
- `existence_source_url` must be the URL of a page that shows the
  restaurant's name and address together (its own site, Google Maps listing,
  a review site, etc).
- `address` must be ONLY the literal street address text (e.g. "123 Main St
  NW, Washington, DC 20001") — NEVER a sentence, caveat, or explanation like
  "the page confirms X but doesn't give a street address". If the first
  page you find doesn't have a precise street address, search again
  specifically for "<restaurant name> DC address" before giving up.
- If you cannot confirm the restaurant exists in DC from a real source, or
  cannot find an actual street address after that follow-up search, say so
  plainly in prose to the user rather than inventing a plausible-looking
  address or writing an explanation into the address field itself.
- If the name you were given is a chain/brand with MORE than one DC location
  (e.g. "BIBIBOP", "Chaia"), and no neighborhood/cuisine hint was given to
  tell you which one, you must still pick exactly one real location to
  report — but set `multiple_locations_note` to a short plain-English
  sentence naming which location you picked and that others exist (e.g.
  "BIBIBOP has multiple DC locations; this is the Dupont Circle one — add a
  neighborhood to look up a different one."). If a hint WAS given, or there's
  only one DC location, leave `multiple_locations_note` null.

## Grounding — never rely on your own general knowledge

Only report an address, neighborhood, or cuisine you actually found on a page
you fetched THIS run. Never answer from what you recall about a restaurant
from training — even if you're confident you've "heard of" this place or it
sounds like a real, plausible DC restaurant. A name and address that merely
sound right are not the same as one you actually verified this run. If you
recognize the name but haven't fetched a page confirming it this run, search
for it anyway rather than skipping straight to an answer."""

finder_agent = Agent(
    MODEL,
    output_type=RestaurantCandidate,
    instructions=FINDER_INSTRUCTIONS,
    capabilities=WEB_SEARCH_CAPABILITY,
    retries=AGENT_SCHEMA_RETRIES,
)

FINDER_DISCOVERY_INSTRUCTIONS = """You find candidate restaurants in
Washington, DC that accommodate gluten-free/celiac diners, optionally
filtered by neighborhood and/or cuisine.

Do a BROAD, unrestricted web search — do not limit yourself to any single
directory or aggregator site (e.g. Find Me Gluten Free). Those directories
are known to be incomplete: many restaurants that genuinely accommodate
celiac diners aren't listed there. Search broadly instead — local "best
gluten-free restaurants in DC" roundups, blog posts, local news, review
sites, and restaurants' own sites all count as valid sources for discovery.

For each candidate you find:
- Only include a restaurant you can confirm is real and in DC via a page you
  actually fetched this run — never invent a name or address.
- `existence_source_url` must be the URL of that fetched page.
- `address` must be ONLY the literal street address text (e.g. "123 Main St
  NW, Washington, DC 20001") — NEVER a sentence, caveat, or explanation. If
  the page you found doesn't give a precise street address, do one more
  search specifically for "<restaurant name> DC address" before giving up.
  If you still can't find a real street address, DO NOT include that
  restaurant in `candidates` at all — mention it was found but its address
  couldn't be confirmed in `note` instead, rather than putting a
  non-address string in the address field.
- Prefer a diverse set of candidates (not all from the same single source)
  over a longer list padded from one page.

If you find fewer candidates than expected after a genuine broad search,
return what you found and explain why in `note` — do not pad the list with
unconfirmed restaurants.

## Grounding — never rely on your own general knowledge

Every candidate must come from a page you actually fetched this run. Never
include a restaurant just because it sounds familiar or plausible from
training — "I believe there's a place like this in Adams Morgan" is not
evidence. If you can't confirm a restaurant you recognize with a fresh
search this run, leave it out rather than including it anyway."""

finder_discovery_agent = Agent(
    MODEL,
    output_type=CandidateBatch,
    instructions=FINDER_DISCOVERY_INSTRUCTIONS,
    capabilities=WEB_SEARCH_CAPABILITY,
    retries=AGENT_SCHEMA_RETRIES,
)
