import os
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Float, ForeignKey, Text, JSON,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), unique=True, index=True, nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    plan = Column(String(50), default="free")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="organization", cascade="all, delete-orphan")
    settings = relationship("IntegrationSetting", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    invitations = relationship("OrganizationInvitation", back_populates="organization", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="organization", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="organization", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="organization", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="organization", cascade="all, delete-orphan")
    repositories = relationship("RepositoryConnection", back_populates="organization", cascade="all, delete-orphan")

class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(50), default="Developer")
    token = Column(String(255), unique=True, index=True, nullable=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    is_accepted = Column(Boolean, default=False)
    accepted_at = Column(DateTime, nullable=True)
    invited_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="invitations")
    invited_by = relationship("User", foreign_keys=[invited_by_id])

    __table_args__ = (
        Index("idx_invitation_org_email", "org_id", "email"),
    )

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    jti = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="Developer")  # SuperAdmin, Owner, Administrator, Engineering Manager, Developer, Viewer
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=True)  # Email verification
    verification_token = Column(String(255), nullable=True, index=True)
    verification_token_expires_at = Column(DateTime, nullable=True)
    reset_password_token = Column(String(255), nullable=True, index=True)
    reset_password_token_expires_at = Column(DateTime, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255), nullable=True)
    password_changed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
    assigned_risks = relationship("RiskFinding", back_populates="assignee", foreign_keys="RiskFinding.assigned_to")
    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    repository_url = Column(String(500), default="")
    languages = Column(JSON, default=list)  # e.g. ["TypeScript", "Python"]
    frameworks = Column(JSON, default=list)  # e.g. ["React", "FastAPI"]
    owner_name = Column(String(255), default="Engineering Team")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_assessment_date = Column(DateTime, nullable=True)
    is_archived = Column(Boolean, default=False, index=True)
    archived_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", back_populates="projects")
    project_technologies = relationship("ProjectTechnology", back_populates="project", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="project", cascade="all, delete-orphan")
    risks = relationship("RiskFinding", back_populates="project", cascade="all, delete-orphan")
    scheduled_reviews = relationship("ScheduledReview", back_populates="project", cascade="all, delete-orphan")
    repository_connection = relationship("RepositoryConnection", back_populates="project", uselist=False, cascade="all, delete-orphan")
    code_findings = relationship("CodeFinding", back_populates="project", cascade="all, delete-orphan")
    team_permissions = relationship("ProjectTeamPermission", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_project_name"),
        Index("idx_project_org_created", "org_id", "created_at"),
    )

class Technology(Base):
    __tablename__ = "technologies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), unique=True, index=True, nullable=False)
    ecosystem = Column(String(100), default="npm", index=True)  # npm, pypi, maven, gradle, cargo, go, packagist
    category = Column(String(100), default="Library")  # Framework, Library, Language, Database, Tool
    latest_stable_version = Column(String(100), default="unknown")
    description = Column(Text, default="")
    website_url = Column(String(500), default="")
    repo_url = Column(String(500), default="")
    license = Column(String(150), default="UNKNOWN")
    is_deprecated = Column(Boolean, default=False)
    is_eol = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project_links = relationship("ProjectTechnology", back_populates="technology")
    scores = relationship("TechnologyScore", back_populates="technology")
    risks = relationship("RiskFinding", back_populates="technology")
    evidence_sources = relationship("EvidenceSource", back_populates="technology")

class ProjectTechnology(Base):
    __tablename__ = "project_technologies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    technology_id = Column(String(36), ForeignKey("technologies.id", ondelete="CASCADE"), nullable=False, index=True)
    installed_version = Column(String(100), default="latest")
    latest_version = Column(String(100), default="unknown")
    is_direct_dep = Column(Boolean, default=True)
    is_outdated = Column(Boolean, default=False)
    license = Column(String(150), default="UNKNOWN")
    vulnerability_status = Column(String(50), default="UNKNOWN")
    file_source = Column(String(255), default="manual")  # package.json, requirements.txt, manual, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="project_technologies")
    technology = relationship("Technology", back_populates="project_links")

    __table_args__ = (
        UniqueConstraint("project_id", "technology_id", name="uq_project_technology"),
    )

