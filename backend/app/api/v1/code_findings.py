from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import User, CodeFinding, Assessment, Project
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/code-findings", tags=["Code Findings & Diagnostics"])

@router.get("/assessment/{assessment_id}")
def get_assessment_code_findings(
    assessment_id: str,
    severity: Optional[str] = Query(None, description="Filter by severity: Critical, High, Medium, Low, Info"),
    category: Optional[str] = Query(None, description="Filter by category: security, complexity, maintainability, architecture, reliability"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve fine-grained source code diagnostic findings with exact file line anchors and remediation recipes."""
    assessment = db.query(Assessment).join(Project, Assessment.project_id == Project.id).filter(
        Assessment.id == assessment_id,
        Project.org_id == current_user.org_id
    ).first()

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found or access denied")

    query = db.query(CodeFinding).filter(CodeFinding.assessment_id == assessment_id)
    if severity:
        query = query.filter(CodeFinding.severity == severity)
    if category:
        query = query.filter(CodeFinding.category == category)

    findings = query.order_by(
        CodeFinding.severity.desc(),
        CodeFinding.file_path.asc(),
        CodeFinding.line_start.asc()
    ).all()

    return [
        {
            "id": f.id,
            "assessment_id": f.assessment_id,
            "project_id": f.project_id,
            "file_path": f.file_path,
            "line_start": f.line_start,
            "line_end": f.line_end,
            "rule_id": f.rule_id,
            "category": f.category,
            "severity": f.severity,
            "confidence": f.confidence,
            "title": f.title,
            "explanation": f.explanation,
            "technical_evidence": f.technical_evidence,
            "why_it_matters": f.why_it_matters,
            "recommended_remediation": f.recommended_remediation,
            "estimated_remediation_hours": f.estimated_remediation_hours,
            "is_auto_verifiable": f.is_auto_verifiable,
            "created_at": f.created_at.isoformat()
        }
        for f in findings
    ]

@router.get("/project/{project_id}")
def get_project_latest_findings(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve code findings from the most recent completed assessment for a project."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_assessment = (
        db.query(Assessment)
        .filter(Assessment.project_id == project_id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )

    if not latest_assessment:
        return {"assessment_id": None, "findings": []}

    findings = db.query(CodeFinding).filter(CodeFinding.assessment_id == latest_assessment.id).all()
    return {
        "assessment_id": latest_assessment.id,
        "scoring_version": latest_assessment.scoring_version,
        "technical_debt_ratio": latest_assessment.technical_debt_ratio,
        "estimated_remediation_hours": latest_assessment.estimated_remediation_hours,
        "lines_of_code": latest_assessment.lines_of_code,
        "findings_count": len(findings),
        "findings": [
            {
                "id": f.id,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "rule_id": f.rule_id,
                "category": f.category,
                "severity": f.severity,
                "title": f.title,
                "explanation": f.explanation,
                "technical_evidence": f.technical_evidence,
                "recommended_remediation": f.recommended_remediation,
                "estimated_remediation_hours": f.estimated_remediation_hours
            }
            for f in findings
        ]
    }

@router.get("/{finding_id}")
def get_code_finding_detail(
    finding_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    finding = db.query(CodeFinding).join(Project, CodeFinding.project_id == Project.id).filter(
        CodeFinding.id == finding_id,
        Project.org_id == current_user.org_id
    ).first()

    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    return {
        "id": finding.id,
        "assessment_id": finding.assessment_id,
        "project_id": finding.project_id,
        "file_path": finding.file_path,
        "line_start": finding.line_start,
        "line_end": finding.line_end,
        "rule_id": finding.rule_id,
        "category": finding.category,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "title": finding.title,
        "explanation": finding.explanation,
        "technical_evidence": finding.technical_evidence,
        "why_it_matters": finding.why_it_matters,
        "recommended_remediation": finding.recommended_remediation,
        "estimated_remediation_hours": finding.estimated_remediation_hours,
        "is_auto_verifiable": finding.is_auto_verifiable,
        "created_at": finding.created_at.isoformat()
    }

@router.get("/project/{project_id}/quality-summary")
def get_project_quality_summary(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve comprehensive quality score, maintainability index, defect density, and grade."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_assessment = (
        db.query(Assessment)
        .filter(Assessment.project_id == project_id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )

    findings = db.query(CodeFinding).filter(CodeFinding.project_id == project_id).all()

    sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
    cat_hours: dict = {}
    total_hours = 0.0

    for f in findings:
        sev = f.severity or "Medium"
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        cat = f.category or "maintainability"
        hours = f.estimated_remediation_hours or 1.0
        cat_hours[cat] = round(cat_hours.get(cat, 0.0) + hours, 1)
        total_hours += hours

    loc = latest_assessment.lines_of_code if (latest_assessment and latest_assessment.lines_of_code) else 1000
    defect_density = round((len(findings) / max(1, loc)) * 1000, 2)
    crit_count = sev_counts["Critical"]

    if crit_count > 2:
        grade = "F"
    elif crit_count > 0:
        grade = "D"
    elif defect_density < 8.0 and sev_counts["High"] == 0:
        grade = "A"
    elif defect_density < 20.0 and sev_counts["High"] <= 3:
        grade = "B"
    elif defect_density < 40.0:
        grade = "C"
    else:
        grade = "D"

    return {
        "project_id": project_id,
        "quality_grade": grade,
        "total_findings": len(findings),
        "total_remediation_hours": round(total_hours, 1),
        "defect_density_per_kloc": defect_density,
        "severity_breakdown": sev_counts,
        "category_remediation_hours": cat_hours,
        "lines_of_code": loc
    }

@router.post("/project/{project_id}/analyze")
def trigger_project_code_analysis(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Trigger on-demand static code analysis on the project repository workspace."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    import os
    from app.services.source_code_analyzer import SourceCodeAnalyzer

    workspace_dir = os.path.abspath(os.path.join("storage", "repos", project_id))
    analyzer = SourceCodeAnalyzer(root_dir=workspace_dir if os.path.exists(workspace_dir) else ".")
    result = analyzer.analyze_repository()

    return {
        "project_id": project_id,
        "files_analyzed": result["files_analyzed"],
        "lines_of_code": result["lines_of_code"],
        "maintainability_index": result["maintainability_index"],
        "quality_grade": result["quality_grade"],
        "defect_density": result["defect_density"],
        "findings_count": len(result["findings"]),
        "severity_breakdown": result["severity_breakdown"],
        "hotspots": result["hotspots"][:5]
    }

