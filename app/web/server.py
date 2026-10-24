"""Step 4: minimal server-rendered UI. FastAPI + Jinja2 — no separate Node
setup. Run with: python3 -m uvicorn app.web.server:app --reload --port 8000
(from the final project/ root, so app.* imports resolve)."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.harness.audit_log import RunLog, estimate_cost_usd
from app.harness.input_guard import validate_search_input
from app.models import RestaurantCandidate
from app.pipeline import (
    SAFETY_LEVEL_RANK_ORDER,
    AgentCapExceeded,
    PipelineResult,
    _run_evidence_to_assessment,
    resolve_restaurant,
    run_for_discovered_list,
)
from app.web.labels import confidence_dots, safety_class, safety_icon, safety_label

BASE_DIR = Path(__file__).resolve().parent

# Neighborhoods the discovery pipeline has actually been run against (Step 6's
# cached-dataset build) — a dropdown rather than free text, since an
# unvalidated neighborhood name is more likely to come back empty. Users can
# request others via the suggestion form below instead of guessing at
# phrasing that might not match anything.
SUPPORTED_NEIGHBORHOODS = [
    "Adams Morgan",
    "Capitol Hill",
    "Cleveland Park",
    "Dupont Circle",
    "Foggy Bottom",
    "Georgetown",
    "H Street NE",
    "Logan Circle",
    "Mount Vernon Triangle",
    "Navy Yard",
    "Petworth",
    "Shaw",
    "U Street",
    "Chinatown",
]

NEIGHBORHOOD_SUGGESTIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "neighborhood_suggestions.json"
USER_FEEDBACK_PATH = Path(__file__).resolve().parents[2] / "data" / "user_feedback.json"

app = FastAPI(title="Celiac-Safe DC Restaurant Ranker")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["safety_label"] = safety_label
templates.env.filters["safety_class"] = safety_class
templates.env.filters["safety_icon"] = safety_icon
templates.env.filters["confidence_dots"] = confidence_dots
templates.env.filters["estimate_cost_usd"] = estimate_cost_usd


@dataclass
class StoredSearch:
    results: list[PipelineResult]
    note: str | None
    search_likely_failed: bool
    input_rejected: bool
    restaurant_name: str
    neighborhood: str
    cuisine: str


# In-memory stores for this process's lifetime only — no database yet (Step 6
# adds the cached dataset). Enough to give each search its own URL (so a
# detail page can link back to the exact result set it came from, and a
# refresh doesn't resubmit the search form) and let a detail page look up
# the restaurant it belongs to.
SEARCHES_STORE: dict[str, StoredSearch] = {}
RESULTS_STORE: dict[str, tuple[PipelineResult, str]] = {}  # run_id -> (result, search_id)


@dataclass
class PendingConfirmation:
    restaurant: RestaurantCandidate
    run_log: RunLog
    neighborhood: str
    cuisine: str


# "Did you mean X?" confirm step (FAILURES.md #18): a named-restaurant search
# resolves the name via the Finder ALONE first (cheap, one call) and waits
# for the user to confirm before running the costlier evidence/skeptic/
# ranker calls on what might be the wrong restaurant for an ambiguous name.
PENDING_STORE: dict[str, PendingConfirmation] = {}

MAX_CANDIDATES = 3  # kept small — each candidate is a real, slow, costly live run


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"neighborhoods": SUPPORTED_NEIGHBORHOODS})


@app.post("/suggest-neighborhood", response_class=HTMLResponse)
async def suggest_neighborhood(request: Request, suggested_neighborhood: str = Form("")):
    rejection = validate_search_input(suggested_neighborhood, None)
    context = {"neighborhoods": SUPPORTED_NEIGHBORHOODS}
    if rejection:
        context["suggestion_error"] = rejection
        return templates.TemplateResponse(request, "index.html", context)

    NEIGHBORHOOD_SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if NEIGHBORHOOD_SUGGESTIONS_PATH.exists():
        existing = json.loads(NEIGHBORHOOD_SUGGESTIONS_PATH.read_text())
    existing.append({"neighborhood": suggested_neighborhood, "suggested_at": datetime.now(timezone.utc).isoformat()})
    NEIGHBORHOOD_SUGGESTIONS_PATH.write_text(json.dumps(existing, indent=2))

    context["suggestion_thanks"] = suggested_neighborhood
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_form(request: Request):
    return templates.TemplateResponse(request, "feedback.html", {})


@app.post("/feedback", response_class=HTMLResponse)
async def submit_feedback(
    request: Request,
    restaurant_tried: str = Form(""),
    matched_experience: str = Form(""),
    usual_time_minutes: str = Form(""),
    app_time_minutes: str = Form(""),
    trust_rating: str = Form(""),
    comment: str = Form(""),
):
    # Reuse the existing input guard on the two free-text fields — same
    # injection-protection standard as every other form in this app.
    rejection = validate_search_input(
        restaurant_tried, None, field_names=("Restaurant", "")
    ) or validate_search_input(comment[:60], None, field_names=("Comment", ""))
    if rejection:
        return templates.TemplateResponse(request, "feedback.html", {"error": rejection})

    USER_FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if USER_FEEDBACK_PATH.exists():
        existing = json.loads(USER_FEEDBACK_PATH.read_text())
    existing.append(
        {
            "restaurant_tried": restaurant_tried,
            "matched_experience": matched_experience,
            "usual_time_minutes": usual_time_minutes,
            "app_time_minutes": app_time_minutes,
            "trust_rating": trust_rating,
            "comment": comment,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    USER_FEEDBACK_PATH.write_text(json.dumps(existing, indent=2))

    return templates.TemplateResponse(request, "feedback.html", {"submitted": True})


@app.post("/search")
async def search(restaurant_name: str = Form(""), neighborhood: str = Form(""), cuisine: str = Form("")):
    search_id = uuid.uuid4().hex[:8]

    if restaurant_name:
        # Named-restaurant lookup (found missing in Step 9's real user test —
        # the form only had neighborhood/cuisine, so a tester had nowhere
        # obvious to type a specific restaurant). Resolves the name via the
        # Finder ALONE first (resolve_restaurant), then shows a "did you
        # mean X?" confirm step (FAILURES.md #18) before spending the
        # costlier evidence/skeptic/ranker calls on what a short/ambiguous
        # name might have mismatched. neighborhood/cuisine (if given) are
        # passed through as a disambiguating hint.
        rejection = validate_search_input(restaurant_name, None, field_names=("Restaurant name", ""), max_length=120)
        if rejection:
            SEARCHES_STORE[search_id] = StoredSearch(
                results=[],
                note=rejection,
                search_likely_failed=False,
                input_rejected=True,
                restaurant_name=restaurant_name,
                neighborhood=neighborhood,
                cuisine=cuisine,
            )
            return RedirectResponse(f"/results/{search_id}", status_code=303)

        hint = ", ".join(p for p in (neighborhood, cuisine) if p) or None
        try:
            restaurant, run_log = await resolve_restaurant(restaurant_name, hint)
        except AgentCapExceeded as exc:
            note = f"Hit a cost/time limit: {exc}"
            search_likely_failed = True
        except Exception as exc:  # noqa: BLE001
            note = f"Couldn't confirm this restaurant ({type(exc).__name__}): {exc}"
            search_likely_failed = True
        else:
            pending_id = uuid.uuid4().hex[:8]
            PENDING_STORE[pending_id] = PendingConfirmation(
                restaurant=restaurant, run_log=run_log, neighborhood=neighborhood, cuisine=cuisine
            )
            return RedirectResponse(f"/confirm/{pending_id}", status_code=303)

        SEARCHES_STORE[search_id] = StoredSearch(
            results=[],
            note=note,
            search_likely_failed=search_likely_failed,
            input_rejected=False,
            restaurant_name=restaurant_name,
            neighborhood=neighborhood,
            cuisine=cuisine,
        )
        return RedirectResponse(f"/results/{search_id}", status_code=303)

    outcome = await run_for_discovered_list(neighborhood or None, cuisine or None, MAX_CANDIDATES)
    SEARCHES_STORE[search_id] = StoredSearch(
        results=outcome.results,
        note=outcome.note,
        search_likely_failed=outcome.search_likely_failed,
        input_rejected=outcome.input_rejected,
        restaurant_name=restaurant_name,
        neighborhood=neighborhood,
        cuisine=cuisine,
    )
    for r in outcome.results:
        RESULTS_STORE[r.run_log.run_id] = (r, search_id)
    # Redirect (not render directly) so the results page has its own URL —
    # refreshing it re-displays the same search instead of resubmitting the
    # form, and a detail page can link back to it by that URL.
    return RedirectResponse(f"/results/{search_id}", status_code=303)


@app.get("/confirm/{pending_id}", response_class=HTMLResponse)
async def confirm_restaurant(request: Request, pending_id: str):
    pending = PENDING_STORE.get(pending_id)
    if pending is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(request, "confirm.html", {"restaurant": pending.restaurant, "pending_id": pending_id})


@app.post("/confirm/{pending_id}")
async def confirm_restaurant_submit(pending_id: str):
    pending = PENDING_STORE.pop(pending_id, None)
    search_id = uuid.uuid4().hex[:8]
    if pending is None:
        SEARCHES_STORE[search_id] = StoredSearch(
            results=[],
            note="This confirmation link has expired — please search again.",
            search_likely_failed=True,
            input_rejected=False,
            restaurant_name="",
            neighborhood="",
            cuisine="",
        )
        return RedirectResponse(f"/results/{search_id}", status_code=303)

    try:
        result = await _run_evidence_to_assessment(pending.restaurant, pending.run_log)
        results, note, search_likely_failed = [result], None, False
    except AgentCapExceeded as exc:
        results, note, search_likely_failed = [], f"Hit a cost/time limit: {exc}", True
    except Exception as exc:  # noqa: BLE001
        results, note, search_likely_failed = [], f"Couldn't evaluate this restaurant ({type(exc).__name__}): {exc}", True

    SEARCHES_STORE[search_id] = StoredSearch(
        results=results,
        note=note,
        search_likely_failed=search_likely_failed,
        input_rejected=False,
        restaurant_name=pending.restaurant.name,
        neighborhood=pending.neighborhood,
        cuisine=pending.cuisine,
    )
    for r in results:
        RESULTS_STORE[r.run_log.run_id] = (r, search_id)
    return RedirectResponse(f"/results/{search_id}", status_code=303)


@app.post("/search/{search_id}/more")
async def search_more(search_id: str):
    stored = SEARCHES_STORE.get(search_id)
    if stored is None or stored.restaurant_name:
        # "Show more" only applies to a neighborhood/cuisine browse, not a
        # named lookup (there's only ever one restaurant to show for that).
        return RedirectResponse(f"/results/{search_id}", status_code=303)

    already_shown = [r.restaurant.name for r in stored.results]
    already_shown_slugs = {n.strip().lower() for n in already_shown}
    outcome = await run_for_discovered_list(
        stored.neighborhood or None, stored.cuisine or None, MAX_CANDIDATES, exclude_names=already_shown
    )
    # The exclusion above is just a prompt instruction to the Finder (best
    # effort, not guaranteed) — also filter case-insensitively ourselves so
    # a near-duplicate name doesn't sneak a repeat into the list.
    new_results = [r for r in outcome.results if r.restaurant.name.strip().lower() not in already_shown_slugs]
    combined = stored.results + new_results
    combined.sort(key=lambda r: SAFETY_LEVEL_RANK_ORDER.index(r.assessment.safety_level))
    stored.results = combined
    if not new_results and not stored.note:
        stored.note = outcome.note or "No further new restaurants were found for this search."
    for r in new_results:
        RESULTS_STORE[r.run_log.run_id] = (r, search_id)

    return RedirectResponse(f"/results/{search_id}", status_code=303)


@app.get("/results/{search_id}", response_class=HTMLResponse)
async def results(request: Request, search_id: str):
    stored = SEARCHES_STORE.get(search_id)
    if stored is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "results": stored.results,
            "note": stored.note,
            "search_likely_failed": stored.search_likely_failed,
            "input_rejected": stored.input_rejected,
            "restaurant_name": stored.restaurant_name,
            "neighborhood": stored.neighborhood,
            "cuisine": stored.cuisine,
            "max_candidates": MAX_CANDIDATES,
            "search_id": search_id,
        },
    )


@app.get("/restaurant/{run_id}", response_class=HTMLResponse)
async def restaurant_detail(request: Request, run_id: str):
    stored = RESULTS_STORE.get(run_id)
    if stored is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    result, search_id = stored
    return templates.TemplateResponse(request, "detail.html", {"result": result, "search_id": search_id})
