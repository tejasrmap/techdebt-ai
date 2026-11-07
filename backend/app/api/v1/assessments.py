from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.database import get_db
from app.models.all_models import Assessment, Project, User, TechnologyScore, EvidenceSource, AuditLog
from app.schemas.schemas import AssessmentRunRequest, AssessmentResponse, TechnologyScoreResponse, EvidenceSourceResponse
from app.services.auth_service import get_current_user, require_roles, UserRole
from app.services.scheduler_service import execute_project_review
from app.services.memento_adapter import MementoMemoryAdapter
from app.services.debt_scoring_engine import CommercialDebtScoringEngine

router = APIRouter(prefix="/assessments", tags=["Assessments"])

@router.post("/run", response_model=AssessmentResponse)
async def run_assessment(
    req: AssessmentRunRequest,
    current_user: User = Depends(require_roles([
        UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR, UserRole.ENGINEERING_MANAGER, UserRole.DEVELOPER
    ])),
    db: Session = Depends(get_db)
):
    # 1. Enforce organization ownership check
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    # 2. Enforce monthly assessments quota
    from app.services.billing_service import BillingService
    allowed, limit, current = BillingService.check_entitlement(db, current_user.org_id, "monthly_assessments")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if hasattr(status, "HTTP_402_PAYMENT_REQUIRED") else 402,
            detail=f"Monthly assessment limit reached for your plan ({current}/{limit}). Please upgrade your subscription."
        )

    assessment = await execute_project_review(
        project_id=req.project_id,
        trigger_type=req.trigger_type or "manual",
        db_session=db
    )

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="assessment.run",
        resource_type="assessment",
        resource_id=assessment.id,
        details={"project_id": project.id, "project_name": project.name, "score": assessment.overall_health_score}
    )
    db.add(audit)
    db.commit()

    return get_assessment(assessment.id, current_user, db)

