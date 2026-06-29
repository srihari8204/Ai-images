"""User profile, settings, consent, export, and deletion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, DbSession
from app.modules.users import service
from app.modules.users.schemas import (
    ConsentOut,
    ConsentRequest,
    ExportOut,
    ProfileOut,
    ProfileUpdate,
    SettingsOut,
    SettingsUpdate,
)

router = APIRouter(tags=["users"])


def _profile(user) -> ProfileOut:
    return ProfileOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_image_id=user.avatar_image_id,
        locale=user.locale,
        status=user.status.value,
        roles=user.role_names,
        email_verified=user.is_verified,
        created_at=user.created_at,
    )


@router.get("/me", response_model=ProfileOut, summary="Get current profile")
async def get_me(user: CurrentUser) -> ProfileOut:
    return _profile(user)


@router.patch("/me", response_model=ProfileOut, summary="Update profile")
async def update_me(req: ProfileUpdate, user: CurrentUser, db: DbSession) -> ProfileOut:
    await service.update_profile(
        db,
        user,
        display_name=req.display_name,
        locale=req.locale,
        avatar_image_id=req.avatar_image_id,
    )
    return _profile(user)


@router.get("/me/settings", response_model=SettingsOut, summary="Get settings")
async def get_settings(user: CurrentUser) -> SettingsOut:
    return SettingsOut(settings=user.settings_json or {})


@router.patch("/me/settings", response_model=SettingsOut, summary="Update settings")
async def update_settings(
    req: SettingsUpdate, user: CurrentUser, db: DbSession
) -> SettingsOut:
    merged = await service.update_settings(db, user, req.settings)
    return SettingsOut(settings=merged)


@router.post(
    "/me/consents",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record consent",
)
async def record_consent(
    req: ConsentRequest, user: CurrentUser, db: DbSession
) -> ConsentOut:
    consent = await service.record_consent(db, user, req.type, req.version, req.granted)
    return ConsentOut.model_validate(consent)


@router.get("/me/consents", response_model=list[ConsentOut], summary="List consents")
async def list_consents(user: CurrentUser, db: DbSession) -> list[ConsentOut]:
    rows = await service.list_consents(db, user.id)
    return [ConsentOut.model_validate(r) for r in rows]


@router.post(
    "/me/export",
    response_model=ExportOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request data export",
)
async def request_export(user: CurrentUser, db: DbSession) -> ExportOut:
    export = await service.request_export(db, user)
    return ExportOut.model_validate(export)


@router.delete(
    "/me", status_code=status.HTTP_202_ACCEPTED, summary="Delete account"
)
async def delete_account(user: CurrentUser, db: DbSession) -> dict:
    await service.soft_delete_account(db, user)
    return {"message": "Account scheduled for deletion. Sessions revoked."}
