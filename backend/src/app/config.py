import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Weak default values that must NOT be used in production.
_INSECURE_DEFAULTS = frozenset({"doe_password", "neo4j_password", "change-me", ""})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # PostgreSQL
    postgres_user: str = "doe_user"
    postgres_password: str = "doe_password"
    postgres_db: str = "doe_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic migrations (uses psycopg2)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Security
    api_secret_key: str = ""
    chat_rate_limit: str = "10/minute"
    auth_rate_limit: str = "5/minute"
    register_rate_limit: str = "3/hour"

    # JWT Authentication
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # SMTP Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Admin / Signup approval
    admin_emails: str = ""
    invite_token_expire_hours: int = 72
    frontend_url: str = "http://localhost:5173"

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def cors_allow_methods(self) -> list[str]:
        if self.app_env == "production":
            return ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
        return ["*"]

    @property
    def cors_allow_headers(self) -> list[str]:
        if self.app_env == "production":
            return ["Content-Type", "X-API-Key", "Authorization"]
        return ["*"]

    def validate_production_secrets(self) -> None:
        """Raise on insecure defaults when running in production.

        Called during application startup so the server refuses to start
        with weak or missing secrets.
        """
        if self.app_env != "production":
            return

        problems: list[str] = []

        if self.jwt_secret_key in _INSECURE_DEFAULTS:
            problems.append("JWT_SECRET_KEY is empty or uses a default value")
        if self.api_secret_key in _INSECURE_DEFAULTS:
            problems.append("API_SECRET_KEY is empty or uses a default value")
        if self.postgres_password in _INSECURE_DEFAULTS:
            problems.append("POSTGRES_PASSWORD uses a weak default value")
        if self.neo4j_password in _INSECURE_DEFAULTS:
            problems.append("NEO4J_PASSWORD uses a weak default value")

        if problems:
            msg = "Insecure configuration detected in production:\n  - " + "\n  - ".join(problems)
            raise SystemExit(msg)


settings = Settings()
