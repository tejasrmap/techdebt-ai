from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import Assessment, Project, User
from app.services.auth_service import get_current_user
from app.services.report_generator import ReportGenerator

router = APIRouter(prefix="/reports", tags=["Reports"])

def _build_assessment_export_data(assessment: Assessment) -> dict:
    scores = []
    for s in assessment.scores:
        installed = "latest"
        for pt in assessment.project.project_technologies:
            if pt.technology_id == s.technology_id:
                installed = pt.installed_version
                break
        scores.append({
            "technology_name": s.technology.name if s.technology else "",
            "installed_version": installed,
            "latest_stable_version": s.technology.latest_stable_version if s.technology else "unknown",
            "overall_score": s.overall_score,
            "risk_classification": s.risk_classification,
            "maintenance_health": s.maintenance_health,
            "security_exposure": s.security_exposure,
            "version_currency": s.version_currency,
            "community_activity": s.community_activity,
            "documentation_quality": s.documentation_quality,
            "ecosystem_compatibility": s.ecosystem_compatibility,
            "sustainability": s.sustainability,
            "upgrade_complexity": s.upgrade_complexity,
            "confidence_level": s.confidence_level,
            "upgrade_complexity_level": s.upgrade_complexity_level,
            "recommended_action": s.recommended_action
        })

    risks = []
    for r in assessment.risks:
        risks.append({
            "severity": r.severity,
            "technology_name": r.technology.name if r.technology else "",
            "title": r.title,
            "status": r.status,
            "business_impact": r.business_impact,
            "technical_impact": r.technical_impact
        })

    return {
        "overall_health_score": assessment.overall_health_score or 0.0,
        "risk_classification": assessment.risk_classification,
        "confidence_level": assessment.confidence_level,
        "scores": scores,
        "risks": risks
    }

@router.get("/pdf/{assessment_id}")
def download_pdf_report(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Enforce strict organization ownership check (supports assessment_id or project_id)
    a = (
        db.query(Assessment)
        .join(Project)
        .filter(
            ((Assessment.id == assessment_id) | (Assessment.project_id == assessment_id)),
            Project.org_id == current_user.org_id
        )
        .order_by(Assessment.created_at.desc())
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Assessment report not found or unauthorized")

    data = _build_assessment_export_data(a)
    pdf_bytes = ReportGenerator.generate_pdf(a.project.name, data)

    clean_proj_name = "".join(c for c in a.project.name if c.isalnum() or c in ("-", "_")).lower()
    filename = f"techdebt-report-{clean_proj_name}-{a.created_at.strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/csv/{assessment_id}")
def download_csv_report(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Enforce strict organization ownership check (supports assessment_id or project_id)
    a = (
        db.query(Assessment)
        .join(Project)
        .filter(
            ((Assessment.id == assessment_id) | (Assessment.project_id == assessment_id)),
            Project.org_id == current_user.org_id
        )
        .order_by(Assessment.created_at.desc())
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Assessment report not found or unauthorized")

    data = _build_assessment_export_data(a)
    csv_str = ReportGenerator.generate_csv(a.project.name, data)

    clean_proj_name = "".join(c for c in a.project.name if c.isalnum() or c in ("-", "_")).lower()
    filename = f"techdebt-report-{clean_proj_name}-{a.created_at.strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("")
def list_available_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    assessments = (
        db.query(Assessment)
        .join(Project)
        .filter(Project.org_id == current_user.org_id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .limit(25)
        .all()
    )
    return [
        {
            "assessment_id": a.id,
            "project_id": a.project_id,
            "project_name": a.project.name,
            "health_score": a.overall_health_score,
            "risk_classification": a.risk_classification,
            "created_at": a.created_at,
            "pdf_url": f"/api/v1/reports/pdf/{a.id}",
            "csv_url": f"/api/v1/reports/csv/{a.id}"
        }
        for a in assessments
    ]
