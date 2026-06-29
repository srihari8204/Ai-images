"""Gallery endpoints and the public share-render route."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.gallery import service
from app.modules.gallery.schemas import (
    GalleryItem,
    GalleryItemDetail,
    GalleryPage,
    ShareRequest,
    ShareResponse,
    UpdateGalleryItem,
)

router = APIRouter(prefix="/gallery", tags=["gallery"])
# Public share route lives at the root (edge-cacheable), outside the gallery prefix.
public_router = APIRouter(tags=["gallery"])


def _item(image) -> GalleryItem:
    out = GalleryItem.model_validate(image)
    out.kind = image.kind.value
    out.visibility = image.visibility.value
    out.safety_status = image.safety_status.value
    out.url = service.presigned_url(image)
    return out


@router.get("", response_model=GalleryPage, summary="List your images")
async def list_gallery(
    user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(None),
    limit: int = Query(24, ge=1, le=100),
    kind: str | None = Query(None),
    favorite: bool | None = Query(None),
) -> GalleryPage:
    before = None
    if cursor:
        created, _ = decode_cursor(cursor)
        before = created
    images = await service.list_gallery(
        db, user.id, limit=limit + 1, before=before, kind=kind, favorite=favorite
    )
    has_more = len(images) > limit
    images = images[:limit]
    next_cursor = (
        encode_cursor(images[-1].created_at, images[-1].id) if has_more and images else None
    )
    return GalleryPage(
        items=[_item(i) for i in images], next_cursor=next_cursor, has_more=has_more
    )


@router.get("/{image_id}", response_model=GalleryItemDetail, summary="Image detail")
async def get_image(image_id: uuid.UUID, user: CurrentUser, db: DbSession) -> GalleryItemDetail:
    image = await service.get_owned(db, user.id, image_id)
    base = _item(image)
    return GalleryItemDetail(
        **base.model_dump(),
        job_id=image.job_id,
        content_hash=image.content_hash,
        meta=image.meta or {},
    )


@router.patch("/{image_id}", response_model=GalleryItem, summary="Update visibility/favorite")
async def update_image(
    image_id: uuid.UUID, req: UpdateGalleryItem, user: CurrentUser, db: DbSession
) -> GalleryItem:
    image = await service.get_owned(db, user.id, image_id)
    if req.visibility is not None:
        image = await service.set_visibility(db, user.id, image_id, req.visibility)
    if req.is_favorite is not None:
        image = await service.set_favorite(db, user.id, image_id, req.is_favorite)
    return _item(image)


@router.post("/{image_id}/share", response_model=ShareResponse, summary="Create/rotate share link")
async def share_image(
    image_id: uuid.UUID, req: ShareRequest, user: CurrentUser, db: DbSession
) -> ShareResponse:
    image = await service.create_share_link(db, user.id, image_id, rotate=req.rotate)
    return ShareResponse(
        share_token=image.share_token,
        share_url=f"{settings.public_base_url}/s/{image.share_token}",
    )


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete image")
async def delete_image(image_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    await service.delete_image(db, user.id, image_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/s/{share_token}", summary="Public render of a shared image")
async def render_shared(share_token: str, db: DbSession) -> RedirectResponse:
    image = await service.get_by_share_token(db, share_token)
    # Redirect to a presigned URL; the edge/CDN caches this route per token.
    url = service.presigned_url(image, ttl=3600)
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
