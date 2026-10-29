import os
from dataclasses import dataclass
from functools import lru_cache

_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret-change-me"
_DEV_DB = "postgresql+psycopg://postgres@localhost:5432/spendathon"


def _normalize_db_url(url: str) -> str:
    """Neon/Vercel give `postgres://` or `postgresql://`; SQLAlchemy needs the psycopg driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    token_ttl_days: int
    timezone: str
    cors_origins: list[str]


@lru_cache
def get_settings() -> Settings:
    in_prod = bool(os.environ.get("VERCEL_ENV") == "production")
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        if in_prod:
            raise RuntimeError("JWT_SECRET must be set in the Vercel project settings")
        secret = _DEV_SECRET
    db = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""
    if not db:
        if in_prod:
            raise RuntimeError("DATABASE_URL must be set (connect Neon to the Vercel project)")
        db = _DEV_DB
    return Settings(
        database_url=_normalize_db_url(db),
        jwt_secret=secret,
        token_ttl_days=int(os.environ.get("TOKEN_TTL_DAYS", "30")),
        timezone=os.environ.get("APP_TIMEZONE", "Asia/Kolkata"),
        cors_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
    )