class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    fencing_generation = Column(Integer, default=1, nullable=False)
    trigger_type = Column(String(50), default="manual")  # manual, scheduled, webhook
    status = Column(String(50), default="completed", index=True)  # queued, processing, completed, failed
    overall_health_score = Column(Float, nullable=True)  # None if not assessed/failed
    risk_classification = Column(String(50), default="Healthy")  # Healthy, Good, Needs Attention, High Risk, Critical
    confidence_level = Column(String(50), default="High")  # High, Medium, Low, Unknown
    summary = Column(Text, default="")
    raw_output = Column(JSON, default=dict)
    commit_sha = Column(String(100), default="", index=True)
    analyzer_version = Column(String(50), default="3.1.0")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # v2.0.0 / v3.1.0 Commercial Debt & Code Metrics
    scoring_version = Column(String(20), default="v3.1.0")
    technical_debt_ratio = Column(Float, default=0.0)  # TDR percentage (0-100)
    estimated_remediation_hours = Column(Float, default=0.0)
    lines_of_code = Column(Integer, default=0)
    files_analyzed = Column(Integer, default=0)
    code_maintainability_score = Column(Float, nullable=True)
    architecture_score = Column(Float, nullable=True)
    dependency_score = Column(Float, nullable=True)
    security_score = Column(Float, nullable=True)
    test_quality_score = Column(Float, nullable=True)
    documentation_score = Column(Float, nullable=True)
    reliability_score = Column(Float, nullable=True)
    performance_score = Column(Float, nullable=True)
    complexity_score = Column(Float, nullable=True)
    upgrade_risk_score = Column(Float, nullable=True)

    project = relationship("Project", back_populates="assessments")
    scores = relationship("TechnologyScore", back_populates="assessment", cascade="all, delete-orphan")
    risks = relationship("RiskFinding", back_populates="assessment", cascade="all, delete-orphan")
    evidence_sources = relationship("EvidenceSource", back_populates="assessment", cascade="all, delete-orphan")
    code_findings = relationship("CodeFinding", back_populates="assessment", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_assessment_project_created", "project_id", "created_at"),
    )

class TechnologyScore(Base):
    __tablename__ = "technology_scores"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    technology_id = Column(String(36), ForeignKey("technologies.id", ondelete="CASCADE"), nullable=False, index=True)
    overall_score = Column(Float, nullable=False)  # 0 to 100
    risk_classification = Column(String(50), default="Good")

    # 8 Weighted Categories
    maintenance_health = Column(Float, default=100.0)      # 20%
    security_exposure = Column(Float, default=100.0)       # 20%
    version_currency = Column(Float, default=100.0)        # 15%
    community_activity = Column(Float, default=100.0)      # 10%
    documentation_quality = Column(Float, default=100.0)   # 10%
    ecosystem_compatibility = Column(Float, default=100.0) # 10%
    sustainability = Column(Float, default=100.0)          # 10%
    upgrade_complexity = Column(Float, default=100.0)      # 5%

    confidence_level = Column(String(50), default="High")
    recommended_action = Column(Text, default="")
    upgrade_complexity_level = Column(String(50), default="Low")  # Low, Moderate, High, Breaking
    notes = Column(Text, default="")

    assessment = relationship("Assessment", back_populates="scores")
    technology = relationship("Technology", back_populates="scores")

    __table_args__ = (
        Index("idx_tech_score_assessment_tech", "assessment_id", "technology_id"),
    )

class RiskFinding(Base):
    __tablename__ = "risk_findings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    technology_id = Column(String(36), ForeignKey("technologies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    severity = Column(String(50), default="Medium", index=True)  # Critical, High, Medium, Low
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    business_impact = Column(Text, default="")
    technical_impact = Column(Text, default="")
    status = Column(String(50), default="Open", index=True)  # Open, Investigating, Planned, In Progress, Resolved, Accepted Risk
    assigned_to = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    estimated_remediation_hours = Column(Float, default=2.0)
    fingerprint = Column(String(128), nullable=True, index=True)
    resolution_notes = Column(Text, default="")
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    assessment = relationship("Assessment", back_populates="risks")
    technology = relationship("Technology", back_populates="risks")
    project = relationship("Project", back_populates="risks")
    assignee = relationship("User", back_populates="assigned_risks", foreign_keys=[assigned_to])

    __table_args__ = (
        Index("idx_risk_proj_status_sev", "project_id", "status", "severity"),
    )

