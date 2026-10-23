# AI Prompts — Final Project (Celiac-Safe DC Restaurant Ranker)

Every prompt used to build this, logged verbatim (or summarized with the reason follow-ups were needed), step by step, matching the step numbers in `HARNESS.md`.

## Step 0 — Scope-check the brief against the official rubric

### Prompts used

1. > hi, lets start the final project for this. lets make a new folder called final project
2. > ok heres the prompt for now - dont build yet. read and let me know your thoughts. repeat back to me what u think our goal is at a high level
   > [full project brief: celiac-safe DC restaurant ranker, 4 PydanticAI agents (Finder, Evidence extractor, Skeptic, Ranker), gpt-6-luna via Portkey, code-level harness requirements, HARNESS.md/FAILURES.md, build order, timeline through Mon Oct 26]
3. > ok regardless this is what we're building: https://zlisto.github.io/mgt_409_fa26/project_requirements.html — did my prompt meet the ask?

### Follow-up summary

Read the full brief and restated the high-level goal before any building: this is less "build a restaurant app" and more "demonstrate a multi-agent system a manager could trust," where the evidence-quote-URL requirement and code-level harness are the actual graded content. Flagged upfront risks (web-search feasibility as a real go/no-go gate, the harness requirements being the biggest time sink) without building anything yet, per the explicit "don't build yet" instruction.

Fetched the official rubric page and compared it line by line against the brief: the report-section order, model/env constraints, 10-minute fresh-clone rule, and cached-dataset requirement all matched closely. Found two real gaps — the brief never mentioned the required GitHub repo deliverable (public, or private + `zlisto` as collaborator) or a `.gitignore`/clean-repo expectation, and the Tokenomics section's required per-user-month and 100-/10,000-user cost projections weren't explicitly called for (only "real token counts" was). Confirmed the idea itself isn't on the "overdone ideas" cap list, so it isn't pre-capped at Tier 1.

### Follow-up: pivot question and dataset confusion

1. > what if we pivot to something that doesnt need a live database? seems like that would be a problem
2. > ok regardless this is what we're building... did my prompt meet the ask? (see above)
3. > i dont have a json though?

### Follow-up summary

Clarified that no pivot was needed: the brief's "cached dataset" and "per-restaurant cache" requirements are flat JSON files, not a database server, and nothing in the brief requires a running DB process — this was already compatible with the 10-minute fresh-clone / no-unusual-dependencies constraint. Separately clarified that the ~20-restaurant JSON dataset isn't something the student needs to supply — it's generated as Step 6's output, by running the finished agent pipeline against real restaurants and saving the result, not hand-written or scraped in advance.

### Follow-up: planning the whole project, closing the tokenomics gap

1. > ok can you come up with a step by step that closes this gap. and we can talk through how to build step by step and iterate with each step too
2. > well we can make it all local and then i can upload to github later. i more meant a step by step plan to the whole project, and in this new plan include a way to fix the tokenomics scale projection gap

### Follow-up summary

Proposed a 12-step plan (local git now, GitHub push deferred) with a dedicated step for the tokenomics scale projection (pulling real per-agent token counts from audit logs already produced in earlier steps, then computing cost per run → per user/month → at 100 and 10,000 users, with assumptions spelled out) rather than leaving it as an afterthought in report-writing.

### Follow-up: matching HW5's actual build process

1. > wait im ngl can you look at hw 5 and see how built that? becuase i feel like this this reads really differently
2. > yeah go ahead

### Follow-up summary

