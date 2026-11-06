import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- Auth & User ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    organization_name: str
    # NOTE: Public role selection removed for security! Creator is strictly Administrator.

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return v

    @field_validator("organization_name")
    @classmethod
    def validate_org_name(cls, v: str) -> str:
        v_clean = v.strip()
        if len(v_clean) < 2:
            raise ValueError("Organization name must be at least 2 characters")
        return v_clean

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    org_id: str
    organization_name: Optional[str] = None
    is_verified: bool = False
    is_active: bool = True
    mfa_enabled: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# --- Organization Invitation ---
class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = "Developer"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = ["Administrator", "Engineering Manager", "Developer", "Viewer"]
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(allowed)}")
        return v

class InvitationResponse(BaseModel):
    id: str
    org_id: str
    email: str
    role: str
    token: str
    invitation_url: Optional[str] = None
    expires_at: datetime
    is_accepted: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class InvitationAccept(BaseModel):
    token: str
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return v

# --- Project ---
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    repository_url: Optional[str] = ""
    languages: Optional[List[str]] = []
    frameworks: Optional[List[str]] = []
    owner_name: Optional[str] = "Engineering Team"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v_clean = v.strip()
        if not v_clean:
            raise ValueError("Project name cannot be empty")
        return v_clean

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repository_url: Optional[str] = None
    languages: Optional[List[str]] = None
    frameworks: Optional[List[str]] = None
    owner_name: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    org_id: str
    name: str
    description: str
    repository_url: str
    languages: List[str]
    frameworks: List[str]
    owner_name: str
    created_at: datetime
    updated_at: datetime
    last_assessment_date: Optional[datetime] = None
    technology_count: Optional[int] = 0
    health_score: Optional[float] = None  # None when unassessed (avoids misleading 100)
    risk_classification: Optional[str] = None
    is_archived: bool = False
    model_config = {"from_attributes": True}

# --- Technology ---
class TechnologyCreate(BaseModel):
    name: str
    ecosystem: Optional[str] = "npm"
    category: Optional[str] = "Library"
    installed_version: Optional[str] = "latest"
    latest_stable_version: Optional[str] = "unknown"
    description: Optional[str] = ""
    project_id: Optional[str] = None

class DependencyImportRequest(BaseModel):
    project_id: str
    file_name: str
    content: str  # Content of package.json, requirements.txt, etc.

class TechnologyResponse(BaseModel):
    id: str
    name: str
    ecosystem: str
    category: str
    installed_version: Optional[str] = "latest"
    latest_stable_version: str
    description: str
    website_url: Optional[str] = ""
    repo_url: Optional[str] = ""
    is_deprecated: bool = False
    is_eol: bool = False
    health_score: Optional[float] = None
    risk_classification: Optional[str] = None
    model_config = {"from_attributes": True}

# --- Assessment ---
class AssessmentRunRequest(BaseModel):
    project_id: str
    trigger_type: Optional[str] = "manual"
    force_refresh_intel: Optional[bool] = False

class EvidenceSourceResponse(BaseModel):
    id: str
    url: str
    title: str
    source_type: str
    reliability_score: float
    publication_date: Optional[str] = None
    is_official: bool
    snippet: str

class TechnologyScoreResponse(BaseModel):
    technology_id: str
    technology_name: str
    installed_version: str
    latest_stable_version: str
    overall_score: float
    risk_classification: str
    maintenance_health: float
    security_exposure: float
    version_currency: float
    community_activity: float
    documentation_quality: float
    ecosystem_compatibility: float
    sustainability: float
    upgrade_complexity: float
    confidence_level: str
    recommended_action: str
    upgrade_complexity_level: str
    notes: str
    evidence: List[EvidenceSourceResponse] = []

class AssessmentResponse(BaseModel):
    id: str
    project_id: str
    project_name: Optional[str] = None
    trigger_type: str
    status: str
    overall_health_score: Optional[float] = None
    risk_classification: str
    confidence_level: str
    summary: str
    created_at: datetime
    scores: List[TechnologyScoreResponse] = []
    risks_count: Optional[int] = 0
    model_config = {"from_attributes": True}