class EvidenceSource(Base):
    __tablename__ = "evidence_sources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    technology_id = Column(String(36), ForeignKey("technologies.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(1000), nullable=False)
    title = Column(String(500), default="")
    source_type = Column(String(100), default="documentation")  # release_notes, github_repo, security_advisory, documentation, registry, osv
    reliability_score = Column(Float, default=1.0)  # 0.0 to 1.0
    publication_date = Column(String(100), nullable=True)
    is_official = Column(Boolean, default=True)
    snippet = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="evidence_sources")
    technology = relationship("Technology", back_populates="evidence_sources")

class HistoricalAssessment(Base):
    __tablename__ = "historical_assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    technology_id = Column(String(36), ForeignKey("technologies.id", ondelete="CASCADE"), nullable=True, index=True)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    fencing_generation = Column(Integer, default=1, nullable=False)
    health_score = Column(Float, nullable=False)
    score_delta = Column(Float, default=0.0)
    risk_classification = Column(String(50), default="Good")
    snapshot_data = Column(JSON, default=dict)
    summary_of_changes = Column(Text, default="")
    new_risks_count = Column(Integer, default=0)
    resolved_risks_count = Column(Integer, default=0)
    storage_provider = Column(String(50), default="postgresql")
    sync_status = Column(String(50), default="postgresql_authoritative")
    sync_error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_history_project_created", "project_id", "created_at"),
    )

class ScheduledReview(Base):
    __tablename__ = "scheduled_reviews"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    frequency = Column(String(50), default="Weekly")  # Manual, Daily, Weekly, Monthly, Custom
    cron_expression = Column(String(100), default="0 0 * * 1")
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="scheduled_reviews")
    jobs = relationship("ReviewJob", back_populates="review", cascade="all, delete-orphan")

class ReviewJob(Base):
    __tablename__ = "review_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scheduled_review_id = Column(String(36), ForeignKey("scheduled_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    fencing_generation = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="Pending", index=True)  # Pending, Running, Completed, Failed
    error_message = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    review = relationship("ScheduledReview", back_populates="jobs")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=True)
    org_id = Column(String(36), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)  # e.g., auth.login, project.create, risk.resolve
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class IntegrationSetting(Base):
    __tablename__ = "integration_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    # Stored encrypted at rest using Fernet
    firecrawl_api_key = Column(String(500), default="")
    openai_api_key = Column(String(500), default="")
    gemini_api_key = Column(String(500), default="")
    preferences = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="settings")

class DistributedLock(Base):
    __tablename__ = "distributed_locks"

    lock_key = Column(String(255), primary_key=True)
    owner_id = Column(String(255), nullable=False)
    generation = Column(Integer, default=1, nullable=False)
    acquired_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

# ==============================================================================
# v2.0.0 Commercial SaaS Platform Models
# ==============================================================================

class Team(Base):
    __tablename__ = "teams"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    project_permissions = relationship("ProjectTeamPermission", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_team_name"),
    )

class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="Member")  # Lead, Member, Contributor
    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )

class ProjectTeamPermission(Base):
    __tablename__ = "project_team_permissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    permission = Column(String(50), default="write")  # admin, write, read
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="team_permissions")
    team = relationship("Team", back_populates="project_permissions")

    __table_args__ = (
        UniqueConstraint("project_id", "team_id", name="uq_project_team"),
    )

class RepositoryConnection(Base):
    __tablename__ = "repository_connections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), default="github")  # github, gitlab, bitbucket, zip_upload, manual
    repo_name = Column(String(255), nullable=False)
    repo_full_name = Column(String(255), default="")
    repo_url = Column(String(500), nullable=False)
    default_branch = Column(String(100), default="main")
    selected_branch = Column(String(100), default="main")
    is_private = Column(Boolean, default=False)
    auth_type = Column(String(50), default="token")  # token, github_app, oauth, none
    encrypted_access_token = Column(String(1000), default="")
    webhook_secret = Column(String(255), default="")
    status = Column(String(50), default="connected", index=True)  # connected, syncing, synced, error, disconnected
    last_sync_status = Column(String(50), default="ready")
    last_synced_at = Column(DateTime, nullable=True)
    commit_sha = Column(String(100), default="")
    commit_message = Column(Text, default="")
    commit_author = Column(String(255), default="")
    file_count = Column(Integer, default=0)
    size_bytes = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="repositories")
    project = relationship("Project", back_populates="repository_connection")

    def __init__(self, **kwargs):
        if "branch" in kwargs:
            kwargs["selected_branch"] = kwargs.pop("branch")
        if "local_path" in kwargs:
            path = kwargs.pop("local_path")
            meta = dict(kwargs.get("metadata_json") or {})
            meta["local_path"] = path
            kwargs["metadata_json"] = meta
        if "repo_name" not in kwargs:
            kwargs["repo_name"] = os.path.basename(kwargs.get("repo_url", "repository"))
        if "org_id" not in kwargs and "project_id" in kwargs:
            # Look up project org_id if not explicitly provided
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                p = db.query(Project).filter(Project.id == kwargs["project_id"]).first()
                if p:
                    kwargs["org_id"] = p.org_id
            finally:
                db.close()
        super().__init__(**kwargs)

    @property
    def branch(self) -> str:
        return self.selected_branch or self.default_branch or "main"

    @branch.setter
    def branch(self, val: str):
        self.selected_branch = val

    @property
    def local_path(self) -> Optional[str]:
        return (self.metadata_json or {}).get("local_path")

    @local_path.setter
    def local_path(self, val: Optional[str]):
        meta = dict(self.metadata_json or {})
        meta["local_path"] = val
        self.metadata_json = meta

