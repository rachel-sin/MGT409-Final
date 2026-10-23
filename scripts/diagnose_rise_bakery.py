"""One-off diagnostic: why did Rise Bakery's evidence extraction hit the
token cap? Runs with a generously raised limit (not a permanent change) and
prints every tool call made and how much text came back, so we can see the
real trace instead of guessing."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_ai.usage import UsageLimits  # noqa: E402

from app.agents.evidence_extractor import evidence_extractor_agent  # noqa: E402

DIAGNOSTIC_LIMITS = UsageLimits(request_limit=30, total_tokens_limit=80_000)


async def main() -> None:
    prompt = (
        "Restaurant: Rise Bakery\n"
        "Address: Washington, DC\n"
        "Find celiac-safety evidence for this specific restaurant."
    )
    result = await evidence_extractor_agent.run(prompt, usage_limits=DIAGNOSTIC_LIMITS)

    print(f"Final usage: {result.usage}\n")
    print(f"Claims extracted: {len(result.output.claims)}\n")

    tool_call_count = 0
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            kind = type(part).__name__
            if kind == "ToolCallPart":
                tool_call_count += 1
                args = getattr(part, "args", None)
                print(f"[{tool_call_count}] TOOL CALL ({part.tool_name}): {args}")
            elif kind == "ToolReturnPart":
                content = getattr(part, "content", "")
                content_str = str(content)
                print(f"    -> returned {len(content_str)} chars: {content_str[:200]!r}...")
            elif kind == "BuiltinToolCallPart":
                args = getattr(part, "args", None)
                print(f"[{tool_call_count + 1}] BUILTIN TOOL CALL ({part.tool_name}): {args}")
            elif kind == "BuiltinToolReturnPart":
                content = getattr(part, "content", "")
                content_str = str(content)
                print(f"    -> returned {len(content_str)} chars: {content_str[:300]!r}...")


if __name__ == "__main__":
    asyncio.run(main())