Read `Homework/5/README.md`, `AI_prompts.md`, and `output/design.md`/`harness.md` directly rather than assuming. Found the plan I'd proposed was structurally different from how HW5 was actually built: HW5 worked one small decision at a time (not batched steps), logged every prompt verbatim in its own `AI_prompts.md`, grew `harness.md` continuously rather than writing docs at the end, verified everything statically (`py_compile`, direct imports, scratch-copy tests) before ever calling the live API, and had the student draft subjective content (agent prompts, UI direction) first with gap-checks rather than having it generated wholesale. Proposed adopting that process here while keeping the Step 0-11 list as a sequencing reference, not a rigid pre-approved batch plan. Confirmed this approach, then began Step 1: created this file and `HARNESS.md`, and wrote (but per the build order, did not yet run) `scripts/test_web_access.py`.

While writing the script, checked the installed `pydantic_ai` (2.50.0) API directly rather than assuming from memory or HW5's pattern (which never used web search) — found `Agent(..., builtin_tools=[...])` doesn't exist in this version; the real API is `Agent(model, capabilities=[NativeTool(WebSearchTool())])` with an `OpenAIResponsesModel` (web search requires the Responses API, not Chat Completions — confirmed directly from the package's own bundled `NATIVE-TOOLS.md` reference doc rather than guessing). Fixed the script to match, then statically verified it constructs correctly with a fake API key (no live call made) before stopping, per the plan.

### Follow-up: running the test live

1. > Yes, run the web access test now.

### Follow-up summary

First live run failed on both approaches with a connection error. Diagnosed rather than guessed: isolated the exact same HTTPS request via `curl` and Python's `requests` library, both of which succeeded immediately with a real 200 response — proving the Portkey/Azure backend itself was fine, and the failure was specific to the `openai` package's own `httpx2` transport (its default TLS verification against macOS's native trust store doesn't work in this sandboxed dev setup). Fixed by constructing the shared `AsyncOpenAI` client with an explicit `http_client=httpx2.AsyncClient(verify=certifi.where())`. Re-ran: **both approaches now PASS** — real, dated (October 22, 2026), cited web-search results came back through both `pydantic_ai`'s `WebSearchTool` and the raw Responses API. Logged the full finding (including the environment quirk, in case it resurfaces during the grader's fresh-clone run) in `HARNESS.md`.

## Step 2 — Single restaurant, full 4-agent pipeline

### Prompts used

1. > yeah go for it

### Follow-up summary

Built `app/models.py` (shared Pydantic I/O types — `RestaurantCandidate`, `EvidenceBatch`/`EvidenceClaim`, `ReviewedBatch`/`ReviewedClaim`, `SafetyAssessment`), `app/runtime.py` (shared model/client, factored out of Step 1's test script including the certifi TLS fix), the 4 agent files in `app/agents/` (Finder + Evidence Extractor get live web search via `capabilities=[NativeTool(WebSearchTool())]`; Skeptic and Ranker get none, since they only reason over what they're handed), `app/pipeline.py` (sequential orchestration), and `scripts/run_single_restaurant.py`. Verified statically first — `py_compile` on every file, then imported and constructed all 4 agents plus the pipeline module (real `.env` present, but importing/constructing an `Agent` makes no network call) — before running anything live.

### Follow-up: picking a test restaurant, and a caught hallucination

1. > show me ur source for surfside georgetown, that doesnt make sense
2. > where are you "remembering" this from?
3. > is this something we should add to the harness regarding hallucations to make sure this doesnt happen again? eg, if the user searches a restaurant that doesnt exist, make sure it returns resturant not found?
4. > yes set up failures.md. and in terms of restaurants go with lapis

### Follow-up summary

Had proposed "Surfside — Georgetown, tacos, known in the celiac community" as the default test restaurant without any real source — a genuine ungrounded claim, caught immediately when asked for the source. Admitted directly that there was no retrievable source behind it (not a specific memory, just a plausible-sounding pattern from training — i.e., a real hallucination), rather than trying to defend or soften it.

