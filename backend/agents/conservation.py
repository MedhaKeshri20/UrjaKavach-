"""LLM-generated citizen conservation copy (F7 slice of Phase 9).

Reuses backend/agents/llm.py's complete_json (Phase 4) -- provider-generic
despite being Groq-backed today. Falls back to static, hand-written copy
(moved here from routes.py's old _TIPS/_LEVELS) on any failure, exactly the
same graceful-degradation posture as watch.py's LLM path, just single-tier
(SPEC.md Phase 9 decision #13).

The prompt's inputs (level, corridor_name) are deliberately limited to
exactly the two dimensions in the cache key (decision #11) -- never raw
severity/impact numbers, so a cached response is never stale relative to
what it was cached under.
"""

from __future__ import annotations

from backend.agents.llm import LLMUnavailable, complete_json
from backend.config import get_settings

_LEVELS_FALLBACK = {
    "Normal": (
        "Supplies are steady. No action needed.",
        ["Business as usual — no conservation required."],
    ),
    "Elevated": (
        "A supply route is under stress. Officials are rerouting; stay informed.",
        [
            "Combine errands into fewer trips.",
            "Keep tyres properly inflated to save fuel.",
            "Avoid topping-up your tank out of worry — there is no shortage.",
        ],
    ),
    "Shortage": (
        "Significant disruption. Please conserve fuel where you can.",
        [
            "Use public transport or car-pool where possible.",
            "Defer non-essential road travel.",
            "Do not panic-buy fuel — reserves are being managed.",
        ],
    ),
}

_PROMPT_TEMPLATE = """You are writing calm, plain-language guidance for a public \
citizen status board about India's crude-oil supply chain. The current status \
is "{level}"{corridor_clause}.

Write reassuring, non-alarming guidance appropriate to this status level -- \
never mention raw numbers, percentages, or internal model details. Respond \
with a JSON object only: {{"message": "<one or two calm sentences>", \
"conservation_plan": ["<short actionable tip>", ...]}} with 2 to 4 tips."""


def _fallback(level: str) -> dict:
    message, plan = _LEVELS_FALLBACK[level]
    return {"message": message, "conservation_plan": list(plan)}


def generate_conservation_copy(level: str, corridor_name: str | None) -> dict:
    """Returns ``{"message": str, "conservation_plan": list[str]}``.

    ``level`` must be one of "Normal"/"Elevated"/"Shortage" (routes.py's
    ``_level_for``). Skips the LLM call entirely for "Normal" (decision
    #12 -- nothing scenario-specific to say) and falls back to static copy
    whenever the real-agents flag/API key aren't set, or the LLM's response
    is missing/malformed.
    """

    settings = get_settings()
    if level == "Normal":
        return _fallback(level)
    if not settings.use_real_agents or not settings.groq_api_key:
        return _fallback(level)

    corridor_clause = (
        f", driven by disruption on the {corridor_name} corridor" if corridor_name else ""
    )
    prompt = _PROMPT_TEMPLATE.format(level=level, corridor_clause=corridor_clause)
    cache_key = f"{level}|{corridor_name or 'none'}"

    try:
        data = complete_json(prompt, cache_key=cache_key, model=settings.watch_model_primary)
        message = str(data["message"])
        plan = [str(tip) for tip in data["conservation_plan"]]
        if not message or not (1 <= len(plan) <= 6):
            raise ValueError("malformed conservation copy payload")
        return {"message": message, "conservation_plan": plan}
    except (LLMUnavailable, KeyError, TypeError, ValueError):
        return _fallback(level)