@router.get("", response_model=List[AssessmentResponse])
def list_assessments(project_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = (
        db.query(Assessment)
        .join(Project)
        .filter(Project.org_id == current_user.org_id)
    )
    if project_id:
        # Validate project belongs to organization
        proj = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        query = query.filter(Assessment.project_id == project_id)
    
    assessments = query.order_by(Assessment.created_at.desc()).limit(50).all()
    results = []
    for a in assessments:
        results.append({
            "id": a.id,
            "project_id": a.project_id,
            "project_name": a.project.name if a.project else "",
            "trigger_type": a.trigger_type,
            "status": a.status,
            "overall_health_score": a.overall_health_score,
            "risk_classification": a.risk_classification,
            "confidence_level": a.confidence_level,
            "summary": a.summary or "",
            "created_at": a.created_at,
            "scores": [],
            "risks_count": len(a.risks)
        })
    return results

@router.get("/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(assessment_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = (
        db.query(Assessment)
        .join(Project)
        .filter(Assessment.id == assessment_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")

    scores_out = []
    for s in a.scores:
        evidence_list = [
            EvidenceSourceResponse(
                id=ev.id,
                url=ev.url,
                title=ev.title,
                source_type=ev.source_type,
                reliability_score=ev.reliability_score,
                publication_date=ev.publication_date,
                is_official=ev.is_official,
                snippet=ev.snippet or ""
            )
            for ev in a.evidence_sources if ev.technology_id == s.technology_id
        ]

        # Get installed version from project link
        installed = "latest"
        for pt in a.project.project_technologies:
            if pt.technology_id == s.technology_id:
                installed = pt.installed_version
                break

        scores_out.append(TechnologyScoreResponse(
            technology_id=s.technology_id,
            technology_name=s.technology.name if s.technology else "",
            installed_version=installed,
            latest_stable_version=s.technology.latest_stable_version if s.technology else "unknown",
            overall_score=s.overall_score,
            risk_classification=s.risk_classification,
            maintenance_health=s.maintenance_health,
            security_exposure=s.security_exposure,
            version_currency=s.version_currency,
            community_activity=s.community_activity,
            documentation_quality=s.documentation_quality,
            ecosystem_compatibility=s.ecosystem_compatibility,
            sustainability=s.sustainability,
            upgrade_complexity=s.upgrade_complexity,
            confidence_level=s.confidence_level,
            recommended_action=s.recommended_action or "",
            upgrade_complexity_level=s.upgrade_complexity_level or "Low",
            notes=s.notes or "",
            evidence=evidence_list
        ))

    return AssessmentResponse(
        id=a.id,
        project_id=a.project_id,
        project_name=a.project.name if a.project else "",
        trigger_type=a.trigger_type,
        status=a.status,
        overall_health_score=a.overall_health_score,
        risk_classification=a.risk_classification,
        confidence_level=a.confidence_level,
        summary=a.summary or "",
        created_at=a.created_at,
        scores=scores_out,
        risks_count=len(a.risks)
    )

@router.get("/{assessment_id}/comparison")
async def get_assessment_comparison(assessment_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # CRITICAL SECURITY VULNERABILITY FIX:
    # First verify that assessment exists AND belongs to caller's organization!
    assessment = (
        db.query(Assessment)
        .join(Project)
        .filter(Assessment.id == assessment_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found or unauthorized")

    from app.services.integration_config_service import get_memento_adapter_for_org
    memento = get_memento_adapter_for_org(current_user.org_id, db)
    comparison = await memento.generate_delta_comparison(db, assessment_id, caller_org_id=current_user.org_id)
    return comparison

class ExplainScoreRequest(BaseModel):
    code_metrics: Optional[Dict[str, Any]] = None
    tech_scores: Optional[List[Dict[str, Any]]] = None
    risk_findings: Optional[List[Dict[str, Any]]] = None
    code_findings: Optional[List[Dict[str, Any]]] = None
    hourly_rate: float = CommercialDebtScoringEngine.DEFAULT_HOURLY_RATE

@router.post("/explain-score")
def explain_debt_score(
    req: ExplainScoreRequest,
    current_user: User = Depends(get_current_user)
):
    return CommercialDebtScoringEngine.explain_debt_score(
        code_metrics=req.code_metrics,
        tech_scores=req.tech_scores,
        risk_findings=req.risk_findings,
        code_findings=req.code_findings,
        hourly_rate=req.hourly_rate
    )

@router.get("/{assessment_id}/debt-breakdown")
def get_assessment_debt_breakdown(
    assessment_id: str,
    hourly_rate: float = CommercialDebtScoringEngine.DEFAULT_HOURLY_RATE,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    assessment = (
        db.query(Assessment)
        .join(Project)
        .filter(Assessment.id == assessment_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found or unauthorized")

    # Extract stored metrics from assessment raw_output
    raw = assessment.raw_output or {}
    code_metrics = raw.get("code_metrics", {
        "lines_of_code": assessment.lines_of_code or 0,
        "files_analyzed": assessment.files_analyzed or 0
    })

    # Tech scores list
    tech_scores = [
        {
            "maintenance_health": s.maintenance_health,
            "version_currency": s.version_currency,
            "security_exposure": s.security_exposure,
            "documentation_quality": s.documentation_quality
        }
        for s in assessment.scores
    ]

    # Risk findings
    risk_findings = [
        {
            "severity": r.severity,
            "title": r.title
        }
        for r in assessment.risks
    ]

    code_findings = raw.get("code_findings", [])
    if not code_findings and hasattr(assessment, "code_findings") and assessment.code_findings:
        code_findings = [
            {
                "id": cf.id,
                "file_path": cf.file_path,
                "category": cf.category,
                "severity": cf.severity,
                "title": cf.title,
                "estimated_remediation_hours": cf.estimated_remediation_hours
            }
            for cf in assessment.code_findings
        ]

    breakdown = CommercialDebtScoringEngine.explain_debt_score(
        code_metrics=code_metrics,
        tech_scores=tech_scores,
        risk_findings=risk_findings,
        code_findings=code_findings,
        hourly_rate=hourly_rate
    )
    breakdown["assessment_id"] = assessment.id
    breakdown["project_id"] = assessment.project_id
    breakdown["project_name"] = assessment.project.name if assessment.project else ""
    return breakdown

@router.get("/{assessment_id}/status")
def get_assessment_status(assessment_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieve real-time assessment stage progress and completion percentage."""
    from app.models.all_models import Assessment
    assessment = (
        db.query(Assessment)
        .join(Project)
        .filter(Assessment.id == assessment_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found or unauthorized")
    
    if assessment.status == "completed":
        percent = 100
        stage = "completed"
    elif assessment.status == "failed":
        percent = 100
        stage = "failed"
    elif assessment.status == "processing":
        percent = 65
        stage = "analyzing"
    else:
        percent = 10
        stage = "queued"
    
    return {
        "assessment_id": assessment.id,
        "status": assessment.status,
        "stage": stage,
        "progress_percent": percent,
        "overall_health_score": assessment.overall_health_score,
        "technical_debt_ratio": assessment.technical_debt_ratio,
        "created_at": assessment.created_at
    }

@router.get("/{assessment_id}/findings")
def list_assessment_findings(
    assessment_id: str,
    severity: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve paginated assessment risk and debt findings with severity filter."""
    from app.models.all_models import RiskFinding
    assessment = (
        db.query(Assessment)
        .join(Project)
        .filter(Assessment.id == assessment_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found or unauthorized")
    
    query = db.query(RiskFinding).filter(RiskFinding.assessment_id == assessment_id)
    if severity:
        query = query.filter(RiskFinding.severity == severity)
    
    total = query.count()
    offset = (page - 1) * limit
    findings = query.order_by(RiskFinding.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "business_impact": f.business_impact or "",
                "technical_impact": f.technical_impact or "",
                "resolution_notes": f.resolution_notes or "",
                "created_at": f.created_at
            }
            for f in findings
        ]
    }

@router.get("/compare/two")
def compare_two_assessments(
    base_id: str,
    target_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compare two assessments and calculate score deltas, newly introduced, and resolved risks."""
    from app.models.all_models import Assessment
    base_a = db.query(Assessment).join(Project).filter(Assessment.id == base_id, Project.org_id == current_user.org_id).first()
    target_a = db.query(Assessment).join(Project).filter(Assessment.id == target_id, Project.org_id == current_user.org_id).first()

    if not base_a or not target_a:
        raise HTTPException(status_code=404, detail="One or both assessments not found or unauthorized")
    
    score_delta = round((target_a.overall_health_score or 0.0) - (base_a.overall_health_score or 0.0), 2)
    tdr_delta = round((target_a.technical_debt_ratio or 0.0) - (base_a.technical_debt_ratio or 0.0), 2)

    base_risk_titles = {r.title for r in base_a.risks}
    target_risk_titles = {r.title for r in target_a.risks}

    new_risks = [r.title for r in target_a.risks if r.title not in base_risk_titles]
    resolved_risks = [r.title for r in base_a.risks if r.title not in target_risk_titles]

    status_trend = "improved" if score_delta > 0 else ("degraded" if score_delta < 0 else "unchanged")

    return {
        "base_assessment_id": base_id,
        "target_assessment_id": target_id,
        "base_score": base_a.overall_health_score,
        "target_score": target_a.overall_health_score,
        "score_delta": score_delta,
        "base_tdr": base_a.technical_debt_ratio,
        "target_tdr": target_a.technical_debt_ratio,
        "tdr_delta": tdr_delta,
        "new_risks_count": len(new_risks),
        "new_risks": new_risks,
        "resolved_risks_count": len(resolved_risks),
        "resolved_risks": resolved_risks,
        "trend": status_trend
    }


