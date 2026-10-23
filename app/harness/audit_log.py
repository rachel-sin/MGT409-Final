"""Audit log: every run saved to JSON — timestamp, per-agent tool calls/
sources, decisions, stop reason, duration, and tokens (input, cached input,
output) per agent, per the brief's requirement. Pulled forward ahead of the
rest of Step 5 specifically so every live run from here on is diagnosable —
see FAILURES.md #3/#4 for why that mattered."""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "runs"

StopReason = Literal["completed", "cap_exceeded", "timeout", "error", "cached"]


class TokenUsage(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class AgentCallRecord(BaseModel):
    agent_name: str
    prompt_preview: str
    tokens: TokenUsage | None = None  # None if the call never completed
    duration_seconds: float
    stop_reason: StopReason
    sources: list[str] = Field(default_factory=list)
    error: str | None = None


class RunLog(BaseModel):
    run_id: str
    timestamp: str
    subject: str  # restaurant name, or a discovery query description
    agent_calls: list[AgentCallRecord] = Field(default_factory=list)
    final_safety_level: str | None = None
    final_confidence: str | None = None
    override_applied: bool = False
    overall_stop_reason: StopReason = "completed"

    def total_tokens(self) -> TokenUsage:
        total = TokenUsage()
        for call in self.agent_calls:
            if call.tokens:
                total = total + call.tokens
        return total

    def total_duration_seconds(self) -> float:
        return sum(c.duration_seconds for c in self.agent_calls)


def new_run_log(subject: str) -> RunLog:
    return RunLog(run_id=str(uuid.uuid4())[:8], timestamp=datetime.now(timezone.utc).isoformat(), subject=subject)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


# PLACEHOLDER rates — not confirmed Portkey/gpt-6-luna pricing. Good enough
# for showing a rough per-run cost in the UI now; Step 7 (Tokenomics) must
# replace these with real, sourced rates before they go in the report.
_PLACEHOLDER_INPUT_PER_1K = 0.0030
_PLACEHOLDER_CACHED_INPUT_PER_1K = 0.0015
_PLACEHOLDER_OUTPUT_PER_1K = 0.0120


def estimate_cost_usd(tokens: TokenUsage) -> float:
    return (
        tokens.input_tokens / 1000 * _PLACEHOLDER_INPUT_PER_1K
        + tokens.cached_input_tokens / 1000 * _PLACEHOLDER_CACHED_INPUT_PER_1K
        + tokens.output_tokens / 1000 * _PLACEHOLDER_OUTPUT_PER_1K
    )


def save_run_log(run_log: RunLog) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    safe_timestamp = run_log.timestamp.replace(":", "-")
    path = LOG_DIR / f"{safe_timestamp}_{_slugify(run_log.subject)}_{run_log.run_id}.json"
    data = run_log.model_dump()
    data["total_tokens"] = run_log.total_tokens().model_dump()
    data["total_duration_seconds"] = run_log.total_duration_seconds()
    path.write_text(json.dumps(data, indent=2))
    return path
