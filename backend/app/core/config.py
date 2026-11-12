"""Application settings, read from environment variables and the project-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# backend/app/core/config.py -> parents[3] is the project root (where .env lives).
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Similar Case Search API"
    environment: str = "development"

    postgres_user: str = "caseuser"
    # SecretStr keeps the password out of logs and error messages.
    postgres_password: SecretStr
    postgres_db: str = "casesdb"
    # 127.0.0.1 rather than "localhost": on Windows, "localhost" tries IPv6 first and stalls.
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433

    # Downloaded source files, extracted text and uploads (git-ignored).
    data_dir: Path = PROJECT_ROOT / "data"
    # Uploaded "new case" files: stored under data/uploads/, never served back directly.
    max_upload_mb: int = 20
    # Retention (Step 14.3, scripts/retention.py): uploads are deleted after this many days. Audit entries
    # are deleted only if audit_retention_days is set: that period is for your organisation to decide.
    upload_retention_days: int = Field(default=30, ge=1)
    audit_retention_days: int | None = Field(default=None, ge=1)

    @field_validator("audit_retention_days", mode="before")
    @classmethod
    def _empty_means_not_set(cls, value: object) -> object:
        # Docker Compose passes an unset variable as an empty string: that means "keep audit entries".
        return None if value == "" else value

    # Sentence-embedding model (MIT licence, 384 dimensions, runs on CPU), stored in models/
    # so a server without internet access can be prepared in advance.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    model_cache_dir: Path = PROJECT_ROOT / "models"
    # Passages less similar than this to a query count as unrelated. Measured for
    # bge-small-en-v1.5 on the Supreme Court subset: relevant queries' best matches 0.69-0.81,
    # unrelated queries ("chocolate cake recipe", "football score") at most 0.46-0.56.
    # Re-measure whenever the model changes (docs/steps/06-*.md shows how).
    semantic_min_similarity: float = 0.60
    # The same idea for passage-to-passage comparison (finding cases similar to a whole document).
    # Two passages of legal text are much closer to each other than a short query is to a
    # passage, so this needs its own, higher value (see docs/steps/08-*.md).
    similar_passage_min_similarity: float = 0.80
    # Load the model in the background when the API starts, so the first search isn't slow.
    preload_models: bool = True

    # --- Case chatbot (Step 13): a local model served by Ollama, so case text never leaves the machine ---
    ollama_url: str = "http://127.0.0.1:11434"
    # Apache-2.0 licence; ~2.5 GB; about 2-4 minutes per answer on this CPU (see docs/steps/13-*.md).
    chat_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    # Total time allowed for one answer. Some browsers stop waiting after 300 seconds, so stopping a
    # little earlier gives the user a clear message instead of a network error.
    chat_timeout_seconds: int = 280

    # --- Security (Step 10) ---
    # Required, at least 32 characters: the app refuses to start with a missing or weak secret.
    jwt_secret: SecretStr = Field(min_length=32)
    audit_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = 60
    # After this many wrong passwords in a row, the account is locked for lockout_minutes.
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Failed logins allowed from one computer, for any accounts, within the window (Step 14.2).
    max_failed_logins_per_ip: int = 20
    failed_login_window_minutes: int = 15

    # --- CDR Analysis integration ---
    # Set CDR_D1_JWT_KEY to the same key configured in the D1 backend AUTH_JWT_KEY.
    # If empty, the CDR Analysis button still appears but CDR D1 import won't be authenticated.
    cdr_d1_jwt_key: SecretStr | None = Field(default=None)
    # Base URLs for CDR backends (used by the host to proxy or health-check them).
    cdr_d1_api_url: str = Field(default="http://127.0.0.1:55491")
    cdr_d2_api_url: str = Field(default="http://127.0.0.1:55492")
    cdr_d3_api_url: str = Field(default="http://127.0.0.1:55493")
    # India profile: set CDR_MSISDN_RULE=in-msisdn.v1 and CDR_TIMEZONE=Asia/Kolkata for India.
    cdr_msisdn_rule: str = Field(default="in-msisdn.v1")
    cdr_timezone: str = Field(default="Asia/Kolkata")

    @model_validator(mode="after")
    def _safe_outside_development(self) -> "Settings":
        """Refuse to start a real installation with settings that are only acceptable on a developer's computer."""
        if self.environment == "development":
            return self
        problems = []
        if self.jwt_secret.get_secret_value() == self.audit_secret.get_secret_value():
            problems.append("JWT_SECRET and AUDIT_SECRET must be different")
        password = self.postgres_password.get_secret_value()
        if len(password) < 16 or "change-me" in password:
            problems.append("POSTGRES_PASSWORD must be at least 16 characters and not the example value")
        if problems:
            raise ValueError("Unsafe settings for ENVIRONMENT=" + self.environment + ": " + "; ".join(problems))
        return self

    @property
    def show_api_docs(self) -> bool:
        return self.environment == "development"

    @property
    def database_url(self) -> URL:
        # URL.create escapes special characters in the password correctly.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
