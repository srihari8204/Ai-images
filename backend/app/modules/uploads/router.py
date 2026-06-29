"""Image upload endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, UploadFile, status

from app.core.dependencies import CurrentUser, DbSession
from app.modules.uploads import service
from app.modules.uploads.schemas import (
    ImageOut,
    PresignRequest,
    PresignResponse,
    RegisterRequest,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _to_out(image, *, with_url: bool = True) -> ImageOut:
    out = ImageOut.model_validate(image)
    if with_url:
        out.url = service.presigned_get_url(image)
    return out


@router.post("/presign", response_model=PresignResponse, summary="Get presigned PUT URL")
async def presign(req: PresignRequest, user: CurrentUser, db: DbSession) -> PresignResponse:
    data = await service.presign_upload(db, user.id, req.content_type)
    return PresignResponse(**data)


@router.post(
    "",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a presigned upload, or upload directly (multipart fallback)",
)
async def create_upload(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile | None = File(default=None),
    object_key: str | None = None,
) -> ImageOut:
    if file is not None:
        raw = await file.read()
        image = await service.upload_multipart(db, user.id, raw)
    elif object_key:
        image = await service.register_presigned(db, user.id, object_key)
    else:
        from app.core.errors import ValidationAppError

        raise ValidationAppError("Provide either a multipart file or an object_key")
    return _to_out(image)


@router.post(
    "/register",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a presigned upload by object key",
)
async def register(req: RegisterRequest, user: CurrentUser, db: DbSession) -> ImageOut:
    image = await service.register_presigned(db, user.id, req.object_key)
    return _to_out(image)


@router.get("/{image_id}", response_model=ImageOut, summary="Upload metadata + URL")
async def get_upload(image_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ImageOut:
    image = await service.get_image_for_owner(db, user.id, image_id)
    return _to_out(image)
