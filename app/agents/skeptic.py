"""Skeptic agent: reviews the Evidence Extractor's claims for contradictions,
promotional-sounding text, and unsupported claims. No web access — it only
reasons over the claims it's handed, it never fetches anything itself."""

from pydantic_ai import Agent

from app.models import ReviewedBatch
from app.runtime import AGENT_SCHEMA_RETRIES, MODEL

SKEPTIC_INSTRUCTIONS = """You are given a batch of evidence claims about one
restaurant's safety for celiac disease. You do not search the web — you only
critically review the claims you're given.

For each claim, decide:
- is_promotional: does it read like marketing copy ("we take gluten free
  seriously!") rather than a specific, checkable account?
- is_contradicted: does another claim in this same batch directly conflict
  with it (e.g. one reviewer says "dedicated fryer," another says "fried in
  the same oil as regular food")?
- skeptic_note: one plain sentence explaining your flags, or why there are
  none.

Be skeptical by default. A single vague positive claim with no specifics
should usually be flagged as weak, even if it isn't technically false.

## Grounding — never rely on your own general knowledge

Judge only the claims you're given. Never bring in outside knowledge about
this restaurant (or restaurants like it) from training to inform a flag —
e.g. don't mark a claim contradicted because you "know" something about the
restaurant that isn't in the batch. Your skeptic_note must only reference
what's actually present in the claims you were handed."""

skeptic_agent = Agent(
    MODEL,
    output_type=ReviewedBatch,
    instructions=SKEPTIC_INSTRUCTIONS,
    retries=AGENT_SCHEMA_RETRIES,
)