Distinguished two different failure modes when asked whether to harden the harness against this: (1) an *agent* hallucinating a restaurant's existence/address inside a real pipeline run — already covered by the brief's planned Step 5 "restaurant existence check" code backstop, not a new addition; (2) what actually happened here — an ungrounded claim asserted in planning conversation, upstream of the pipeline entirely, which no in-app code check could ever catch since it never passed through Finder or any grounding logic. Proposed logging incident (2) as `FAILURES.md` entry #1 (process fix: test inputs named plainly with no attached claims) while leaving the Step 5 plan for (1) unchanged. Confirmed; created `FAILURES.md` and re-ran the Step 2 pipeline on "Lapis" (a real Adams Morgan, DC Afghan restaurant) with zero claims attached this time, letting Finder and the Evidence Extractor establish everything themselves.

Live run succeeded end to end: Finder confirmed Lapis's real address (1847 Columbia Road NW) via `lapisdc.com/contact`; Evidence Extractor pulled 8 verbatim, sourced quotes from `findmeglutenfree.com` and TripAdvisor (7 positive, 1 negative — "No GF fryer."); Skeptic reviewed all 8 and flagged none as promotional or contradicted; Ranker correctly landed on "not enough evidence" (medium confidence) rather than overclaiming safety, explicitly reasoning that the asymmetric risk rule didn't trigger (no uncontradicted "got sick" report) but that diner impressions alone, with no stated cross-contact protocol, still weren't enough for a "safe" call. Logged the full build and this run's results in `HARNESS.md`.

### Follow-up: own-menu-first evidence priority, and a diagram

1. > ok i think checking the restaurant own website/menu should come number one as thats the most reliable source of information. i think we can go to yelp/google/findmegf if the menu doesnt have that info. tldr i want this to scrape both restuarnt menus AND these aggregator sites to identify gf restaurants for me
2. > well i think the aggregator sites can both discover and verify?
3. > can you draw me a diagram explaining this flow?

### Follow-up summary

Confirmed the priority order (own menu first, aggregator fallback) for the Evidence Extractor, and clarified that Finder (discovery) and Evidence Extractor (verification) can share the same source pool (FindMeGlutenFree, Yelp, Google, TripAdvisor) just queried differently — Finder asks a broad "what GF restaurants exist in this area" question, Evidence Extractor asks a specific "what's the safety evidence for this one restaurant" question. Produced an SVG flowchart showing: filter → Finder (discover) → Evidence Extractor checks own menu → decision (GF marked?) → yes continues straight to evidence claims, no falls back to aggregator check → Skeptic → Ranker.

### Follow-up: aggregator directories are unreliable for discovery

1. > so my problem with existing aggregator websites (ie, find me gluten free) is that they are unreliable. there are so many more restaurants that accomodate gluten free than the ones they list, and search google for "gf restaurant" and looking at individual resturant menus usually works way better. based on this, how would you update the flow? i like the diagram a lot btw, lets incorporate the key into part of the diagram and see if we can fit it into the report somewhere

### Follow-up summary

