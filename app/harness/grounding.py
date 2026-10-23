"""Source grounding: a claim's verbatim quote must actually appear in text
fetched from its source_url THIS run — not just trusted because the model
said so. Re-fetches independently of whatever the agent's web search tool
saw, and drops any claim that doesn't verify. Also verifies a restaurant's
name+address actually appear together on its existence_source_url page.

This is deliberately a separate, independent fetch (plain HTTP + our own
text extraction), not a check against whatever the agent's builtin web
search tool happened to see — the whole point is not to trust the agent's
own account of what a page said."""

import re
import unicodedata
from io import BytesIO

import requests

FETCH_TIMEOUT_SECONDS = 15
USER_AGENT = "Mozilla/5.0 (compatible; CeliacSafeDCRankerBot/1.0; +grounding-check)"


def fetch_text(url: str) -> str | None:
    """Fetches a URL and returns its best-effort plain text, or None if it
    couldn't be fetched/parsed. Handles HTML and PDF explicitly."""
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except Exception:  # noqa: BLE001 — any fetch failure means "can't verify", not a crash
        return None

    content_type = resp.headers.get("content-type", "").lower()
    if "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf"):
        return _extract_pdf_text(resp.content)
    return _strip_html(resp.text)


def _extract_pdf_text(content: bytes) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        return " ".join(page.extract_text() or "" for page in reader.pages)
    except Exception:  # noqa: BLE001
        return None


def _strip_html(html: str) -> str:
    import html as html_module

    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize(text: str) -> str:
    """Normalizes whitespace and smart quotes so a verbatim comparison isn't
    broken by curly quotes, line breaks, or incidental spacing differences —
    the quote still has to be a real substring, just not byte-for-byte
    identical on cosmetic punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = (
        text.replace("‘", "'")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )
    text = re.sub(r"\s+", " ", text).strip().lower()
    # PDF text extraction (e.g. pypdf on a column-laid-out menu) routinely
    # inserts a space before punctuation that isn't there in the rendered
    # PDF a human reads (observed: "shore-nakhot : chickpea" vs. the quote's
    # "shore-nakhot: chickpea") — collapse it so a real, accurate quote from
    # a PDF source isn't wrongly rejected as "not grounded".
    return re.sub(r"\s+([:,.;)])", r"\1", text)


def quote_is_grounded(quote: str, fetched_text: str) -> bool:
    return _normalize(quote) in _normalize(fetched_text)


def verify_claims_grounded(claims):
    """Returns (grounded, dropped) lists. Re-fetches each unique source_url
    once (claims sharing a source only cost one fetch), then checks every
    claim's quote against that page's real text."""
    cache: dict[str, str | None] = {}
    grounded, dropped = [], []
    for c in claims:
        if c.source_url not in cache:
            cache[c.source_url] = fetch_text(c.source_url)
        text = cache[c.source_url]
        if text is not None and quote_is_grounded(c.quote, text):
            grounded.append(c)
        else:
            dropped.append(c)
    return grounded, dropped


def restaurant_existence_grounded(restaurant) -> bool:
    """Verifies the restaurant's name and street number actually appear on
    its existence_source_url page, independent of the Finder agent's own
    claim that it confirmed this.

    Matches only the CORE name (before any " — location" / " - location"
    disambiguator the Finder appends for display, e.g. "BIBIBOP Asian Grill
    — Dupont Circle") — a real page states its own name and the
    neighborhood separately, often in a different order, so requiring the
    full compound string as one contiguous substring produces false
    negatives on real, correctly-identified restaurants (see FAILURES.md)."""
    text = fetch_text(restaurant.existence_source_url)
    if text is None:
        return False
    normalized = _normalize(text)
    core_name = re.split(r"\s[—-]\s", restaurant.name)[0].strip()
    name_ok = _normalize(core_name) in normalized
    street_number_match = re.match(r"\s*(\d+)", restaurant.address)
    address_ok = street_number_match is None or street_number_match.group(1) in normalized
    return name_ok and address_ok
