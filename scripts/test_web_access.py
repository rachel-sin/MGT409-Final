"""Step 1 — web access feasibility test.

Finds out whether OpenAI's built-in web search tool works through Portkey
with gpt-6-luna, before the Finder agent is built to depend on it. The
brief flags a real risk here: the course backend may be Azure, which may
only support the Responses API (not Chat Completions) for this tool, and
gpt-6-luna is known to reject tool-calling requests unless
openai_reasoning_effort is explicitly set to "none".

Tries two things, in order, and reports pass/fail for each rather than
assuming either will work:
  1. pydantic_ai Agent using OpenAIResponsesModel + WebSearchTool
  2. a raw openai client call to the Responses API with tools=[{"type": "web_search"}]

This script only makes network calls when run directly — importing it
does nothing. Per the build plan, it is written now but not yet run.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Look for .env in this repo's own folder first, then one folder above —
# matches the course's required .env lookup order.
REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ENV_PATHS = [REPO_ROOT / ".env", REPO_ROOT.parent / ".env"]

ENV_PATH = next((p for p in CANDIDATE_ENV_PATHS if p.exists()), None)
if ENV_PATH is None:
    sys.exit(
        "No .env found in either of:\n  "
        + "\n  ".join(str(p) for p in CANDIDATE_ENV_PATHS)
        + "\nCopy .env.example to one of these locations and fill in PORTKEY_API_KEY."
    )
load_dotenv(ENV_PATH)

PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
if not PORTKEY_API_KEY:
    sys.exit(f"PORTKEY_API_KEY not set in {ENV_PATH}")

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL_NAME = "gpt-6-luna"
TEST_QUESTION = (
    "Search the web and tell me: what is one specific, current fact about "
    "restaurants in Washington, DC that you could only know from a live "
    "web search (not from training data)? Name the source."
)


def _make_async_openai_client():
    """Builds the shared AsyncOpenAI client pointed at Portkey.

    Passes an explicit certifi CA bundle rather than relying on openai's
    default httpx2 transport, which (on this machine, inside this sandbox)
    fails TLS verification against its own macOS-native trust store
    (OSStatus -26276) even though the same request succeeds via curl and
    plain `requests` (which use certifi). This is an environment quirk in
    this dev setup, not a Portkey/Azure problem — confirmed by isolating
    httpx2.AsyncClient(verify=certifi.where()) as the fix.
    """
    import certifi
    import httpx2
    from openai import AsyncOpenAI

    http_client = httpx2.AsyncClient(verify=certifi.where())
    return AsyncOpenAI(
        api_key=PORTKEY_API_KEY, base_url=PORTKEY_BASE_URL, timeout=30.0, max_retries=1, http_client=http_client
    )


async def test_pydantic_ai_web_search() -> tuple[bool, str]:
    """Attempt 1: pydantic_ai's WebSearchTool over the Responses API."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import NativeTool
    from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
    from pydantic_ai.native_tools import WebSearchTool
    from pydantic_ai.providers.openai import OpenAIProvider

    client = _make_async_openai_client()
    model = OpenAIResponsesModel(
        MODEL_NAME,
        provider=OpenAIProvider(openai_client=client),
        # Known course issue: gpt-6-luna rejects tool-calling requests
        # unless reasoning effort is explicitly turned off.
        settings=OpenAIResponsesModelSettings(openai_reasoning_effort="none"),
    )
    agent = Agent(model, capabilities=[NativeTool(WebSearchTool())])

    result = await agent.run(TEST_QUESTION)
    return True, result.output


async def test_raw_responses_api() -> tuple[bool, str]:
    """Attempt 2: a raw Responses API call, bypassing pydantic_ai entirely,
    in case the wrapper is the thing that fails rather than the backend."""
    client = _make_async_openai_client()
    response = await client.responses.create(
        model=MODEL_NAME,
        input=TEST_QUESTION,
        tools=[{"type": "web_search"}],
        reasoning={"effort": "none"},
    )
    return True, response.output_text


async def main() -> None:
    print(f"Using .env at: {ENV_PATH}")
    print(f"Model: {MODEL_NAME} via {PORTKEY_BASE_URL}\n")

    for label, test_fn in [
        ("pydantic_ai WebSearchTool (Responses model)", test_pydantic_ai_web_search),
        ("raw openai Responses API (tools=[web_search])", test_raw_responses_api),
    ]:
        print(f"--- {label} ---")
        try:
            ok, output = await test_fn()
            print(f"RESULT: {'PASS' if ok else 'FAIL'}")
            print(f"Output: {output}\n")
        except Exception as exc:  # noqa: BLE001 — report the real error, don't guess at it
            print(f"RESULT: FAIL")
            print(f"Error ({type(exc).__name__}): {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