A real, substantive correction to the Finder design, not just a wording tweak: curated GF directories (Find Me Gluten Free, etc.) under-list real candidates, and a broad web search plus checking individual restaurants' own menus directly surfaces more of them. Updated the plan so Finder does an **unrestricted broad web search** by neighborhood/cuisine rather than scraping any one aggregator's directory page — aggregator sites remain one possible source a broad search can surface, and a fallback signal during evidence verification (not the discovery mechanism itself). Logged this as a named design decision in `HARNESS.md`, including that it's genuine, honest material for the report's "What is new" section (Find Me Gluten Free's curated-database approach is also its coverage limitation; this system trades that for live broad search specifically to close the gap). Updated the flow diagram to reflect the corrected Finder behavior and added an in-diagram legend per request, for reuse in the report's "The agents" section. Saved the diagram as a self-contained `report_assets/agent_flow_diagram.svg` (hardcoded colors, no dependency on the app's own theme system) so it's ready to embed in `report.html` later.

### Follow-up: catching that only the docs/diagram had changed, not the code

1. > sorry i more meant updaitng the actual agent logic and not just the diagram itself. it does seem liek you did that though

### Follow-up summary

Correct catch — at that point only `HARNESS.md`/`AI_prompts.md` and the diagram had been updated; the actual agent code was unchanged. Fixed for real: added a `source_type` field (`"own_menu"` | `"third_party_aggregator"`) to `EvidenceClaim` in `app/models.py`, and rewrote `app/agents/evidence_extractor.py`'s actual prompt to enforce the search order in step-by-step instructions (own site/menu first; third-party sources only if the menu doesn't show clear GF info; explicit note that directories like Find Me Gluten Free are known to be incomplete). Statically verified (`py_compile` + agent re-construction) before stopping. Confirmed Finder's existing code needed no change, since its single-restaurant-confirmation mode already does a general web search rather than querying a directory — the directory-reliance risk is specific to Finder's not-yet-built discovery mode (Step 3).

## Step 3 — Finder discovery mode

### Prompts used

1. > yes rerun lapis, and is this something we shoudl log in failures? [continued from previous section]
2. > youre right lets have it for limits and next steps. lets continue otherwise

### Follow-up summary

Agreed to park the "save your own finds" feature idea in the report's Limits/next-steps section rather than build it now, given the timeline, and logged it as such in `HARNESS.md`. Then built Step 3: `CandidateBatch` model, a second Finder agent (`finder_discovery_agent`) doing a broad, unrestricted web search for candidate restaurants by neighborhood/cuisine (never scraping a single directory, per the earlier design decision), and `app.pipeline.run_for_discovered_list`/`discover_candidates` tying discovery into the existing 4-agent pipeline. Added a `max_candidates` stopgap bound (default 5, script default 3) ahead of real caps, anticipating this would be a bigger live test than prior single-restaurant runs. Statically verified before stopping.

### Follow-up: caps before running live

1. > shouldnt we write the cost/step caps before we run it?
2. > tell me what caps youre putting, and maybe look at the previus homeworks to see if any of those caps apply? (no making data up, timing out, etc.)

### Follow-up summary

Agreed — ran discovery live with zero caps would have been inconsistent with the project's own "enforce in code before trusting it" thesis. Checked `Homework/4` and `Homework/5` directly for patterns rather than inventing new ones from scratch. Added: a per-agent step cap (`AGENT_STEP_LIMIT = 8`, same value/mechanism as HW5's `backend/team.py`), a per-agent token cap (`AGENT_TOKEN_LIMIT = 20_000`, new beyond HW5 since web search pulls in much more text per step than HW5's DB lookups), a per-agent wall-clock timeout (60s via `asyncio.wait_for`, new since neither homework did open-ended web search), confirmed the existing HTTP client-level timeout+retry already matched HW4's `agent.py` pattern, and added HW4's exact graceful-degradation pattern (`except Exception` around a single restaurant's run, skip with a message instead of crashing the batch) to `run_for_discovered_list`. Also added an explicit `## Grounding — never rely on your own general knowledge` section to all 4 agent prompts, matching HW4/HW5's dedicated-heading convention, directly targeting the exact failure mode already caught once in this project (`FAILURES.md` #1, the Surfside hallucination) — now stated to the agents themselves. Confirmed the delegation-hop-cap/no-repeat-visits pattern from HW5 doesn't apply here (no delegation mesh — fixed linear pipeline), and that structural tool scoping is already satisfied (Skeptic/Ranker get zero web-search capability by construction). Named what's genuinely still missing (per-session caps, 30-day cache, fallback-to-cache, full audit log) as real Step 5 work, not an oversight. Statically verified (`py_compile` + direct import of the new cap constants and pipeline functions) before running anything live. Logged the full comparison in `HARNESS.md`.

### Follow-up: re-running Lapis, and logging the doc-vs-code gap as a failure

1. > yes rerun lapis, and is this something we shoudl log in failures?

### Follow-up summary

