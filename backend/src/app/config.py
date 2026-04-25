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
    feedback_rate_limit: str = "20/hour"

    # Tool execution
    # ``tool_safe_mode`` routes process_improve calls through
    # safe_execute_tool_call (subprocess isolation + timeout + memory cap).
    # Disable in tests / notebooks for speed; leave on in hosted deployments.
    tool_safe_mode: bool = True
    tool_timeout_seconds: float = 300.0
    tool_memory_mb: int = 2048
    tool_max_cells: int = 1_000_000
    tool_max_string: int = 100_000

    # DOE upload (Excel/CSV ingestion via Claude). ``upload_max_bytes`` is the
    # raw file size cap; ``upload_max_cells`` bounds how much of the parsed
    # 2D matrix we will hand to Claude in a single round-trip.
    upload_max_bytes: int = 5 * 1024 * 1024
    upload_max_cells: int = 10_000

    # Fake-data simulator. When true, reveal_simulator dispatches with
    # confirmed=True on the FIRST call and bypasses the user-confirmation
    # gate. Intended only for debugging or internal tooling; keep false
    # in production so the LLM cannot leak the hidden model uninvited.
    simulator_reveal_force: bool = False

    # MCP server (hosted). Exposes the process_improve tool registry over
    # HTTP + SSE. Gated by auth + per-identity CPU budget; off by default
    # until an operator explicitly turns it on.
    mcp_enabled: bool = False
    mcp_rate_limit: str = "30/minute"
    mcp_daily_cpu_seconds: int = 3600
    mcp_path_prefix: str = "/mcp"

    # Browser session cookies.
    # ``factorial_session`` is the httpOnly cookie carrying an opaque
    # session id (looked up directly in the ``sessions`` table). There is
    # no signing key in the loop, so server redeploys are
    # session-transparent. ``factorial_csrf`` is a non-httpOnly cookie
    # mirrored into ``X-CSRF-Token`` on state-changing requests.
    cookie_session_idle_days: int = 30
    cookie_session_absolute_days: int = 180

    @property
    def cookie_secure(self) -> bool:
        """Send cookies with the ``Secure`` attribute only in production.

        Dev runs over plain http://localhost; ``Secure`` would prevent
        the cookie from being set in that case.
        """
        return self.app_env == "production"

    # SMTP Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Signup approval / setup tokens
    invite_token_expire_hours: int = 72
    frontend_url: str = "http://localhost:5173"

    # Shareable experiment links
    share_token_expire_days: int = 30
    share_token_length: int = 32

    # Exports
    exports_enable_pdf: bool = True
    exports_chromium_path: str | None = None
    public_share_rate_limit: str = "30/minute"

    # GeoIP
    # Path to a MaxMind GeoLite2-Country.mmdb file. If unset or missing,
    # country lookup is silently skipped — login flows continue normally.
    geoip_country_db_path: str | None = None

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

        if self.api_secret_key in _INSECURE_DEFAULTS:
            problems.append(
                "API_SECRET_KEY is empty or uses a default value (also used "
                "to sign sqladmin sessions)",
            )
        if self.postgres_password in _INSECURE_DEFAULTS:
            problems.append("POSTGRES_PASSWORD uses a weak default value")
        if self.neo4j_password in _INSECURE_DEFAULTS:
            problems.append("NEO4J_PASSWORD uses a weak default value")

        if problems:
            msg = "Insecure configuration detected in production:\n  - " + "\n  - ".join(problems)
            raise SystemExit(msg)


settings = Settings()
