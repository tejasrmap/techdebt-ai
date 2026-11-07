import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import Assessment, Project, User, RiskFinding, Organization
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
            "recommended_action": s.recommended_action or ""
        })

    risks = []
    for r in assessment.risks:
        risks.append({
            "severity": r.severity,
            "technology_name": r.technology.name if r.technology else "",
            "title": r.title,
            "status": r.status,
            "business_impact": r.business_impact or "",
            "technical_impact": r.technical_impact or ""
        })

    code_findings = (assessment.raw_output or {}).get("code_findings", [])
    if not code_findings and hasattr(assessment, "code_findings") and assessment.code_findings:
        code_findings = [
            {
                "id": cf.id,
                "file_path": cf.file_path,
                "line_start": cf.line_start,
                "rule_id": cf.rule_id,
                "category": cf.category,
                "severity": cf.severity,
                "title": cf.title,
                "estimated_remediation_hours": cf.estimated_remediation_hours
            }
            for cf in assessment.code_findings
        ]

    hours = assessment.estimated_remediation_hours or 0.0
    return {
        "overall_health_score": assessment.overall_health_score if assessment.overall_health_score is not None else 100.0,
        "risk_classification": assessment.risk_classification or "Healthy",
        "confidence_level": assessment.confidence_level or "High",
        "commit_sha": assessment.commit_sha or "N/A",
        "analyzer_version": assessment.analyzer_version or "v3.1.0",
        "scoring_version": assessment.scoring_version or "v3.1.0",
        "technical_debt_ratio": assessment.technical_debt_ratio or 0.0,
        "estimated_remediation_hours": hours,
        "financial_liability_usd": round(hours * 120.0, 2),
        "lines_of_code": assessment.lines_of_code or 0,
        "files_analyzed": assessment.files_analyzed or 0,
        "pillar_scores": {
            "code_quality": assessment.code_maintainability_score or 85.0,
            "architecture": assessment.architecture_score or 80.0,
            "security": assessment.security_score or 90.0,
            "dependencies": assessment.dependency_score or 78.0,
            "maintainability": assessment.reliability_score or 82.0
        },
        "scores": scores,
        "risks": risks,
        "code_findings": code_findings
    }

def _build_portfolio_export_data(org_id: str, db: Session) -> dict:
    projects = db.query(Project).filter(Project.org_id == org_id, Project.is_archived == False).all()
    project_items = []
    total_liability = 0.0
    scores_sum = 0.0
    crit_count = 0

    for p in projects:
        latest_a = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        p_crit = db.query(RiskFinding).filter(
            RiskFinding.project_id == p.id,
            RiskFinding.severity == "Critical",
            RiskFinding.status.notin_(["Resolved", "Accepted Risk"])
        ).count()
        crit_count += p_crit

        h_score = latest_a.overall_health_score if latest_a and latest_a.overall_health_score is not None else 100.0
        tdr = latest_a.technical_debt_ratio if latest_a and latest_a.technical_debt_ratio is not None else 0.0
        loc = latest_a.lines_of_code if latest_a and latest_a.lines_of_code else 0
        hours = latest_a.estimated_remediation_hours if latest_a and latest_a.estimated_remediation_hours else 0.0
        liability = round(hours * 120.0, 2)
        if liability == 0.0 and p_crit > 0:
            liability = p_crit * 1500.0

        scores_sum += h_score
        total_liability += liability

        project_items.append({
            "project_id": p.id,
            "project_name": p.name,
            "health_score": h_score,
            "technical_debt_ratio": tdr,
            "financial_liability_usd": liability,
            "lines_of_code": loc,
            "critical_risks_count": p_crit,
            "risk_level": "Critical" if h_score < 60 or p_crit > 2 else ("High Risk" if h_score < 75 else ("Needs Attention" if h_score < 85 else "Healthy"))
        })

    avg_health = round(scores_sum / len(projects), 1) if projects else 100.0
    return {
        "total_projects": len(projects),
        "average_health_score": avg_health,
        "total_liability_usd": round(total_liability, 2),
        "total_critical_risks": crit_count,
        "projects": project_items
    }

@router.get("/pdf/{assessment_id}")
def download_pdf_report(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
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

@router.get("/json/{assessment_id}")
def download_json_report(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve full machine-readable JSON technical debt audit report."""
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
    json_report = ReportGenerator.generate_json(a.project.name, data)
    return json_report

@router.get("/portfolio/pdf")
def download_portfolio_pdf_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate executive-level portfolio PDF report covering all organization projects."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    org_name = org.name if org else "Enterprise Organization"
    data = _build_portfolio_export_data(current_user.org_id, db)
    pdf_bytes = ReportGenerator.generate_portfolio_pdf(org_name, data)

    filename = f"techdebt-portfolio-report-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/portfolio/csv")
def download_portfolio_csv_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate organization-wide portfolio CSV report."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    org_name = org.name if org else "Enterprise Organization"
    data = _build_portfolio_export_data(current_user.org_id, db)
    csv_str = ReportGenerator.generate_portfolio_csv(org_name, data)

    filename = f"techdebt-portfolio-report-{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/portfolio/json")
def download_portfolio_json_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate organization-wide portfolio JSON report."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    org_name = org.name if org else "Enterprise Organization"
    data = _build_portfolio_export_data(current_user.org_id, db)
    return {
        "metadata": {
            "vendor": ReportGenerator.VENDOR_NAME,
            "platform": ReportGenerator.PLATFORM_NAME,
            "organization_name": org_name,
            "generated_at": datetime.utcnow().isoformat() + "Z"
        },
        "portfolio": data
    }

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
            "csv_url": f"/api/v1/reports/csv/{a.id}",
            "json_url": f"/api/v1/reports/json/{a.id}"
        }
        for a in assessments
    ]