# --- Risk Management ---
class RiskUpdate(BaseModel):
    status: Optional[str] = None  # Open, Investigating, Planned, In Progress, Resolved, Accepted Risk
    severity: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None

class RiskResponse(BaseModel):
    id: str
    project_id: str
    project_name: Optional[str] = None
    technology_id: str
    technology_name: Optional[str] = None
    severity: str
    title: str
    description: str
    business_impact: str
    technical_impact: str
    status: str
    assigned_to: Optional[str] = None
    assignee_name: Optional[str] = None
    resolution_notes: str
    resolved_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}

# --- Comparison ---
class TechnologyComparisonRequest(BaseModel):
    technology_names: List[str] = Field(..., min_length=2, max_length=4)

class ComparisonCategory(BaseModel):
    category: str
    scores: Dict[str, float]
    analysis: str

class TechnologyComparisonResponse(BaseModel):
    technologies: List[str]
    categories: List[ComparisonCategory]
    balanced_summary: str
    tradeoffs: Dict[str, List[str]]
    recommendations: str

# --- Scheduler ---
class ScheduledReviewCreate(BaseModel):
    project_id: str
    frequency: str  # Weekly, Monthly, Daily, Custom
    cron_expression: Optional[str] = "0 0 * * 1"
    is_active: Optional[bool] = True

class ScheduledReviewUpdate(BaseModel):
    frequency: Optional[str] = None
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None

class ScheduledReviewResponse(BaseModel):
    id: str
    project_id: str
    project_name: Optional[str] = None
    frequency: str
    cron_expression: str
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}

# --- Settings & Integrations ---
class IntegrationSettingsUpdate(BaseModel):
    firecrawl_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None

class IntegrationSettingsResponse(BaseModel):
    firecrawl_configured: bool
    openai_configured: bool
    gemini_configured: bool
    historical_memory_storage: str = "postgresql_authoritative"
    # Legacy compatibility fields
    memento_configured: bool = True
    memento_mode: str = "postgresql"
    memento_endpoint: str = ""
    preferences: Dict[str, Any]

# --- Dashboard Summary ---
class DashboardOverviewResponse(BaseModel):
    total_projects: int
    total_technologies: int
    technologies_requiring_attention: int
    critical_technology_risks: int
    overall_health_score: Optional[float] = None
    outdated_dependencies: int
    declining_maintenance_count: int
    health_distribution: Dict[str, int]
    risk_distribution: Dict[str, int]
    recent_assessments: List[Dict[str, Any]]
    historical_trend: List[Dict[str, Any]]
    project_health_breakdown: List[Dict[str, Any]]
    total_financial_liability_usd: Optional[float] = 0.0
    average_technical_debt_ratio: Optional[float] = 0.0
    total_lines_of_code: Optional[int] = 0
    remediation_mttr_days: Optional[float] = 0.0

class ExecutiveKPIsResponse(BaseModel):
    total_financial_liability_usd: float
    average_technical_debt_ratio: float
    remediation_mttr_days: float
    sla_compliance_rate: float
    total_vulnerabilities: int
    critical_vulnerabilities: int
    high_vulnerabilities: int
    total_lines_of_code: int
    portfolio_status: str
    pillar_breakdown: Dict[str, float]
    top_hotspots: List[Dict[str, Any]]

class RemediationVelocityResponse(BaseModel):
    total_open_risks: int
    total_resolved_risks: int
    total_accepted_risks: int
    overall_mttr_days: float
    mttr_by_severity: Dict[str, float]
    monthly_trend: List[Dict[str, Any]]

class PortfolioProjectItem(BaseModel):
    project_id: str
    project_name: str
    health_score: float
    technical_debt_ratio: float
    financial_liability_usd: float
    lines_of_code: int
    risk_level: str
    critical_risks_count: int
    last_assessed_at: Optional[str] = None

class PortfolioMatrixResponse(BaseModel):
    total_projects: int
    total_portfolio_liability_usd: float
    average_tdr: float
    projects: List[PortfolioProjectItem]
