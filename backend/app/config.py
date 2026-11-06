import os
import sys
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, field_validator


def _load_dotenv_files() -> None:
    """Load key=value pairs from .env files without overriding existing env vars."""
    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parent
    for env_path in (repo_root / ".env", backend_dir / ".env"):
        if env_path.is_file():
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, val)


_load_dotenv_files()

DEFAULT_DEV_SECRET = "techdebt-ai-super-secret-development-key-2025-jwt"
PROHIBITED_SECRET_DEFAULTS = {
    DEFAULT_DEV_SECRET,
    "techdebt-ai-production-super-secret-key-jwt-2025",
    "techdebt-ai-fernet-encryption-key-prod-2025",
    "changeme",
    "secret",
    "password",
    "admin",
    "12345678"
}

PROHIBITED_PLACEHOLDER_SUBSTRINGS = [
    "replace-with",
    "your-secret",
    "example-key",
    "change-me",
    "changeme",
    "default",
    "techdebt-ai-super-secret",
    "techdebt-ai-production-super-secret",
    "techdebt-ai-fernet-encryption-key"
]

def contains_prohibited_placeholder(value: Optional[str]) -> bool:
    if not value or not value.strip():
        return True
    val_lower = value.strip().lower()
    return any(p in val_lower for p in PROHIBITED_PLACEHOLDER_SUBSTRINGS)

class Settings(BaseModel):
    PROJECT_NAME: str = "TechDebt AI"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # JWT Security
    SECRET_KEY: str = DEFAULT_DEV_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Database & Supabase Integration
    DATABASE_URL: str = "sqlite:///./techdebt.db"
    SUPABASE_PROJECT_ID: Optional[str] = ""
    SUPABASE_URL: Optional[str] = ""
    SUPABASE_PUBLISHABLE_KEY: Optional[str] = ""
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = ""

    # AI Providers
    OPENAI_API_KEY: Optional[str] = ""
    GEMINI_API_KEY: Optional[str] = ""
    ANTHROPIC_API_KEY: Optional[str] = ""
    DEFAULT_AI_PROVIDER: str = "gemini"
    AI_MODEL_NAME: str = "gemini-1.5-flash"
    AI_TEMPERATURE: float = 0.2

    # Web Intelligence Engine
    FIRECRAWL_API_KEY: Optional[str] = ""
    FIRECRAWL_API_URL: str = "https://api.firecrawl.dev/v1"

    # Security & Upload Validation
    MAX_UPLOAD_SIZE_BYTES: int = 2 * 1024 * 1024  # 2 MB max
    ENABLE_DEMO_SEED: bool = True
    ENCRYPTION_KEY: Optional[str] = ""
    ALLOW_PLATFORM_INTEGRATION_FALLBACK: bool = False

    # CORS Origins
    CORS_ORIGINS: List[str] = []

    def __init__(self, **values):
        values.setdefault("ENVIRONMENT", os.getenv("ENVIRONMENT", "development").lower())
        values.setdefault("SECRET_KEY", os.getenv("SECRET_KEY", DEFAULT_DEV_SECRET))
        values.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", "sqlite:///./techdebt.db"))
        values.setdefault("SUPABASE_PROJECT_ID", os.getenv("SUPABASE_PROJECT_ID", ""))
        values.setdefault("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
        values.setdefault("SUPABASE_PUBLISHABLE_KEY", os.getenv("SUPABASE_PUBLISHABLE_KEY", ""))
        values.setdefault("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
        values.setdefault("ENCRYPTION_KEY", os.getenv("ENCRYPTION_KEY", ""))
        values.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        values.setdefault("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        values.setdefault("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
        values.setdefault("DEFAULT_AI_PROVIDER", os.getenv("DEFAULT_AI_PROVIDER", "gemini"))
        values.setdefault("AI_MODEL_NAME", os.getenv("AI_MODEL_NAME", "gemini-1.5-flash"))
        values.setdefault("AI_TEMPERATURE", float(os.getenv("AI_TEMPERATURE", "0.2")))
        values.setdefault("FIRECRAWL_API_KEY", os.getenv("FIRECRAWL_API_KEY", ""))
        values.setdefault("FIRECRAWL_API_URL", os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v1"))
        values.setdefault("ENABLE_DEMO_SEED", os.getenv("ENABLE_DEMO_SEED", "true").lower() == "true")
        values.setdefault("ALLOW_PLATFORM_INTEGRATION_FALLBACK", os.getenv("ALLOW_PLATFORM_INTEGRATION_FALLBACK", "false").lower() == "true")
        values.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")))

        super().__init__(**values)
        raw_origins = os.getenv("CORS_ORIGINS", "")
        if raw_origins:
            self.CORS_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]
        else:
            if self.ENVIRONMENT == "production":
                # In production, require explicit origins or default to localhost domain without wildcard
                self.CORS_ORIGINS = ["http://localhost", "https://localhost"]
            else:
                self.CORS_ORIGINS = [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:3000",
                    "http://localhost:8000"
                ]

        # Enforce strong secret key and encryption key in production
        if self.ENVIRONMENT == "production":
            # 1. Validate SECRET_KEY
            if not self.SECRET_KEY or len(self.SECRET_KEY) < 32 or self.SECRET_KEY in PROHIBITED_SECRET_DEFAULTS or contains_prohibited_placeholder(self.SECRET_KEY):
                raise ValueError(
                    "FATAL SECURITY VIOLATION: In production, SECRET_KEY must be a cryptographically secure random secret "
                    "at least 32 characters long. Placeholder values, known defaults, and template values from .env.example "
                    "(e.g. 'replace-with', 'your-secret', 'change-me') are strictly rejected."
                )

            # 2. Validate ENCRYPTION_KEY
            if not self.ENCRYPTION_KEY or len(self.ENCRYPTION_KEY) < 16 or self.ENCRYPTION_KEY in PROHIBITED_SECRET_DEFAULTS or contains_prohibited_placeholder(self.ENCRYPTION_KEY):
                raise ValueError(
                    "FATAL SECURITY VIOLATION: In production, ENCRYPTION_KEY must be a cryptographically secure key "
                    "at least 16 characters long. Placeholder values, known defaults, and template values from .env.example "
                    "(e.g. 'replace-with', 'your-secret', 'change-me') are strictly rejected."
                )

            # 3. Reject known default database credentials in production
            if any(p in self.DATABASE_URL.lower() for p in ["postgrespassword", ":password@", "replace-with", "your-secret", "change-me"]):
                raise ValueError(
                    "FATAL SECURITY VIOLATION: In production, DATABASE_URL must not use default, placeholder, or template credentials."
                )

settings = Settings()