Re-ran the live Step 2 pipeline on Lapis with the fixed Evidence Extractor. Confirmed the fix is real, not just documented: the agent's own `note` field reported checking Lapis's own site/menu first (its official page lacked detail, but its Toast online-ordering menu marked one dish "(gf)") before falling back to Find Me Gluten Free and TripAdvisor, and every claim now carries a correct `source_type`. Final verdict stayed "not enough evidence," now grounded in the first-party menu signal plus a third-party "no dedicated fryer" report, rather than third-party impressions alone.

Agreed the doc-vs-code mismatch was worth logging and added it as `FAILURES.md` entry #2: the agreed own-menu-first design had been written into `HARNESS.md`/`AI_prompts.md` and the diagram, but not into the actual `EvidenceClaim` schema or the Evidence Extractor's prompt, until the user caught it. Framed explicitly as the same risk class the project's harness thesis is built on ("enforce rules in code, not only in prompts") showing up one level up, in the build process itself.

## Safety-level taxonomy redesign

### Prompts used

1. > ok i feel like "not enough evidence" isnt the right verdict - it shoud be that the restaurant can accomodate gluten allergy, proceed with caution re cross contamination
2. > no i think it should be 1) menu indiciates can accomodate gluten allergy, under which a) confirmed gf dedicated frier vs b) proceed with caution re cross contamination. or 2) evidence suggests ability to accomodate allergies, unclear on gluten specifically, recommend contact restaurant or 3) no evidence found supporting accomodating gluten allergy, sorry (lol but in nicer phrasing). does that make sense?
3. > i feel like got sick should get its own tier. tell me where you thin kit should fit — 1a i think a credible blogger is fine as long as the source is within the past 6 months of the date of the search
4. > that makes sense, implement

### Follow-up summary

Pointed out that "not enough evidence" was conflating two different situations for Lapis: genuinely thin evidence vs. real accommodation evidence with a specific identified caution. Proposed a 4-tier restructure organized around what's actually confirmed, rather than a generic safe/risky spectrum. Raised one open question before implementing: where does a credible got-sick report fit, since the proposed structure didn't have an explicit slot for it, and the brief's asymmetric-risk rule needs one. User placed it as its own highest-priority tier, overriding everything else, and set the rule for 1a: a credible blogger's claim counts, but only if dated within 6 months of the search date.

Implemented: `app/models.py`'s `SafetyLevel` is now 5 tiers in priority order (`credible_illness_report` > `confirmed_dedicated_gf_prep` > `accommodates_caution_cross_contamination` > `unclear_gluten_specific` > `no_evidence_found`), plus a new `source_date` field on `EvidenceClaim` (never guessed, null if the page shows no date) — which also happens to satisfy the brief's not-yet-built "recency weighting" harness requirement. Rewrote `app/agents/ranker.py`'s prompt for the new priority-ordered tier logic, and added a genuine code-level backstop (`app/pipeline.py`'s `apply_safety_backstops`) that independently re-checks the two rules that matter most — the illness-report override and the 6-month recency requirement — and corrects the model's output if it got it wrong, tagging `override_applied`/`override_reason` so the correction is visible. This is deliberately built as a backstop, not a replacement for getting the prompt right, per the project's "enforce rules in code, not only in prompts" principle (and per `FAILURES.md` #2, now applying that principle to the build process too).

Verified with 5 unit tests against fake data before any live call: credible got-sick overrides an optimistic tier; a contradicted got-sick claim does not override; a stale (>6mo) dedicated-fryer claim gets downgraded; a recent one is left alone; an undated claim never qualifies for tier 1. All 5 passed. Re-ran the live pipeline on Lapis: result changed from "not enough evidence" to `accommodates_caution_cross_contamination` (medium confidence) — the Ranker itself correctly applied the recency rule in its own reasoning this time, with the code backstop available as a safety net (proven to work via the unit tests) rather than needing to intervene on this particular run. Logged the full redesign in `HARNESS.md`.
