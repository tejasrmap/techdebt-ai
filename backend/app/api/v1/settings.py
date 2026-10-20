from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import IntegrationSetting, User, AuditLog
from app.schemas.schemas import IntegrationSettingsUpdate, IntegrationSettingsResponse
from app.services.auth_service import get_current_user, require_roles
from app.services.crypto_service import encrypt_credential, decrypt_credential
from app.config import settings

router = APIRouter(prefix="/settings", tags=["Settings & Integrations"])

@router.get("", response_model=IntegrationSettingsResponse)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = db.query(IntegrationSetting).filter(IntegrationSetting.org_id == current_user.org_id).first()
    
    from app.services.integration_config_service import get_org_integration_config
    cfg = get_org_integration_config(current_user.org_id, db)
    
    # Check if keys configured for this organization (or via explicit platform fallback)
    has_firecrawl = bool(cfg.firecrawl_api_key)
    has_openai = bool(cfg.openai_api_key)
    has_gemini = bool(cfg.gemini_api_key)

    return IntegrationSettingsResponse(
        firecrawl_configured=has_firecrawl,
        openai_configured=has_openai,
        gemini_configured=has_gemini,
        historical_memory_storage="postgresql_authoritative",
        memento_configured=True,
        memento_mode="postgresql",
        memento_endpoint="",
        preferences=setting.preferences if setting and setting.preferences else {
            "default_ai_provider": settings.DEFAULT_AI_PROVIDER,
            "auto_risk_creation": True,
            "min_confidence_threshold": "Medium",
            "strict_license_checks": True
        }
    )

@router.post("", response_model=IntegrationSettingsResponse)
def update_settings(
    req: IntegrationSettingsUpdate,
    current_user: User = Depends(require_roles(["Administrator"])),
    db: Session = Depends(get_db)
):
    """Administrator-only endpoint to configure organization integration secrets."""
    setting = db.query(IntegrationSetting).filter(IntegrationSetting.org_id == current_user.org_id).first()
    if not setting:
        setting = IntegrationSetting(org_id=current_user.org_id)
        db.add(setting)

    # Encrypt credentials at rest before storing in database
    if req.firecrawl_api_key is not None:
        setting.firecrawl_api_key = encrypt_credential(req.firecrawl_api_key) if req.firecrawl_api_key else ""
    if req.openai_api_key is not None:
        setting.openai_api_key = encrypt_credential(req.openai_api_key) if req.openai_api_key else ""
    if req.gemini_api_key is not None:
        setting.gemini_api_key = encrypt_credential(req.gemini_api_key) if req.gemini_api_key else ""
    if req.preferences is not None:
        setting.preferences = req.preferences

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="settings.integrations_updated",
        resource_type="integration_settings",
        resource_id=setting.id,
        details={"updated_by": current_user.email}
    )
    db.add(audit)
    db.commit()
    db.refresh(setting)

    return get_settings(current_user, db)

@router.post("/verify/{service_name}")
async def verify_integration(
    service_name: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    """Test connection to third-party services without leaking keys."""
    service_name = service_name.lower()
    setting = db.query(IntegrationSetting).filter(IntegrationSetting.org_id == current_user.org_id).first()
    
    if service_name == "firecrawl":
        from app.services.integration_config_service import get_firecrawl_service_for_org
        svc = get_firecrawl_service_for_org(current_user.org_id, db)
        return await svc.verify_connectivity()

    elif service_name in ["memento", "historical_memory"]:
        from app.services.integration_config_service import get_historical_memory_adapter_for_org
        mem = get_historical_memory_adapter_for_org(current_user.org_id, db)
        return await mem.verify_connectivity()

    elif service_name in ["gemini", "openai"]:
        from app.services.integration_config_service import get_ai_analyzer_for_org
        analyzer = get_ai_analyzer_for_org(current_user.org_id, db)
        return await analyzer.verify_connectivity(service_name)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown service '{service_name}'. Supported: firecrawl, memento, gemini, openai.")
