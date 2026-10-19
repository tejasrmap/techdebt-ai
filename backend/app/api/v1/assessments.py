from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.all_models import Assessment, Project, User, TechnologyScore, EvidenceSource, AuditLog
from app.schemas.schemas import AssessmentRunRequest, AssessmentResponse, TechnologyScoreResponse, EvidenceSourceResponse
from app.services.auth_service import get_current_user
from app.services.scheduler_service import execute_project_review
from app.services.memento_adapter import MementoMemoryAdapter

router = APIRouter(prefix="/assessments", tags=["Assessments"])

@router.post("/run", response_model=AssessmentResponse)
async def run_assessment(req: AssessmentRunRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Enforce organization ownership check
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

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
