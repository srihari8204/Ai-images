"""Job pricing.

Cost is the base cost scaled by the style multiplier, the number of output
candidates, and per-stage surcharges for expensive post-processing. Pricing is
deterministic so the held amount always equals the eventual debit.
"""

from __future__ import annotations

import math

from app.core.config import settings

# Additional credit cost per optional stage (on top of the base generate stage).
_STAGE_SURCHARGE = {
    "instantid": 1,
    "controlnet": 1,
    "gfpgan": 1,
    "realesrgan": 2,
    "bg_removal": 1,
}


def price_job(
    *,
    cost_multiplier: float = 1.0,
    stages: list[str],
    num_outputs: int = 1,
    steps: int | None = None,
) -> int:
    base = settings.base_job_cost_credits
    surcharge = sum(_STAGE_SURCHARGE.get(s, 0) for s in stages if s != "generate")
    # Step count above the default tier adds proportional cost.
    step_factor = 1.0
    if steps and steps > 30:
        step_factor = 1.0 + (steps - 30) / 60.0
    raw = (base + surcharge) * max(cost_multiplier, 1.0) * max(num_outputs, 1) * step_factor
    return max(1, math.ceil(raw))
