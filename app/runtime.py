"""Shared runtime pieces every agent is built from: the one Portkey-routed
model (so every agent uses gpt-6-luna consistently) and a helper for giving
an agent live web search. Mirrors the HW5 pattern of one shared client/model
object rather than each agent file reinventing its own setup.
"""

import os
from pathlib import Path

import certifi
import httpx2
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.native_tools import WebSearchTool
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

# app/runtime.py -> app -> final project root. .env is looked for here first,
# then one folder above (the course's required lookup order).
REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ENV_PATHS = [REPO_ROOT / ".env", REPO_ROOT.parent / ".env"]
ENV_PATH = next((p for p in CANDIDATE_ENV_PATHS if p.exists()), None)
if ENV_PATH is None:
    raise RuntimeError(
        "No .env found in either of:\n  " + "\n  ".join(str(p) for p in CANDIDATE_ENV_PATHS) + "\nCopy .env.example."
    )
load_dotenv(ENV_PATH)

PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
if not PORTKEY_API_KEY:
    raise RuntimeError(f"PORTKEY_API_KEY not found — expected it in {ENV_PATH}")

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL_NAME = "gpt-6-luna"

# Explicit certifi CA bundle, not openai's default httpx2 transport — on this
# dev machine, httpx2's default TLS verification (macOS native trust store)
# fails inside the sandbox even though the same request succeeds via curl
# and `requests` (certifi-based). Confirmed in Step 1 (see HARNESS.md).
_http_client = httpx2.AsyncClient(verify=certifi.where())
_openai_client = AsyncOpenAI(
    api_key=PORTKEY_API_KEY,
    base_url=PORTKEY_BASE_URL,
    timeout=30.0,
    max_retries=1,
    http_client=_http_client,
)

# Responses API (not Chat Completions) — required for WebSearchTool support
# (Step 1 finding). openai_reasoning_effort="none" works around gpt-6-luna
# rejecting tool-calling requests with a reasoning effort set.
MODEL = OpenAIResponsesModel(
    MODEL_NAME,
    provider=OpenAIProvider(openai_client=_openai_client),
    settings=OpenAIResponsesModelSettings(openai_reasoning_effort="none"),
)

WEB_SEARCH_CAPABILITY = [NativeTool(WebSearchTool())]

# Minimum-viable cost/reliability caps, ahead of Step 5's full harness (which
# also needs the cached dataset/rate-limiter/fallback-to-cache logic). These
# two protect any single agent call from a runaway tool-call loop or
# excessive token spend before that fuller system exists.
AGENT_STEP_LIMIT = 8  # max tool calls + reasoning turns per agent call
AGENT_TOKEN_LIMIT = 20_000  # max total tokens per agent call
AGENT_WALL_CLOCK_TIMEOUT_SECONDS = 60  # per agent call

DEFAULT_USAGE_LIMITS = UsageLimits(request_limit=AGENT_STEP_LIMIT, total_tokens_limit=AGENT_TOKEN_LIMIT)

# Discovery mode searches for multiple distinct restaurants in one agent
# call, not one — naturally needs more budget than every other agent call in
# this project. Calibrated after the default cap genuinely tripped on a
# real 3-candidate search (total_tokens=20484 vs. the 20_000 default).
DISCOVERY_STEP_LIMIT = 16
DISCOVERY_TOKEN_LIMIT = 50_000
DISCOVERY_WALL_CLOCK_TIMEOUT_SECONDS = 120

DISCOVERY_USAGE_LIMITS = UsageLimits(request_limit=DISCOVERY_STEP_LIMIT, total_tokens_limit=DISCOVERY_TOKEN_LIMIT)

# Evidence extraction searches BOTH the restaurant's own menu AND, often,
# multiple third-party sources for one restaurant — routinely needs more
# than the generic default. Raised after two separate restaurants (Rise
# Bakery, Johnny Pistolas) both legitimately needed ~24-25k tokens, not just
# one rare outlier (see FAILURES.md #3 and HARNESS.md's cap-calibration note).
EVIDENCE_STEP_LIMIT = 10
EVIDENCE_TOKEN_LIMIT = 30_000
EVIDENCE_WALL_CLOCK_TIMEOUT_SECONDS = 60

EVIDENCE_USAGE_LIMITS = UsageLimits(request_limit=EVIDENCE_STEP_LIMIT, total_tokens_limit=EVIDENCE_TOKEN_LIMIT)

# Bounds how many restaurants' pipelines run concurrently. Doesn't change
# total token spend (same number of calls either way) — it bounds the PEAK
# request rate against Portkey/Azure, since we don't know their per-second
# concurrency limits. Set to match the current small candidate cap rather
# than left unbounded, so this stays safe if max_candidates grows later.
MAX_CONCURRENT_RESTAURANT_RUNS = 3

# Explicit (not pydantic_ai's implicit default of 1) schema-validation/tool-
# call retry budget per agent call, per the brief's "schema validation with
# max 2 retries then fail safe" requirement. On exhaustion, pydantic_ai
# raises (typically UnexpectedModelBehavior) — already caught by
# app/pipeline.py's _run_agent_logged generic exception handler, which logs
# it and lets the caller skip that one restaurant/call rather than crash
# (same path already proven by the prompt-injection test's content-filter
# case and the token-cap skip behavior).
AGENT_SCHEMA_RETRIES = 2
