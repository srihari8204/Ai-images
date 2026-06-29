"""FastAPI application factory.

Wires middleware, exception handlers, and all module routers under the versioned
``/api/v1`` namespace, plus unversioned monitoring, webhook, and public share
routes. OpenAPI 3.1 is generated automatically (D: API-first).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app import __version__
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import AccessLogMiddleware, CorrelationIdMiddleware

# Routers
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.credits.router import router as credits_router
from app.modules.gallery.router import public_router as gallery_public_router
from app.modules.gallery.router import router as gallery_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.payments.router import router as billing_router
from app.modules.payments.router import webhook_router as payments_webhook_router
from app.modules.pipeline.router import router as jobs_router
from app.modules.prompts.router import router as prompts_router
from app.modules.styles.router import router as styles_router
from app.modules.uploads.router import router as uploads_router
from app.modules.users.router import router as users_router

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(json_logs=settings.is_prod, level="INFO")
    logger.info("startup", env=settings.environment.value, version=__version__)
    try:
        from app.storage import object_store

        object_store.ensure_buckets()
    except Exception as exc:  # noqa: BLE001 - storage may not be up yet in some envs
        logger.warning("bucket_init_skipped", error=str(exc))
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "API-first, self-hosted AI image-generation platform. "
            "All product capabilities are versioned HTTP endpoints under /api/v1."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ---- Middleware (order: correlation id outermost, then access log) ----
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "Retry-After"],
    )

    register_exception_handlers(app)

    # ---- Versioned API routers ----
    v1 = settings.api_v1_prefix
    app.include_router(auth_router, prefix=v1)
    app.include_router(users_router, prefix=v1)
    app.include_router(uploads_router, prefix=v1)
    app.include_router(prompts_router, prefix=v1)
    app.include_router(styles_router, prefix=v1)
    app.include_router(jobs_router, prefix=v1)
    app.include_router(gallery_router, prefix=v1)
    app.include_router(credits_router, prefix=v1)
    app.include_router(billing_router, prefix=v1)
    app.include_router(admin_router, prefix=v1)

    # ---- Unversioned routes ----
    app.include_router(monitoring_router)  # /healthz /readyz /metrics
    app.include_router(payments_webhook_router)  # /webhooks/payments
    app.include_router(gallery_public_router)  # /s/{share_token}

    _customize_openapi(app)
    return app


def _customize_openapi(app: FastAPI) -> None:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["openapi"] = "3.1.0"
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "BearerAuth"
        ] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        # Default bearer auth requirement (individual public routes opt out).
        schema["security"] = [{"BearerAuth": []}]
        schema["info"]["x-error-envelope"] = {
            "error": {"code": "string", "message": "string", "details": {}}
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi


app = create_app()