class CodeFinding(Base):
    __tablename__ = "code_findings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False, index=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    rule_id = Column(String(100), nullable=False, index=True)
    category = Column(String(50), default="maintainability", index=True)  # maintainability, architecture, security, reliability, complexity
    severity = Column(String(50), default="Medium", index=True)  # Critical, High, Medium, Low, Info
    confidence = Column(String(50), default="High")  # High, Medium, Low
    title = Column(String(255), nullable=False)
    explanation = Column(Text, default="")
    technical_evidence = Column(Text, default="")
    why_it_matters = Column(Text, default="")
    recommended_remediation = Column(Text, default="")
    estimated_remediation_hours = Column(Float, default=1.0)
    is_auto_verifiable = Column(Boolean, default=False)
    status = Column(String(50), default="Open", index=True)  # Open, In Progress, Resolved, Accepted Risk, False Positive
    assigned_to = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_at = Column(DateTime, nullable=True)
    analyzer_name = Column(String(100), default="SourceCodeAnalyzer")
    analyzer_version = Column(String(50), default="3.1.0")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    assessment = relationship("Assessment", back_populates="code_findings")
    project = relationship("Project", back_populates="code_findings")

    __table_args__ = (
        Index("idx_code_finding_ass_sev", "assessment_id", "severity"),
    )

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(String(50), primary_key=True)  # free, starter, professional, enterprise
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    price_monthly_cents = Column(Integer, default=0)
    price_yearly_cents = Column(Integer, default=0)
    max_projects = Column(Integer, default=3)
    max_monthly_assessments = Column(Integer, default=10)
    max_repo_size_mb = Column(Integer, default=25)
    max_team_members = Column(Integer, default=5)
    ai_recommendations_enabled = Column(Boolean, default=False)
    advanced_code_analysis_enabled = Column(Boolean, default=False)
    retention_days = Column(Integer, default=30)
    features = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def slug(self) -> str:
        return self.id

    @property
    def price_monthly(self) -> float:
        return (self.price_monthly_cents or 0) / 100.0

    @property
    def price_annual(self) -> float:
        return (self.price_yearly_cents or 0) / 100.0

    @property
    def max_assessments_per_month(self) -> int:
        return self.max_monthly_assessments

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan_id = Column(String(50), ForeignKey("subscription_plans.id"), default="free", nullable=False, index=True)
    status = Column(String(50), default="active", index=True)  # active, trialing, past_due, canceled
    billing_cycle = Column(String(20), default="monthly")  # monthly, yearly
    payment_provider = Column(String(50), default="razorpay")  # razorpay, stripe, none
    provider_customer_id = Column(String(255), default="", index=True)
    provider_subscription_id = Column(String(255), default="", index=True)
    provider_order_id = Column(String(255), default="", index=True)
    provider_payment_id = Column(String(255), default="", index=True)
    stripe_customer_id = Column(String(255), default="", index=True)
    stripe_subscription_id = Column(String(255), default="", index=True)
    current_period_start = Column(DateTime, default=datetime.utcnow)
    current_period_end = Column(DateTime, default=datetime.utcnow)
    cancel_at_period_end = Column(Boolean, default=False)
    trial_ends_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="subscription")
    plan = relationship("SubscriptionPlan")

