"""Prompt engine: composition, token validation, and safety filtering.

A composed prompt merges the user's text into the style template (``{prompt}``
placeholder) and combines negative prompts. Token length is validated against
the model's context limit. Safety filtering blocks prohibited categories before
any job is enqueued and records a moderation event.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import safety
from app.core.errors import PolicyError, ValidationAppError
from app.modules.admin.service import record_moderation_event

# FLUX.1 text encoder practical token budget (T5 + CLIP). Bounded conservatively.
MAX_PROMPT_TOKENS = 512


def _estimate_tokens(text: str) -> int:
    # Lightweight estimate: split on whitespace/punctuation. Avoids pulling a
    # tokenizer into the API tier; the worker re-validates against the real one.
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text))


def compose(
    user_prompt: str,
    *,
    template: str | None = None,
    style_negative: str | None = None,
    user_negative: str | None = None,
) -> tuple[str, str]:
    """Return ``(final_prompt, final_negative_prompt)``."""

    user_prompt = (user_prompt or "").strip()
    if not user_prompt and not template:
        raise ValidationAppError("Prompt must not be empty", details={"field": "prompt"})

    if template and "{prompt}" in template:
        final = template.replace("{prompt}", user_prompt)
    elif template:
        final = f"{template}, {user_prompt}".strip(", ")
    else:
        final = user_prompt

    if not user_prompt:
        # Style-only ("AI Mirror") mode: clean placeholder artifacts so a
        # prompt with no user text reads naturally, e.g.
        # "portrait of , dramatic" -> "portrait, dramatic".
        final = re.sub(r"\bof\s*,", ",", final)
        final = re.sub(r"\s*,\s*,", ",", final)
        final = re.sub(r"\s{2,}", " ", final).strip(" ,")

    negatives = [n for n in (style_negative, user_negative) if n]
    final_negative = ", ".join(dict.fromkeys(", ".join(negatives).split(", "))).strip(", ")

    total = _estimate_tokens(final) + _estimate_tokens(final_negative)
    if total > MAX_PROMPT_TOKENS:
        raise ValidationAppError(
            "Composed prompt exceeds the model token limit",
            details={"limit": MAX_PROMPT_TOKENS, "estimated": total},
        )
    return final, final_negative


async def screen_prompt(
    db: AsyncSession, user_id: uuid.UUID, prompt: str, *, subject_id: str | None = None
) -> None:
    """Block prohibited prompts and record a moderation event on violation."""

    result = safety.score_prompt(prompt)
    if not result.allowed:
        await record_moderation_event(
            db,
            subject_type="prompt",
            subject_id=subject_id,
            user_id=user_id,
            classifier=result.classifier,
            score=result.score,
            decision="rejected",
            detail=result.reason,
        )
        raise PolicyError(
            "Prompt violates content policy",
            code="prompt_policy_violation",
            status_code=422,
        )
