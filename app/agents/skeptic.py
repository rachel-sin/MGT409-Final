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
- is_promotional: does it read like unverifiable marketing puffery — vague
  superlatives or reassurances with nothing concrete behind them ("we take
  gluten free seriously!", "best GF options in DC", "you can eat here worry
  -free")? A short claim is NOT automatically promotional just because it's
  short or lacks elaboration: a plain, specific, falsifiable factual
  statement ("our entire menu is gluten-free," "we have a dedicated
  gluten-free fryer") is a real, checkable account even with no further
  detail, and should NOT be flagged as promotional. Judge the claim's
  substance, not its length.
- is_contradicted: does another claim in this same batch assert the opposite
  FACT about the restaurant's own practice/policy (e.g. one source says
  "dedicated fryer," another says "fried in the same oil as regular food" —
  those can't both be true, so they're contradicted)? Two different reviewers
  having two different personal OUTCOMES is NOT a contradiction — one diner
  getting sick and a separate diner having no symptoms are both perfectly
  possible at the very same restaurant (inconsistent handling, human error,
  different orders) and do not cancel each other out. Never mark a
  reviewer_got_sick claim contradicted just because another, different
  reviewer reported being fine — only mark it contradicted if a claim
  conflicts with that SAME account (e.g. the same review elsewhere says they
  had no symptoms).
- skeptic_note: one plain sentence explaining your flags, or why there are
  none.

Be skeptical of vague or unverifiable claims by default, but don't conflate
"vague" with "lacks elaboration." A concrete factual claim stands on its own
even without supporting detail — only flag it if it's actually puffery, or
actually contradicted.

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
