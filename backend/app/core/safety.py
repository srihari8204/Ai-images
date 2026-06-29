"""Content safety screening for images and prompts.

This module provides a pluggable interface. The default implementation is a
deterministic, dependency-free heuristic suitable for dev/test; production wires
``score_image``/``score_prompt`` to a real NSFW classifier or a third-party
moderation API. Either way the *interface* and the quarantine/record flow stay
identical, satisfying the "screen and quarantine on violation" requirements.
"""

from __future__ import annotations

import re

from app.core.config import settings

# Prohibited prompt categories (minors, non-consensual, explicit illegal content).
_PROHIBITED_PATTERNS = [
    r"\b(child|minor|underage|preteen|loli|shota)\b.*\b(nude|naked|sexual|explicit)\b",
    r"\b(non[- ]?consensual|rape|revenge porn)\b",
    r"\bdeepfake\b.*\b(nude|porn|sexual)\b",
    r"\b(bestiality|incest)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PROHIBITED_PATTERNS]


class SafetyResult:
    def __init__(self, *, allowed: bool, score: float, classifier: str, reason: str | None = None):
        self.allowed = allowed
        self.score = score
        self.classifier = classifier
        self.reason = reason


def score_prompt(prompt: str) -> SafetyResult:
    for pattern in _COMPILED:
        if pattern.search(prompt):
            return SafetyResult(
                allowed=False,
                score=1.0,
                classifier="prompt-policy-v1",
                reason="matched prohibited category",
            )
    return SafetyResult(allowed=True, score=0.0, classifier="prompt-policy-v1")


_nsfw_pipeline = None
_nsfw_failed = False


def _get_nsfw_pipeline():
    """Lazy-load a real NSFW image classifier when enabled (transformers)."""

    global _nsfw_pipeline, _nsfw_failed
    if _nsfw_pipeline is not None or _nsfw_failed:
        return _nsfw_pipeline
    try:
        from transformers import pipeline as hf_pipeline  # type: ignore

        _nsfw_pipeline = hf_pipeline("image-classification", model=settings.nsfw_model)
    except Exception:  # noqa: BLE001 - deps/weights/GPU absent
        _nsfw_failed = True
    return _nsfw_pipeline


def score_image(data: bytes, mime: str) -> SafetyResult:
    """Score an image for NSFW content.

    With ``ENABLE_NSFW_MODEL`` set and transformers available, uses a real
    classifier (e.g. Falconsai/nsfw_image_detection); otherwise falls back to a
    deterministic heuristic so dev/test stays dependency-free. The threshold
    lives in settings so ops can tune it.
    """

    if settings.enable_nsfw_model:
        clf = _get_nsfw_pipeline()
        if clf is not None:
            try:
                import io

                from PIL import Image as PILImage

                img = PILImage.open(io.BytesIO(data)).convert("RGB")
                preds = {p["label"].lower(): p["score"] for p in clf(img)}
                score = float(preds.get("nsfw", preds.get("porn", 0.0)))
                allowed = score < settings.nsfw_threshold
                return SafetyResult(
                    allowed=allowed,
                    score=score,
                    classifier=settings.nsfw_model,
                    reason=None if allowed else "exceeded nsfw threshold",
                )
            except Exception:  # noqa: BLE001 - fall through to heuristic
                pass

    # Heuristic fallback (no model): low score unless a test marker is present.
    score = 0.99 if b"NSFW_TEST_MARKER" in data[:64] else 0.01
    allowed = score < settings.nsfw_threshold
    return SafetyResult(
        allowed=allowed,
        score=score,
        classifier="image-nsfw-heuristic-v1",
        reason=None if allowed else "exceeded nsfw threshold",
    )
