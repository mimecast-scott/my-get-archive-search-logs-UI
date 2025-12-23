from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # -------------------------------------------------
    # Mimecast API 2.0 – OAuth (client_credentials)
    # -------------------------------------------------
    mimecast_oauth_token_url: str = Field(
        default="https://api.services.mimecast.com/oauth/token",
        description="OAuth token endpoint for Mimecast API 2.0",
    )

    mimecast_api_base_url: str = Field(
        default="https://api.services.mimecast.com",
        description="Base URL for Mimecast API 2.0 endpoints",
    )

    mimecast_client_id: str = Field(
        ...,
        description="OAuth client_id from Mimecast",
    )

    mimecast_client_secret: str = Field(
        ...,
        description="OAuth client_secret from Mimecast",
    )

    # -------------------------------------------------
    # Polling behaviour
    # -------------------------------------------------
    initial_backfill_days: int = Field(
        default=30,
        description="Days to backfill on first startup",
    )

    poll_seconds: int = Field(
        default=3600,
        description="Polling interval in seconds",
    )

    lookback_seconds: int = Field(
        default=7200,
        description="Overlap window to avoid missing delayed events",
    )

    # -------------------------------------------------
    # Mimecast API pagination (IMPORTANT)
    # -------------------------------------------------
    archive_page_size: int = Field(
        default=100,
        description="Page size for Mimecast archive search logs API (API 2.0 pagination)",
    )

    # -------------------------------------------------
    # Database (libSQL / SQLite)
    # -------------------------------------------------
    db_path: str = Field(
        default="/data/searchlogs.db",
        description="Path to local libSQL/SQLite database file",
    )

    # Optional libSQL/Turso replication (kept for compatibility)
    libsql_url: str | None = Field(
        default=None,
        description="Optional libSQL/Turso remote URL",
    )

    libsql_auth_token: str | None = Field(
        default=None,
        description="Optional libSQL/Turso auth token",
    )

    # -------------------------------------------------
    # UI defaults
    # -------------------------------------------------
    default_days: int = Field(
        default=30,
        description="Default lookback window for UI (days)",
    )

    page_size: int = Field(
        default=50,
        description="Rows per page in user detail view",
    )

    class Config:
        env_file = ".env"
        case_sensitive = False


# Singleton settings object
settings = Settings()
