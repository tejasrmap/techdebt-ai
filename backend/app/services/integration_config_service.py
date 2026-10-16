import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from app.config import settings
from app.models.all_models import IntegrationSetting
from app.services.crypto_service import decrypt_credential

logger = logging.getLogger(__name__)

@dataclass
class OrgIntegrationConfig:
    org_id: str
    firecrawl_api_key: Optional[str] = None
    firecrawl_api_url: str = settings.FIRECRAWL_API_URL
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    memento_api_key: Optional[str] = None
    memento_endpoint: str = ""
    ai_model_name: str = settings.AI_MODEL_NAME
    default_ai_provider: str = settings.DEFAULT_AI_PROVIDER
    preferences: Dict[str, Any] = field(default_factory=dict)
    key_provenance: Dict[str, str] = field(default_factory=dict)

def get_org_integration_config(
    org_id: str,
    db: Session,
    allow_platform_fallback: Optional[bool] = None
) -> OrgIntegrationConfig:
    """
    Retrieves and securely decrypts organization-specific integration credentials.
    Enforces tenant isolation: Organization credentials are never shared across orgs.
    Platform-level environment credentials are only used as an explicitly allowed fallback.
    Never logs or exposes raw decrypted credentials.
    """
    if allow_platform_fallback is None:
        allow_platform_fallback = getattr(settings, "ALLOW_PLATFORM_INTEGRATION_FALLBACK", False)

    setting = db.query(IntegrationSetting).filter(IntegrationSetting.org_id == org_id).first()

    config = OrgIntegrationConfig(org_id=org_id)
    provenance: Dict[str, str] = {}

    # 1. Firecrawl Credentials
    org_firecrawl = decrypt_credential(setting.firecrawl_api_key) if setting and setting.firecrawl_api_key else ""
    if org_firecrawl and len(org_firecrawl.strip()) > 5:
        config.firecrawl_api_key = org_firecrawl.strip()
        provenance["firecrawl"] = "org_setting"
    elif allow_platform_fallback and settings.FIRECRAWL_API_KEY and len(settings.FIRECRAWL_API_KEY.strip()) > 5:
        config.firecrawl_api_key = settings.FIRECRAWL_API_KEY.strip()
        provenance["firecrawl"] = "platform_fallback"
    else:
        config.firecrawl_api_key = None
        provenance["firecrawl"] = "none"

    # 2. OpenAI Credentials
    org_openai = decrypt_credential(setting.openai_api_key) if setting and setting.openai_api_key else ""
    if org_openai and len(org_openai.strip()) > 5:
        config.openai_api_key = org_openai.strip()
        provenance["openai"] = "org_setting"
    elif allow_platform_fallback and settings.OPENAI_API_KEY and len(settings.OPENAI_API_KEY.strip()) > 5:
        config.openai_api_key = settings.OPENAI_API_KEY.strip()
        provenance["openai"] = "platform_fallback"
    else:
        config.openai_api_key = None
        provenance["openai"] = "none"

    # 3. Gemini Credentials
    org_gemini = decrypt_credential(setting.gemini_api_key) if setting and setting.gemini_api_key else ""
    if org_gemini and len(org_gemini.strip()) > 5:
        config.gemini_api_key = org_gemini.strip()
        provenance["gemini"] = "org_setting"
    elif allow_platform_fallback and settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY.strip()) > 5:
        config.gemini_api_key = settings.GEMINI_API_KEY.strip()
        provenance["gemini"] = "platform_fallback"
    else:
        config.gemini_api_key = None
        provenance["gemini"] = "none"

    # 4. Historical Assessment Memory (PostgreSQL Authoritative)
    config.memento_api_key = None
    config.memento_endpoint = ""
    provenance["historical_storage"] = "postgresql_authoritative"
    provenance["memento"] = "postgresql_authoritative"

    # 5. Preferences & Models
    if setting and setting.preferences:
        config.preferences = setting.preferences
        if "default_ai_provider" in setting.preferences:
            config.default_ai_provider = setting.preferences["default_ai_provider"]
        if "ai_model_name" in setting.preferences:
            config.ai_model_name = setting.preferences["ai_model_name"]

    config.key_provenance = provenance
    return config

def get_firecrawl_service_for_org(org_id: str, db: Session):
    from app.services.firecrawl_service import FirecrawlIntelligenceService
    cfg = get_org_integration_config(org_id, db)
    return FirecrawlIntelligenceService(
        api_key=config_firecrawl_key(cfg),
        api_url=cfg.firecrawl_api_url
    )

def config_firecrawl_key(cfg: OrgIntegrationConfig) -> Optional[str]:
    return cfg.firecrawl_api_key

def get_ai_analyzer_for_org(org_id: str, db: Session):
    from app.services.ai_analyzer import AITechnologyDebtAnalyzer
    cfg = get_org_integration_config(org_id, db)
    return AITechnologyDebtAnalyzer(
        gemini_api_key=cfg.gemini_api_key,
        openai_api_key=cfg.openai_api_key,
        model_name=cfg.ai_model_name
    )

def get_historical_memory_adapter_for_org(org_id: str, db: Session):
    from app.services.historical_memory_adapter import HistoricalAssessmentMemoryAdapter
    # Historical assessment storage is backed exclusively by PostgreSQL
    return HistoricalAssessmentMemoryAdapter()

# Backwards-compatibility alias (Deprecated in v1.0.8, scheduled for removal in v1.1.0)
get_memento_adapter_for_org = get_historical_memory_adapter_for_org

