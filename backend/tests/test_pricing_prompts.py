"""Pricing, prompt composition, and safety screening."""

from __future__ import annotations

import pytest

from app.core import safety
from app.core.errors import ValidationAppError
from app.modules.pipeline.pricing import price_job
from app.modules.prompts import service as prompts


def test_price_scales_with_stages_and_multiplier():
    base = price_job(cost_multiplier=1.0, stages=["generate"], num_outputs=1)
    more = price_job(
        cost_multiplier=1.5, stages=["generate", "realesrgan", "gfpgan"], num_outputs=2
    )
    assert more > base


def test_compose_applies_template():
    final, neg = prompts.compose(
        "a cat", template="photo of {prompt}, 8k", style_negative="blurry"
    )
    assert final == "photo of a cat, 8k"
    assert "blurry" in neg


def test_compose_rejects_overlong_prompt():
    with pytest.raises(ValidationAppError):
        prompts.compose("word " * 600)


def test_prompt_safety_blocks_prohibited():
    res = safety.score_prompt("non-consensual explicit content")
    assert not res.allowed


def test_prompt_safety_allows_normal():
    assert safety.score_prompt("a serene mountain landscape").allowed