class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False, index=True)  # assessments_count, repo_ingestion_mb, ai_tokens
    period = Column(String(7), nullable=False, index=True)  # e.g. "2026-11"
    count = Column(Float, default=0.0)
    limit = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="usage_records")

    __table_args__ = (
        UniqueConstraint("org_id", "metric_type", "period", name="uq_org_metric_period"),
    )

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number = Column(String(100), unique=True, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(10), default="usd")
    status = Column(String(50), default="paid", index=True)  # paid, open, void
    hosted_invoice_url = Column(String(500), default="")
    pdf_url = Column(String(500), default="")
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    @property
    def amount_due(self) -> float:
        return (self.amount_cents or 0) / 100.0

    @property
    def amount_paid(self) -> float:
        return (self.amount_cents or 0) / 100.0 if self.status == "paid" else 0.0

    @property
    def invoice_pdf(self) -> str:
        return self.pdf_url or self.hosted_invoice_url

    @property
    def stripe_invoice_id(self) -> str:
        return getattr(self, "_stripe_invoice_id", "")

    @property
    def period_start(self) -> Optional[datetime]:
        return self.created_at

    @property
    def period_end(self) -> Optional[datetime]:
        return self.created_at

    organization = relationship("Organization", back_populates="invoices")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, default="")
    category = Column(String(50), default="assessment", index=True)  # assessment, security, billing, team, system
    severity = Column(String(50), default="info")  # info, warning, error, success
    link = Column(String(500), default="")
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    organization = relationship("Organization", back_populates="notifications")
    user = relationship("User", back_populates="notifications")

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    email_assessment_completed = Column(Boolean, default=True)
    email_critical_risk = Column(Boolean, default=True)
    email_billing_alerts = Column(Boolean, default=True)
    email_weekly_digest = Column(Boolean, default=True)
    inapp_notifications = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="notification_preferences")

class AIUsageLedger(Base):
    __tablename__ = "ai_usage_ledgers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    operation_type = Column(String(100), default="chat")  # chat, recommendation, assessment, review
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    organization = relationship("Organization")
    user = relationship("User")


# ==============================================================================
# v3.1.0 Engineering Intelligence, Ingestion Snapshots, Billing & Security Models
# ==============================================================================

