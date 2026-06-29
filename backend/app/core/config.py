"""Application settings.

Environment-driven configuration with separate dev/prod profiles. Settings are
loaded once and cached; import :func:`get_settings` everywhere rather than
reading ``os.environ`` directly so behaviour stays testable and consistent.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"
    TEST = "test"


class Settings(BaseSettings):
    """Central configuration object.

    Values are read from environment variables (case-insensitive) and an
    optional ``.env`` file. Nested groups use the ``__`` delimiter, e.g.
    ``DB__POOL_SIZE``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Core ----
    environment: Environment = Environment.DEV
    debug: bool = False
    app_name: str = "AI Mirror Platform"
    api_v1_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"

    # ---- Security / JWT ----
    secret_key: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 15 * 60  # <= 15 minutes per spec
    refresh_token_ttl_seconds: int = 30 * 24 * 3600
    email_verification_ttl_seconds: int = 24 * 3600
    password_reset_ttl_seconds: int = 3600
    password_min_length: int = 10

    # ---- CORS ----
    # NoDecode: keep the raw env string so the CSV validator below handles it
    # (pydantic-settings otherwise JSON-decodes list fields and rejects "a,b").
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # ---- Database ----
    database_url: str = "postgresql+asyncpg://aimirror:aimirror@localhost:5432/aimirror"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_echo: bool = False

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "generation"
    queue_dlq_name: str = "generation-dead"

    # ---- Object storage (MinIO / S3) ----
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_use_ssl: bool = False
    bucket_uploads: str = "uploads"
    bucket_outputs: str = "outputs"
    bucket_exports: str = "exports"
    presign_ttl_seconds: int = 900

    # ---- Upload limits ----
    upload_max_bytes: int = 25 * 1024 * 1024
    upload_min_dimension: int = 64
    upload_max_dimension: int = 8192
    upload_allowed_mime: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )

    # ---- Rate limiting (per window) ----
    rate_limit_auth_per_ip: int = 20
    rate_limit_auth_per_account: int = 10
    rate_limit_window_seconds: int = 300

    # ---- Generation backend ----
    # "auto"    -> try FLUX.1 on GPU, else deterministic CPU stand-in
    # "sdturbo" -> real SD-Turbo diffusion on CPU (local testing, no GPU)
    # "flux"    -> require FLUX.1 (production GPU)
    generation_backend: str = "auto"
    # CPU diffusion model for local testing. Defaults to SD-Turbo (few-step), but
    # any diffusers text2img checkpoint works — e.g. segmind/tiny-sd (~0.5GB) for
    # slow networks, with steps≈20 and guidance≈7.5.
    sdturbo_model: str = "stabilityai/sd-turbo"
    sdturbo_steps: int = 2
    sdturbo_guidance: float = 0.0

    # ---- Real model references (used on GPU; mounted/downloaded weights) ----
    flux_model: str = "black-forest-labs/FLUX.1-dev"
    flux_controlnet_model: str = "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro"
    # InstantID is SDXL-based; point these at the downloaded weights.
    instantid_base_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    instantid_repo: str = "InstantX/InstantID"  # ControlNet + ip-adapter
    insightface_root: str = "/models/insightface"
    gfpgan_model_path: str = (
        "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth"
    )
    realesrgan_model_path: str = (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
    )
    torch_device: str = "cuda"  # "cuda" on GPU; "cpu" locally
    # NSFW image classifier (optional). When enabled the worker/API screens with a
    # real model; otherwise the lightweight heuristic is used.
    enable_nsfw_model: bool = False
    nsfw_model: str = "Falconsai/nsfw_image_detection"

    # ---- Generation / pricing ----
    base_job_cost_credits: int = 1
    max_steps: int = 50
    max_resolution: int = 1536
    job_max_retries: int = 3
    job_retry_base_delay_seconds: int = 5
    nsfw_threshold: float = 0.85

    # ---- Payments ----
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    payments_allow_negative_balance: bool = True  # refunds may overdraw per policy

    # ---- OAuth ----
    google_client_id: str = ""
    google_client_secret: str = ""
    apple_client_id: str = ""
    apple_client_secret: str = ""

    # ---- Retention ----
    purge_retention_days: int = 30

    # ---- Email (dev: log only) ----
    email_from: str = "no-reply@aimirror.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    @field_validator("cors_origins", "upload_allowed_mime", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.startswith("["):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_prod(self) -> bool:
        return self.environment in (Environment.PROD, Environment.STAGING)

    @property
    def sync_database_url(self) -> str:
        """Synchronous DSN for Alembic and the RQ worker."""
        return self.database_url.replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
