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

from app.harness.audit_log import estimate_cost_usd
from app.harness.input_guard import validate_search_input
from app.pipeline import AgentCapExceeded, PipelineResult, run_for_discovered_list, run_for_restaurant
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
        # obvious to type a specific restaurant). Uses run_for_restaurant
        # directly instead of discovery; neighborhood/cuisine (if given) are
        # passed through as a disambiguating hint, same as the CLI script.
        rejection = validate_search_input(restaurant_name, None, field_names=("Restaurant name", ""))
        if rejection:
            results, note, search_likely_failed, input_rejected = [], rejection, False, True
        else:
            hint = ", ".join(p for p in (neighborhood, cuisine) if p) or None
            try:
                result = await run_for_restaurant(restaurant_name, hint)
                results, note, search_likely_failed, input_rejected = [result], None, False, False
            except AgentCapExceeded as exc:
                results, note, search_likely_failed, input_rejected = [], f"Hit a cost/time limit: {exc}", True, False
            except Exception as exc:  # noqa: BLE001
                results, note, search_likely_failed, input_rejected = (
                    [],
                    f"Couldn't confirm this restaurant ({type(exc).__name__}): {exc}",
                    True,
                    False,
                )
    else:
        outcome = await run_for_discovered_list(neighborhood or None, cuisine or None, MAX_CANDIDATES)
        results, note, search_likely_failed, input_rejected = (
            outcome.results,
            outcome.note,
            outcome.search_likely_failed,
            outcome.input_rejected,
        )

    SEARCHES_STORE[search_id] = StoredSearch(
        results=results,
        note=note,
        search_likely_failed=search_likely_failed,
        input_rejected=input_rejected,
        restaurant_name=restaurant_name,
        neighborhood=neighborhood,
        cuisine=cuisine,
    )
    for r in results:
        RESULTS_STORE[r.run_log.run_id] = (r, search_id)
    # Redirect (not render directly) so the results page has its own URL —
    # refreshing it re-displays the same search instead of resubmitting the
    # form, and a detail page can link back to it by that URL.
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
        },
    )


@app.get("/restaurant/{run_id}", response_class=HTMLResponse)
async def restaurant_detail(request: Request, run_id: str):
    stored = RESULTS_STORE.get(run_id)
    if stored is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    result, search_id = stored
    return templates.TemplateResponse(request, "detail.html", {"result": result, "search_id": search_id})
