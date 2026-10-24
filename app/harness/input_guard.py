"""Input guard: queries must be short, real neighborhood/cuisine filters —
not a vector for prompt injection or arbitrary off-topic text. Enforced in
code before any agent is ever called, per the project's "enforce rules in
code, not only in prompts" principle.

Note on scope: the city is never user-controlled — every prompt in this app
hardcodes "Washington, DC" regardless of what the user types, so "must be
about DC" is already structurally guaranteed. The real risk this guard
targets is a neighborhood/cuisine field being used to smuggle in injected
instructions or unrelated prose, not a user literally asking about Chicago."""

import re

MAX_FILTER_LENGTH = 60  # a real neighborhood or cuisine name is always short

# Phrases indicative of an attempted instruction/injection, not a real
# neighborhood or cuisine name. Not exhaustive — this is one layer among
# several (grounding rules, the Skeptic, the output scanner), not the only
# line of defense.
INJECTION_MARKERS = [
    "ignore",
    "disregard",
    "system prompt",
    "you are now",
    "developer mode",
    "new instructions",
    "override",
    "jailbreak",
]


def validate_search_input(
    neighborhood: str | None,
    cuisine: str | None,
    field_names: tuple[str, str] = ("Neighborhood", "Cuisine"),
    max_length: int = MAX_FILTER_LENGTH,
) -> str | None:
    """Returns a user-facing rejection message if the input should be
    blocked, or None if it's fine to proceed. Reused beyond the search form
    (e.g. the feedback form's free-text fields, the restaurant-name field
    with a longer max_length) — pass field_names to get an accurate label in
    the rejection message for those cases."""
    for field_name, value in zip(field_names, (neighborhood, cuisine)):
        if not value:
            continue
        if len(value) > max_length:
            return (
                f"{field_name} looks too long to be a real neighborhood or cuisine name "
                f"(max {max_length} characters) — please enter something shorter."
            )
        lowered = value.lower()
        hit = next((m for m in INJECTION_MARKERS if m in lowered), None)
        if hit:
            return (
                f"{field_name} contains text ({hit!r}) that looks like an attempted instruction rather "
                "than a real neighborhood or cuisine — please rephrase."
            )
        if not re.search(r"[a-zA-Z]", value):
            return f"{field_name} doesn't look like a real neighborhood or cuisine name."
    return None
