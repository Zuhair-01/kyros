"""Task-to-model routing engine.

Given a description of an AI task's shape (size, risk, whether a local
pattern exists to imitate), decides which tier should execute it: a cheap
local model, a mid-tier cloud model, a frontier cloud model, or "retain" —
don't dispatch at all, a human/senior model should just do it directly.

Pure functions over immutable dataclasses. No network calls, no state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Concern(str, Enum):
    CODEGEN = "codegen"
    REASONING = "reasoning"
    COPY = "copy"
    VISION = "vision"


class Tier(str, Enum):
    LOCAL = "local"
    CLOUD_LOW = "cloud-low"
    CLOUD_MEDIUM = "cloud-medium"
    CLOUD_HIGH = "cloud-high"
    RETAIN = "retain"


# High-risk concerns that always skip cheap tiers regardless of task size.
_HIGH_RISK = frozenset({
    "concurrency", "auth", "money", "migration", "security", "data-loss",
})

# Local fleet routing by concern, mirroring the 8GB-VRAM-ceiling roster.
_LOCAL_MODEL_BY_CONCERN = {
    Concern.CODEGEN: "qwen2.5-coder:7b",
    Concern.REASONING: "deepseek-r1:8b",
    Concern.COPY: "llama3.1:8b",
    Concern.VISION: "moondream",
}


@dataclass(frozen=True, slots=True)
class Task:
    """One unit of work under consideration for dispatch."""
    concern: Concern
    output_lines_est: int
    files_touched: int = 1
    pattern_exists: bool = False
    risk_tags: frozenset[str] = field(default_factory=frozenset)
    context_tokens_est: int = 0


@dataclass(frozen=True, slots=True)
class Decision:
    tier: Tier
    model: str
    reason: str


# Dispatch to the local fleet only pays when ALL of these hold — see
# docs/routing-policy.md for the cost data behind these thresholds.
_LOCAL_MIN_OUTPUT_LINES = 60
_LOCAL_MAX_CONTEXT_TOKENS = 16_000

# Cloud tier boundaries by estimated output size, once a task is not risky
# enough to require Opus-tier judgment and not cheap enough for local.
_HAIKU_MAX_LINES = 20
_SONNET_MAX_LINES = 400


def _is_high_risk(task: Task) -> bool:
    return bool(task.risk_tags & _HIGH_RISK)


def _local_eligible(task: Task) -> bool:
    return (
        task.output_lines_est >= _LOCAL_MIN_OUTPUT_LINES
        and task.pattern_exists
        and task.files_touched == 1
        and task.context_tokens_est <= _LOCAL_MAX_CONTEXT_TOKENS
        and not _is_high_risk(task)
    )


def route(task: Task) -> Decision:
    """Decide which tier should execute `task`."""
    if _is_high_risk(task):
        tags = ", ".join(sorted(task.risk_tags & _HIGH_RISK))
        return Decision(Tier.RETAIN, model="none", reason=f"high-risk tags: {tags}")

    if task.files_touched > 1 and task.output_lines_est < _LOCAL_MIN_OUTPUT_LINES:
        return Decision(
            Tier.RETAIN, model="none",
            reason="cross-file judgment call on a small diff — not mechanically dispatchable",
        )

    if _local_eligible(task):
        model = _LOCAL_MODEL_BY_CONCERN[task.concern]
        return Decision(Tier.LOCAL, model=model, reason="bulky + mechanical + pattern exists")

    if task.output_lines_est <= _HAIKU_MAX_LINES and task.pattern_exists:
        return Decision(Tier.CLOUD_LOW, model="claude-haiku-4-5", reason="small, fully-specified, verifiable")

    if task.output_lines_est <= _SONNET_MAX_LINES:
        return Decision(Tier.CLOUD_MEDIUM, model="claude-sonnet-5", reason="standard feature-sized work")

    return Decision(Tier.CLOUD_HIGH, model="claude-opus-5", reason="large or unbounded scope")
