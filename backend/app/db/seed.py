"""Idempotent seed data: roles, plans, styles, and feature flags.

Run with::

    python -m app.db.seed
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import configure_logging, get_logger
from app.db.sync_session import session_scope
from app.modules.admin.models import FeatureFlag
from app.modules.payments.models import Plan, PlanKind
from app.modules.styles.models import Style
from app.modules.users.models import Role

logger = get_logger("seed")


ROLES = [
    ("user", "Standard user"),
    ("moderator", "Content moderator"),
    ("admin", "Administrator"),
]

PLANS = [
    dict(slug="free", name="Free", kind=PlanKind.SUBSCRIPTION, monthly_credits=20,
         credits=0, price_cents=0, features={"priority": False}),
    dict(slug="pro", name="Pro", kind=PlanKind.SUBSCRIPTION, monthly_credits=500,
         credits=0, price_cents=1500, features={"priority": True, "premium_styles": True}),
    dict(slug="studio", name="Studio", kind=PlanKind.SUBSCRIPTION, monthly_credits=2000,
         credits=0, price_cents=4900, features={"priority": True, "premium_styles": True}),
    dict(slug="pack_100", name="100 Credits", kind=PlanKind.CREDIT_PACK, monthly_credits=0,
         credits=100, price_cents=900, features={}),
    dict(slug="pack_500", name="500 Credits", kind=PlanKind.CREDIT_PACK, monthly_credits=0,
         credits=500, price_cents=3900, features={}),
]

def _style(slug, name, category, template, negative, mult=1.0, gate=None, steps=28, guidance=3.5):
    return dict(
        slug=slug, name=name, category=category, template=template,
        negative_prompt=negative, cost_multiplier=mult, plan_gate=gate,
        default_params={"steps": steps, "guidance": guidance},
    )


_NEG_PHOTO = "cartoon, painting, blurry, lowres, deformed, extra limbs, watermark, text"
_NEG_ART = "photo, photorealistic, blurry, lowres, deformed, watermark, text"

STYLES = [
    # --- Free / general ---
    _style("photoreal", "Photorealistic", "general",
           "{prompt}, ultra realistic, 8k, sharp focus, natural lighting", _NEG_PHOTO),
    _style("cinematic", "Cinematic", "general",
           "cinematic still of {prompt}, dramatic lighting, film grain, shallow depth of field",
           "flat lighting, snapshot, lowres", guidance=4.0, steps=30),
    _style("hdr", "HDR Vivid", "general",
           "{prompt}, vivid HDR, high dynamic range, crisp detail, vibrant color", _NEG_PHOTO),
    _style("minimalist", "Minimalist", "general",
           "minimalist {prompt}, clean composition, negative space, soft palette", _NEG_PHOTO),

    # --- Portrait ---
    _style("headshot", "Pro Headshot", "portrait",
           "professional corporate headshot of {prompt}, softbox lighting, neutral background, bokeh",
           "harsh shadows, overexposed, distorted face", guidance=3.5, steps=30),
    _style("glamour", "Glamour", "portrait",
           "glamour portrait of {prompt}, beauty lighting, flawless skin, magazine cover",
           "harsh shadows, blemishes, distorted face"),
    _style("bw_portrait", "B&W Portrait", "portrait",
           "black and white fine-art portrait of {prompt}, dramatic rim light, high contrast",
           "color, oversaturated, lowres"),

    # --- Illustration / anime ---
    _style("anime", "Anime", "illustration",
           "anime illustration of {prompt}, vibrant colors, clean line art, cel shading", _NEG_ART,
           guidance=5.0, steps=26),
    _style("manga", "Manga", "illustration",
           "black and white manga panel of {prompt}, ink, screentone, dynamic", _NEG_ART),
    _style("comic", "Comic Book", "illustration",
           "comic book art of {prompt}, bold inks, halftone, dynamic pose", _NEG_ART),
    _style("watercolor", "Watercolor", "illustration",
           "watercolor painting of {prompt}, soft washes, paper texture, delicate", _NEG_ART),
    _style("oil_painting", "Oil Painting", "illustration",
           "classical oil painting of {prompt}, visible brush strokes, rich color", _NEG_ART,
           guidance=5.0),
    _style("sketch", "Pencil Sketch", "illustration",
           "detailed pencil sketch of {prompt}, graphite, cross-hatching, paper", _NEG_ART),
    _style("pop_art", "Pop Art", "illustration",
           "pop art of {prompt}, bold flat colors, Ben-Day dots, high contrast", _NEG_ART),
    _style("low_poly", "Low Poly", "illustration",
           "low poly 3d render of {prompt}, geometric facets, flat shading", _NEG_ART),

    # --- 3D / render ---
    _style("pixar", "3D Cartoon", "3d",
           "cute 3d animated character of {prompt}, pixar style, soft global illumination",
           _NEG_ART, guidance=4.5),
    _style("claymation", "Claymation", "3d",
           "claymation style {prompt}, stop-motion, plasticine texture, studio light", _NEG_ART),
    _style("figurine", "Collectible Figurine", "3d",
           "collectible vinyl figurine of {prompt}, studio product shot, soft shadows", _NEG_ART),

    # --- Themed (free) ---
    _style("cyberpunk", "Cyberpunk", "themed",
           "cyberpunk {prompt}, neon lights, rain, futuristic city, blade-runner mood",
           _NEG_PHOTO, guidance=4.5),
    _style("vaporwave", "Vaporwave", "themed",
           "vaporwave aesthetic {prompt}, pastel neon, retro grid, 80s synth", _NEG_ART),
    _style("noir", "Film Noir", "themed",
           "film noir {prompt}, black and white, venetian blind shadows, moody", _NEG_PHOTO),
    _style("vintage", "Vintage Film", "themed",
           "vintage 1970s film photo of {prompt}, kodak grain, warm faded tones", _NEG_PHOTO),
    _style("synthwave", "Synthwave", "themed",
           "synthwave {prompt}, neon sunset, chrome, retro-futuristic", _NEG_ART),

    # --- Premium (pro) ---
    _style("portrait_pro", "Portrait Pro", "portrait",
           "professional studio portrait of {prompt}, softbox lighting, bokeh, editorial",
           "harsh shadows, overexposed, distorted face", mult=1.5, gate="pro", steps=32),
    _style("fantasy_art", "Fantasy Art", "illustration",
           "epic fantasy concept art of {prompt}, intricate detail, painterly, dramatic",
           _NEG_ART, mult=1.5, gate="pro", steps=34, guidance=5.5),
    _style("scifi", "Sci-Fi Concept", "themed",
           "sci-fi concept art of {prompt}, sleek tech, cinematic, highly detailed",
           _NEG_ART, mult=1.5, gate="pro", steps=32),
    _style("hyperreal", "Hyperreal", "portrait",
           "hyperrealistic close-up of {prompt}, skin pores, studio macro, 85mm",
           "plastic skin, cartoon, lowres", mult=1.5, gate="pro", steps=34),
    _style("oil_master", "Old Masters", "illustration",
           "renaissance old-masters oil portrait of {prompt}, chiaroscuro, museum quality",
           _NEG_ART, mult=1.5, gate="pro", guidance=5.0),

    # --- Premium (studio) ---
    _style("fashion_editorial", "Fashion Editorial", "portrait",
           "high fashion editorial of {prompt}, vogue lighting, designer wardrobe, studio",
           "amateur, snapshot, lowres", mult=2.0, gate="studio", steps=36),
    _style("anime_film", "Anime Film", "illustration",
           "cinematic anime film key visual of {prompt}, studio quality, detailed background",
           _NEG_ART, mult=2.0, gate="studio", steps=34, guidance=5.5),

    # --- AI-Mirror-style themed packs (free for everyone) ---
    _style("pocket_pals", "Pocket Pals", "pack",
           "adorable portrait of {prompt} with a cute pocket-sized fantasy creature companion, "
           "chibi, big sparkling eyes, vibrant, soft studio light", _NEG_ART, steps=30, guidance=5.0),
    _style("anime_aesthetic", "Anime Aesthetic", "pack",
           "dreamy anime aesthetic portrait of {prompt}, soft pastel palette, detailed eyes, "
           "delicate lighting, trending anime art", _NEG_ART, steps=30, guidance=5.0),
    _style("y2k", "Y2K", "pack",
           "Y2K early-2000s aesthetic portrait of {prompt}, glossy metallic, butterfly clips, "
           "holographic, retro digital flash photo", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("funpack", "Fun Pack", "pack",
           "playful colorful sticker-style portrait of {prompt}, party vibes, confetti, "
           "bright bold colors", _NEG_ART, steps=30, guidance=5.0),
    _style("birthday_glow", "Birthday Glow", "pack",
           "joyful birthday portrait of {prompt}, balloons, confetti, warm golden glow, "
           "festive bokeh", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("giant_animal", "Giant Animal", "pack",
           "whimsical portrait of {prompt} beside a giant friendly animal, epic scale, "
           "cinematic wide shot, magical atmosphere", _NEG_PHOTO, steps=32, guidance=5.0),
    _style("reunited", "Reunited", "pack",
           "heartwarming emotional reunion portrait of {prompt}, soft golden-hour light, "
           "cinematic film look, tender mood", _NEG_PHOTO, steps=32, guidance=5.0),
    _style("high_fashion", "High Fashion", "pack",
           "high fashion editorial portrait of {prompt}, couture wardrobe, dramatic studio lighting, "
           "vogue magazine, ultra detailed", "amateur, snapshot, lowres, deformed", steps=32, guidance=5.0),
    _style("noir_mood", "Noir Mood", "pack",
           "moody film-noir portrait of {prompt}, black and white, venetian-blind shadows, "
           "cigarette smoke, dramatic contrast", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("best_companion", "Best Companion", "pack",
           "cozy portrait of {prompt} with a loyal pet companion, warm natural light, "
           "heartwarming", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("mvp", "MVP", "pack",
           "sports MVP hero portrait of {prompt}, stadium floodlights, confetti, trophy, "
           "dynamic athletic, cinematic", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("cheerup", "Cheer Up", "pack",
           "cheerful uplifting portrait of {prompt}, bright sunny light, warm colors, "
           "joyful smile, feel-good mood", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("lets_go", "Let's Go", "pack",
           "energetic adventure travel portrait of {prompt}, dynamic outdoor scene, golden light, "
           "wanderlust, cinematic", _NEG_PHOTO, steps=30, guidance=5.0),
    _style("sketchbook", "Sketchbook", "pack",
           "hand-drawn sketchbook portrait of {prompt}, pencil and ink, doodles, artistic linework, "
           "paper texture", _NEG_ART, steps=30, guidance=5.0),
    _style("poster_maker", "Poster Maker", "pack",
           "bold graphic poster of {prompt}, striking typography, high contrast, modern design, "
           "vibrant", _NEG_ART, steps=30, guidance=5.0),
    _style("painting", "Painting", "pack",
           "fine-art painted portrait of {prompt}, rich oil textures, expressive brush strokes, "
           "gallery quality", _NEG_ART, steps=32, guidance=5.0),
    _style("chibi_figure", "Chibi Figure", "pack",
           "cute chibi collectible figurine of {prompt}, 3d render, big head small body, glossy, "
           "studio product shot", _NEG_ART, steps=30, guidance=5.0),
    _style("gamer", "Gamer", "pack",
           "epic gamer avatar portrait of {prompt}, neon RGB lighting, futuristic esports, "
           "dramatic, high detail", _NEG_PHOTO, steps=30, guidance=5.0),
]

FLAGS = [
    ("model.flux.enabled", {"enabled": True}, "Enable FLUX.1 base model"),
    ("model.instantid.enabled", {"enabled": True}, "Enable InstantID face consistency"),
    ("queue.max_concurrency", {"value": 4}, "Worker max concurrent jobs"),
    ("registration.open", {"enabled": True}, "Allow new sign-ups"),
]


def _seed_roles(db: Session) -> None:
    for name, desc in ROLES:
        if not db.execute(select(Role).where(Role.name == name)).scalar_one_or_none():
            db.add(Role(name=name, description=desc))


def _seed_plans(db: Session) -> None:
    for p in PLANS:
        if not db.execute(select(Plan).where(Plan.slug == p["slug"])).scalar_one_or_none():
            db.add(Plan(**p))


def _seed_styles(db: Session) -> None:
    from app.db.style_catalog import catalog_styles

    seen: set[str] = set()
    for s in list(STYLES) + list(catalog_styles()):
        slug = s["slug"]
        if slug in seen:
            continue
        seen.add(slug)
        if not db.execute(select(Style).where(Style.slug == slug)).scalar_one_or_none():
            db.add(Style(**s))


def _seed_flags(db: Session) -> None:
    for key, value, desc in FLAGS:
        if not db.get(FeatureFlag, key):
            db.add(FeatureFlag(key=key, value=value, description=desc))


def run() -> None:
    configure_logging(json_logs=False)
    with session_scope() as db:
        _seed_roles(db)
        _seed_plans(db)
        _seed_styles(db)
        _seed_flags(db)
    logger.info("seed_complete")


if __name__ == "__main__":
    run()
