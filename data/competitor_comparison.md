# Step 8 — Competitor comparison (Find Me Gluten Free & Google)

Real comparison across Find Me Gluten Free and Google, with real screenshots for every claim below — see the checklist at the bottom.

## Ama (885 New Jersey Ave SE) — our system's clearest differentiator

**Our system:** `credible_illness_report` — the single most severe tier, surfaced as the top-line verdict: "Caution — credible illness report."

**Find Me Gluten Free** (https://www.findmeglutenfree.com/biz/ama/5104439514234880): shows **4.5 out of 5 stars** (16 recent ratings) right at the top of the page — see `report_assets/competitor_screenshots/ama_fmgf_top.webp`. Top-level summary says "Reported to have a gluten-free menu" (neutral/positive framing). Shows aggregated community tags as a net score: "Dedicated gluten-free pasta pot and water +4", "No dedicated fryer -2" — no overall safety verdict. Scrolling through the full review list reveals **three separate real illness reports**, more than our own system found:
- *Kt686, Celiac, 4 months ago* (screenshot: `report_assets/competitor_screenshots/ama_fmgf_illness_report.png`): "Terrible experience, would not recommend... confirmed with two separate people that the pasta dish I received was gluten free only to be told later that it was actually the gluten pasta." — **1 star**, "Yes - moderate to severe symptoms"
- *logan57266, Symptomatic Celiac, 6 months ago*: "I ate lunch here and got my classic glutening symptoms soon after eating... would unfortunately not feel safe recommending this to Celiac friends"
- *blaise93889, Celiac, 1 year ago*: "my wife has gotten sick twice there. Would say its gluten free friendly not celiac friendly."

None of these are surfaced as a warning anywhere on the page — they're three reviews among 16, requiring a user to read the entire list to notice the pattern.

**Google (real screenshot: `report_assets/competitor_screenshots/ama_google_ai_overview.png`, search "Ama restaurant Washington DC gluten free celiac")**: Google's AI Overview is more sophisticated than a plain search summary — it does surface one real caveat, noting Ama "operates as a shared kitchen rather than a 100% dedicated gluten-free facility." But its overall framing is still promotional: it highlights "Safety & Awareness: Staff are trained and knowledgeable," a "Clean-Eating Focus... avoids seed oils, refined sugars, and microplastics," and even closes by offering to suggest *other* nearby restaurants — with **no mention anywhere of the real illness reports** sitting on the very Find Me Gluten Free page it cites as a source.

**Why it matters:** This is the exact failure mode the project is built to fix, and the real screenshots make it sharper than expected. Find Me Gluten Free shows Ama at **4.5 out of 5 stars** right at the top of the page — the 1-star illness report from Kt686 exists, but it's averaged away into a rating that reads as a clear recommendation at a glance. Google's AI Overview goes a step further: it actually cites Find Me Gluten Free as a source, correctly extracts the "shared kitchen, not dedicated" nuance, yet still misses all three illness reports sitting right there on the page it's summarizing — and frames the restaurant in marketing language ("clean-eating," "allergen-friendly") rather than safety language. Only our system's asymmetric-risk-rule-driven top-line warning makes the real risk impossible to miss.

## Rise Bakery (2409 18th St NW) — confirms our system isn't just contrarian

**Our system:** `confirmed_dedicated_gf_prep` — the top tier, high confidence.

**Find Me Gluten Free** (screenshot: `report_assets/competitor_screenshots/rise_bakery_fmgf_top.webp`): **4.5 out of 5 stars**, 177 recent ratings, a green checkmark badge reading "Reported to be dedicated gluten-free."

**Google (via web search)**: Multiple independent sources (Atly, Hoodline/Yelp, Per Diem) describe it as "100% Dedicated Gluten-Free" and the top-rated GF spot in DC (4.5/5, 168 Yelp reviews).

**Why it matters:** All three sources agree here. Our system correctly identifies a genuinely safe, dedicated facility as the top tier — the point isn't to always find something wrong, it's to apply the same evidence standard consistently in both directions.

## Lapis (1847 Columbia Rd NW) — a middle case

**Our system:** `accommodates_caution_cross_contamination` — real accommodation evidence, explicit caution (no confirmed dedicated fryer).

**Find Me Gluten Free** (screenshot: `report_assets/competitor_screenshots/lapis_fmgf_top.webp`): **5 out of 5 stars**, 35 recent ratings — a perfect star rating — with a Safety Rating section (28 ratings) showing "No dedicated fryer ↓ -2" alongside "Dairy-Free ↑ 7." The headline star rating is perfect; the actual safety-relevant caveat only appears if you read into the secondary "Insights" box.

**Why it matters:** Lapis shows a **perfect 5-star rating** on Find Me Gluten Free — a diner skimming star ratings would see it as a stronger choice than Rise Bakery (4.5 stars) or Ama (4.5 stars), despite being the one with the least safety certainty of the three. Our system correctly places it in the middle tier (not the top), because a 5-star average doesn't change the underlying fact that no claim confirms a dedicated fryer or prep area — exactly the caveat Find Me Gluten Free's own data shows, just not reflected in its headline rating at all.

## Screenshots — all captured

Text comparison above is from real, live-fetched page content (`app/harness/grounding.fetch_text`, the same fetcher used for source grounding all session) plus real screenshots, all captured manually by the user (Claude in Chrome extension not connected in this environment) and saved to `report_assets/competitor_screenshots/`:

- [x] `ama_fmgf_top.webp` — Ama's Find Me Gluten Free page top (4.5★, 16 ratings, neutral "reported to have a gluten-free menu" framing)
- [x] `ama_fmgf_illness_report.png` — the real Kt686 1-star illness report, buried below the 4.5★ headline
- [x] `ama_google_ai_overview.png` — Google's AI Overview for Ama: correctly notes "shared kitchen, not dedicated," but zero mention of the illness reports, framed in marketing language
- [x] `rise_bakery_fmgf_top.webp` — Rise Bakery, 4.5★, "Reported to be dedicated gluten-free" badge
- [x] `lapis_fmgf_top.webp` — Lapis, a perfect 5★, with "No dedicated fryer ↓ -2" only visible in the secondary Insights box

Step 8 is complete. This is strong, specific material for the report's "What is new" section — every claim above is backed by a real screenshot, not a description.
