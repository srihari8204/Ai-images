"""Generate a preview thumbnail for every style, using a stock face.

Runs on the GPU worker. For each active style it renders one image with the
InstantID pipeline (stock reference face) and uploads it to R2 at
``previews/<slug>.png``. Idempotent: styles that already have a preview object
are skipped, so it is safe to re-run to fill gaps.

Usage (on RunPod, with the worker env exported):
    bash deploy/runpod/generate-previews.sh
"""

from __future__ import annotations

import glob
import sys


def _stock_face() -> bytes:
    # The cloned InstantID repo ships example faces; use the first one.
    pats = ["/workspace/InstantID/examples/*.jpg",
            "/workspace/InstantID/examples/*.jpeg",
            "/workspace/InstantID/examples/*.png"]
    found: list[str] = []
    for p in pats:
        found.extend(glob.glob(p))
    if not found:
        print("ERROR: no stock face in /workspace/InstantID/examples/", file=sys.stderr)
        sys.exit(1)
    path = sorted(found)[0]
    print(f">>> stock face: {path}")
    with open(path, "rb") as f:
        return f.read()


def main() -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.storage import object_store

    # Register all ORM mappers so Style's relationships resolve.
    try:
        from ai_engine.worker import import_all_models

        import_all_models()
    except Exception:  # noqa: BLE001
        pass

    from ai_engine.pipeline import flux
    from ai_engine.pipeline.base import StageContext
    from app.modules.styles.models import Style

    face_bytes = _stock_face()

    engine = create_engine(settings.sync_database_url, future=True)
    with Session(engine) as db:
        styles = (
            db.execute(
                select(Style).where(Style.is_active.is_(True)).order_by(Style.category, Style.name)
            )
            .scalars()
            .all()
        )
    total = len(styles)
    print(f">>> {total} active styles")

    done = skipped = failed = 0
    for i, st in enumerate(styles, 1):
        key = f"previews/{st.slug}.png"
        if object_store.object_exists(settings.bucket_outputs, key):
            skipped += 1
            continue
        try:
            prompt = (st.template or "").replace("{prompt}", "").strip(" ,")
            ctx = StageContext(
                job_id=f"preview-{st.slug}",
                user_id="preview",
                prompt=prompt,
                negative_prompt=st.negative_prompt or "",
                seed=20240115,  # fixed for consistent previews
                params={"width": 768, "height": 768, "steps": 30, "guidance": 5.0},
                reference_images=[face_bytes],
                stages=["instantid"],
            )
            flux.run(ctx)
            object_store.put_object(
                settings.bucket_outputs, key, ctx.image_bytes("PNG"), "image/png"
            )
            done += 1
            print(f"[{i}/{total}] {st.slug} OK")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[{i}/{total}] {st.slug} FAILED: {exc}")

    print(f">>> previews done={done} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
