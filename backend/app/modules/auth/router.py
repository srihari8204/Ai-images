"""Authentication endpoints.

All endpoints under ``/auth`` are rate-limited per IP and per account to mitigate
brute-force and credential-stuffing (see ``core.rate_limit``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.dependencies import DbSession, get_client_ip
from app.core.rate_limit import enforce_auth_limit
from app.modules.auth import oauth, service
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    GenericMessage,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _token_pair(access: str, refresh: str) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_seconds,
    )


@router.post(
    "/register",
    response_model=GenericMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
async def register(req: RegisterRequest, request: Request, db: DbSession) -> GenericMessage:
    await enforce_auth_limit(get_client_ip(request), req.email)
    await service.register(db, req.email, req.password, req.display_name)
    return GenericMessage(
        message="If the email is available, a verification link has been sent."
    )


@router.post("/verify-email", response_model=GenericMessage, summary="Confirm email")
async def verify_email(req: VerifyEmailRequest, db: DbSession) -> GenericMessage:
    await service.verify_email(db, req.token)
    return GenericMessage(message="Email verified. You can now log in.")


@router.post("/login", response_model=TokenPair, summary="Log in")
async def login(req: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    await enforce_auth_limit(get_client_ip(request), req.email)
    access, refresh, _ = await service.login(
        db,
        req.email,
        req.password,
        user_agent=request.headers.get("user-agent"),
        ip=get_client_ip(request),
    )
    return _token_pair(access, refresh)


@router.post("/guest", response_model=TokenPair, summary="Start a guest session")
async def guest(request: Request, db: DbSession) -> TokenPair:
    access, refresh = await service.guest_session(
        db,
        user_agent=request.headers.get("user-agent"),
        ip=get_client_ip(request),
    )
    return _token_pair(access, refresh)


@router.post("/refresh", response_model=TokenPair, summary="Rotate tokens")
async def refresh(req: RefreshRequest, request: Request, db: DbSession) -> TokenPair:
    access, new_refresh, _ = await service.refresh(
        db,
        req.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip=get_client_ip(request),
    )
    return _token_pair(access, new_refresh)


@router.post("/logout", response_model=GenericMessage, summary="Revoke session")
async def logout(req: LogoutRequest, db: DbSession) -> GenericMessage:
    await service.logout(db, req.refresh_token)
    return GenericMessage(message="Logged out.")


@router.post(
    "/password/forgot", response_model=GenericMessage, summary="Request password reset"
)
async def forgot_password(
    req: ForgotPasswordRequest, request: Request, db: DbSession
) -> GenericMessage:
    await enforce_auth_limit(get_client_ip(request), req.email)
    await service.forgot_password(db, req.email)
    return GenericMessage(
        message="If the account exists, a reset link has been sent."
    )


@router.post(
    "/password/reset", response_model=GenericMessage, summary="Complete password reset"
)
async def reset_password(req: ResetPasswordRequest, db: DbSession) -> GenericMessage:
    await service.reset_password(db, req.token, req.password)
    return GenericMessage(message="Password updated. All sessions were revoked.")


# ---- OAuth ----
@router.get("/oauth/{provider}/start", summary="Begin OAuth login")
async def oauth_start(provider: str) -> RedirectResponse:
    url = await oauth.start(provider)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


async def _oauth_callback(provider: str, request: Request, db: DbSession) -> RedirectResponse:
    if request.method == "POST":
        form = await request.form()
        code, state = form.get("code"), form.get("state")
    else:
        code = request.query_params.get("code")
        state = request.query_params.get("state")
    if not code or not state:
        from app.core.errors import AuthError

        raise AuthError("Missing OAuth code/state", code="oauth_missing_params")
    access, refresh, _ = await oauth.callback(
        db, provider, code, state, ip=get_client_ip(request)
    )
    # Hand tokens to the SPA via fragment so they never hit server logs.
    target = f"{settings.frontend_base_url}/auth/oauth-complete#access_token={access}&refresh_token={refresh}"
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND)


@router.get("/oauth/{provider}/callback", summary="OAuth callback (redirect)")
async def oauth_callback_get(provider: str, request: Request, db: DbSession) -> RedirectResponse:
    return await _oauth_callback(provider, request, db)


@router.post("/oauth/{provider}/callback", summary="OAuth callback (form_post)")
async def oauth_callback_post(provider: str, request: Request, db: DbSession) -> RedirectResponse:
    return await _oauth_callback(provider, request, db)