class RepositoryIngestionRun(Base):
    __tablename__ = "repository_ingestion_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    repo_connection_id = Column(String(36), ForeignKey("repository_connections.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), default="github", nullable=False)  # github, gitlab, bitbucket, zip_upload
    branch = Column(String(100), default="main", nullable=False)
    commit_sha = Column(String(100), default="", index=True)
    commit_message = Column(Text, default="")
    commit_author = Column(String(255), default="")
    status = Column(String(50), default="QUEUED", nullable=False, index=True)  # QUEUED, CLONING_OR_DOWNLOADING, ANALYSING, PERSISTING, COMPLETED, FAILED, CANCELLED
    progress_pct = Column(Integer, default=0)
    analyzer_version = Column(String(50), default="3.1.0")
    files_examined = Column(Integer, default=0)
    files_analyzed = Column(Integer, default=0)
    files_excluded = Column(Integer, default=0)
    unsupported_files = Column(Integer, default=0)
    parser_failures = Column(Integer, default=0)
    lines_of_code = Column(Integer, default=0)
    languages_json = Column(JSON, default=list)
    frameworks_json = Column(JSON, default=list)
    dependencies_count = Column(Integer, default=0)
    findings_count = Column(Integer, default=0)
    error_message = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class RepositoryAnalysisSnapshot(Base):
    __tablename__ = "repository_analysis_snapshots"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    repo_connection_id = Column(String(36), ForeignKey("repository_connections.id", ondelete="SET NULL"), nullable=True, index=True)
    ingestion_run_id = Column(String(36), ForeignKey("repository_ingestion_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), default="github", nullable=False)
    branch = Column(String(100), default="main", nullable=False)
    commit_sha = Column(String(100), default="", nullable=False, index=True)
    commit_message = Column(Text, default="")
    commit_author = Column(String(255), default="")
    analyzer_version = Column(String(50), default="3.1.0", nullable=False)
    files_examined = Column(Integer, default=0)
    files_analyzed = Column(Integer, default=0)
    files_excluded = Column(Integer, default=0)
    unsupported_files = Column(Integer, default=0)
    parser_failures = Column(Integer, default=0)
    lines_of_code = Column(Integer, default=0)
    languages_json = Column(JSON, default=list)
    frameworks_json = Column(JSON, default=list)
    code_metrics_json = Column(JSON, default=dict)
    findings_json = Column(JSON, default=list)
    dependencies_json = Column(JSON, default=list)
    architecture_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_repo_snapshot_proj_commit_ver", "project_id", "commit_sha", "analyzer_version"),
    )

    @property
    def test_files_count(self) -> int:
        return int((self.code_metrics_json or {}).get("test_files_count", 0))

    @property
    def maintainability_index(self) -> Optional[float]:
        return (self.code_metrics_json or {}).get("maintainability_index")

    @property
    def avg_cyclomatic_complexity(self) -> Optional[float]:
        return (self.code_metrics_json or {}).get("avg_cyclomatic_complexity")

    @property
    def max_cyclomatic_complexity(self) -> Optional[int]:
        return (self.code_metrics_json or {}).get("max_cyclomatic_complexity")

    @property
    def code_duplication_percentage(self) -> Optional[float]:
        return (self.code_metrics_json or {}).get("code_duplication_percentage")

    @property
    def defect_density(self) -> Optional[float]:
        return (self.code_metrics_json or {}).get("defect_density")

    @property
    def quality_grade(self) -> Optional[str]:
        return (self.code_metrics_json or {}).get("quality_grade")

    @property
    def file_metrics_json(self) -> dict:
        return dict(self.code_metrics_json or {})

    @property
    def code_findings_json(self) -> list:
        return list(self.findings_json or [])


class VulnerabilityCacheEntry(Base):
    __tablename__ = "vulnerability_cache_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    cache_key = Column(String(500), unique=True, nullable=False, index=True)
    ecosystem = Column(String(100), nullable=False, index=True)
    package_name = Column(String(255), nullable=False, index=True)
    version = Column(String(100), nullable=False)
    provider = Column(String(50), default="osv")
    status = Column(String(50), default="UNKNOWN", nullable=False)  # CLEAN, VULNERABLE, UNKNOWN, CHECK_FAILED
    vulnerabilities_json = Column(JSON, default=list)
    license_raw = Column(String(255), default="")
    license_spdx = Column(String(150), default="UNKNOWN")
    latest_version = Column(String(100), default="unknown")
    is_deprecated = Column(Boolean, default=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), default="razorpay", nullable=False)
    provider_order_id = Column(String(255), unique=True, nullable=False, index=True)
    plan_id = Column(String(50), ForeignKey("subscription_plans.id"), nullable=False, index=True)
    billing_cycle = Column(String(20), default="monthly", nullable=False)
    amount_subunits = Column(Integer, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(50), default="created", nullable=False, index=True)  # created, paid, failed, expired
    provider_payment_id = Column(String(255), unique=True, nullable=True, index=True)
    receipt = Column(String(100), default="")
    error_message = Column(Text, default="")
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider = Column(String(50), nullable=False, index=True)  # razorpay, stripe
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    org_id = Column(String(36), nullable=True, index=True)
    payload_hash = Column(String(64), default="")
    status = Column(String(50), default="processed", nullable=False)
    action_taken = Column(String(100), default="none")
    error_message = Column(Text, default="")
    processed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class WebhookDeliveryEvent(Base):
    __tablename__ = "webhook_delivery_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider = Column(String(50), nullable=False, index=True)  # github, gitlab, bitbucket
    delivery_id = Column(String(255), unique=True, nullable=False, index=True)
    org_id = Column(String(36), nullable=True, index=True)
    project_id = Column(String(36), nullable=True, index=True)
    repo_connection_id = Column(String(36), ForeignKey("repository_connections.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(100), default="push")  # push, pull_request, merge_request
    branch = Column(String(100), default="main")
    commit_sha = Column(String(100), default="")
    pr_number = Column(Integer, nullable=True)
    status = Column(String(50), default="queued", index=True)  # queued, processing, completed, failed
    ingestion_run_id = Column(String(36), nullable=True)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    bucket_key = Column(String(255), primary_key=True)
    window_start = Column(Integer, nullable=False)
    request_count = Column(Integer, default=1, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class RemediationWorkPackage(Base):
    __tablename__ = "remediation_work_packages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    priority = Column(String(50), default="Medium", index=True)  # Critical, High, Medium, Low
    priority_score = Column(Float, default=50.0)
    priority_rationale = Column(Text, default="")
    finding_refs_json = Column(JSON, default=list)
    proposed_fix = Column(Text, default="")
    dependencies_json = Column(JSON, default=list)
    estimated_hours = Column(Float, default=2.0)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_date = Column(DateTime, nullable=True)
    status = Column(String(50), default="Planned", index=True)  # Planned, In Progress, Blocked, Completed
    verification_criteria = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


