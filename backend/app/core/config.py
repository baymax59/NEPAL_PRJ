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

    # --- Case Management evidence (phase CM-2, docs/steps/15-2-evidence.md) ---
    # The write-once evidence store. Default: data_dir/evidence. Keep it on encrypted storage that is not
    # synced to a cloud service; for production, write-once storage is decision D14.
    evidence_dir: Path | None = None
    # Largest evidence file accepted. The web server's limit (deploy/Caddyfile) must be a little higher.
    max_evidence_mb: int = Field(default=100, ge=1)
    # How long a download link stays valid. Each link works once.
    evidence_download_minutes: int = Field(default=5, ge=1, le=60)
    # Programs (e.g. malware samples in a cyber case) are accepted as evidence, marked, and never run or
    # opened by the application. Set to false to refuse them (decision D14).
    evidence_accept_programs: bool = True

    # --- Case Management integrations (phase CM-6, docs/steps/15-6-integrations.md) ---
    # A phone number written without its country code (10 digits) is taken as a number of this country.
    cm_phone_country_code: str = Field(default="91", pattern=r"^[1-9]\d{0,2}$")
    # The built-in fictional test source (it stands in for the Log Analyzer, CDR/IPDR, OSINT and alerts until they
    # exist). Turn it off in production: CM_TEST_SOURCE=false.
    cm_test_source: bool = True

    # --- Case Management governance (phase CM-7, docs/steps/15-7-reports-and-governance.md) ---
    # The key that signs audit checkpoints. Keep it OUTSIDE the database, away from its administrators (decision D11).
    # Until it is set, a key derived from AUDIT_SECRET is used, and the readiness check says so.
    cm_checkpoint_key: SecretStr | None = Field(default=None, min_length=32)
    # The key that encrypts two-step verification secrets. Until it is set, one derived from JWT_SECRET is used.
    mfa_key: SecretStr | None = Field(default=None, min_length=32)
    # Platform administrators and supervisors must log in with two-step verification for privileged actions
    # (approvals, merges, sealing, access changes, legal holds, retention decisions, sources, checkpoints).
    cm_mfa_required: bool = False
    # The application's own database login, a member of the role cm_runtime (no DELETE on case records, no UPDATE
    # on permanent ones; migration 0014). Created by scripts.db_roles. Not set: the owner login above is used.
    postgres_app_user: str | None = Field(default=None, pattern=r"^[a-z_][a-z0-9_]{2,62}$")
    postgres_app_password: SecretStr | None = Field(default=None, min_length=16)
    # How often the worker (scripts.worker) looks for scheduled jobs that are due, in seconds.
    cm_worker_interval: int = Field(default=300, ge=10, le=86400)

    @field_validator("audit_retention_days", "evidence_dir", "cm_checkpoint_key", "mfa_key", "postgres_app_user",
                     "postgres_app_password", mode="before")
    @classmethod
    def _empty_means_not_set(cls, value: object) -> object:
        # Docker Compose passes an unset variable as an empty string: that means "not set" (keep audit
        # entries; the default evidence folder).
        return None if value == "" else value

    @property
    def evidence_root(self) -> Path:
        return self.evidence_dir or self.data_dir / "evidence"

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
    # The same, for the passages of a registered case (its summary and notes) compared with past cases. Notes are shorter and looser than
    # judgments, so they never come as close as two judgments do: with the real model, related text scores 0.70 to 0.78 and unrelated text
    # stays under 0.66 (measured on the 100 imported judgments). 0.80 left the Insights tab empty for every real case.
    case_similar_passage_min_similarity: float = 0.70
    # Load the model in the background when the API starts, so the first search isn't slow.
    preload_models: bool = True

    # --- Case chatbot (Step 13): a local model served by Ollama, so case text never leaves the machine ---
    ollama_url: str = "http://127.0.0.1:11434"
    # Apache-2.0 licence; ~2.5 GB; about 2-4 minutes per answer on this CPU (see docs/steps/13-*.md).
    chat_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    # Total time allowed for one answer. Some browsers stop waiting after 300 seconds, so stopping a
    # little earlier gives the user a clear message instead of a network error.
    chat_timeout_seconds: int = 280
    # Processor threads the model may use. 0 = all of this computer's logical processors. Ollama's own choice on this laptop was 6 of 12,
    # which read the question at about 12 words a second; all 12 read it at about 21 (measured), and an answer needs a quarter less time.
    chat_threads: int = Field(default=0, ge=0, le=256)

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
    # Officers create their own login on the sign-in page (docs/case-management/13, section 12). The account starts with view-only access
    # (Viewer, public clearance) and only for an officer in the register; a Supervisor or Administrator raises it. Set false to switch it off.
    self_registration: bool = True
    # Sign-up attempts allowed from one computer within the window (every attempt counts, successful or not).
    max_signups_per_ip: int = 10
    signup_window_minutes: int = 60
    failed_login_window_minutes: int = 15

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
        """The owner login: migrations (alembic) and scripts.db_roles."""
        # URL.create escapes special characters in the password correctly.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def runtime_database_url(self) -> URL:
        """The application's login: its own (role cm_runtime) when configured, otherwise the owner's."""
        if self.postgres_app_user and self.postgres_app_password is not None:
            return self.database_url.set(username=self.postgres_app_user, password=self.postgres_app_password.get_secret_value())
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
