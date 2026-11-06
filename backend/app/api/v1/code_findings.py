import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import (
    User,
    CodeFinding,
    Assessment,
    Project,
    RepositoryConnection,
    RepositoryAnalysisSnapshot,
    AuditLog,
)
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/code-findings", tags=["Code Findings & Diagnostics"])

SEVERITY_RANK_EXPR = case(
    (CodeFinding.severity == "Critical", 5),
    (CodeFinding.severity == "High", 4),
    (CodeFinding.severity == "Medium", 3),
    (CodeFinding.severity == "Low", 2),
    (CodeFinding.severity == "Info", 1),
    else_=0,
)

VALID_TRIAGE_STATUSES = {"Open", "In Progress", "Resolved", "Accepted Risk", "False Positive", "Deferred"}


def _serialize_finding(f: CodeFinding) -> Dict[str, Any]:
    return {
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
        "status": f.status or "Open",
        "assigned_to": f.assigned_to,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        "analyzer_name": f.analyzer_name or "SourceCodeAnalyzer",
        "analyzer_version": f.analyzer_version or "v3.1.0",
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.get("/assessment/{assessment_id}")
def get_assessment_code_findings(
    assessment_id: str,
    severity: Optional[str] = Query(None, description="Filter by severity: Critical, High, Medium, Low, Info"),
    category: Optional[str] = Query(None, description="Filter by category: security, complexity, maintainability, architecture, reliability"),
    status: Optional[str] = Query(None, description="Filter by triage status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve fine-grained source code diagnostic findings ordered strictly by severity rank."""
    assessment = (
        db.query(Assessment)
        .join(Project, Assessment.project_id == Project.id)
        .filter(Assessment.id == assessment_id, Project.org_id == current_user.org_id)
        .first()
    )

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found or access denied")

    query = db.query(CodeFinding).filter(CodeFinding.assessment_id == assessment_id)
    if severity:
        query = query.filter(CodeFinding.severity == severity)
    if category:
        query = query.filter(CodeFinding.category == category)
    if status:
        query = query.filter(CodeFinding.status == status)

    findings = query.order_by(
        SEVERITY_RANK_EXPR.desc(),
        CodeFinding.file_path.asc(),
        CodeFinding.line_start.asc(),
    ).all()

    return [_serialize_finding(f) for f in findings]


@router.get("/project/{project_id}")
def get_project_latest_findings(
    project_id: str,
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve code findings from the most recent completed assessment (or persisted snapshot) for a project."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_assessment = (
        db.query(Assessment)
        .filter(Assessment.project_id == project_id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )

    if latest_assessment:
        q = db.query(CodeFinding).filter(CodeFinding.assessment_id == latest_assessment.id)
        if status:
            q = q.filter(CodeFinding.status == status)
        findings = q.order_by(
            SEVERITY_RANK_EXPR.desc(),
            CodeFinding.file_path.asc(),
            CodeFinding.line_start.asc(),
        ).all()
        return {
            "assessment_id": latest_assessment.id,
            "commit_sha": latest_assessment.commit_sha,
            "analyzer_version": latest_assessment.analyzer_version,
            "scoring_version": latest_assessment.scoring_version,
            "technical_debt_ratio": latest_assessment.technical_debt_ratio,
            "estimated_remediation_hours": latest_assessment.estimated_remediation_hours,
            "lines_of_code": latest_assessment.lines_of_code,
            "findings_count": len(findings),
            "findings": [_serialize_finding(f) for f in findings],
        }

    # If repository was ingested via snapshot before running a full assessment, surface snapshot findings
    latest_snapshot = (
        db.query(RepositoryAnalysisSnapshot)
        .filter(RepositoryAnalysisSnapshot.project_id == project_id)
        .order_by(RepositoryAnalysisSnapshot.created_at.desc())
        .first()
    )
    if latest_snapshot:
        snap_findings = list(latest_snapshot.code_findings_json or [])
        return {
            "assessment_id": None,
            "snapshot_id": latest_snapshot.id,
            "commit_sha": latest_snapshot.commit_sha,
            "analyzer_version": latest_snapshot.analyzer_version,
            "scoring_version": None,
            "technical_debt_ratio": None,
            "estimated_remediation_hours": round(
                sum(float(f.get("estimated_remediation_hours", 1.0) or 1.0) for f in snap_findings), 1
            ),
            "lines_of_code": latest_snapshot.lines_of_code,
            "findings_count": len(snap_findings),
            "findings": snap_findings,
        }

    return {"assessment_id": None, "findings_count": 0, "findings": []}


@router.get("/{finding_id}")
def get_code_finding_detail(
    finding_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    finding = (
        db.query(CodeFinding)
        .join(Project, CodeFinding.project_id == Project.id)
        .filter(CodeFinding.id == finding_id, Project.org_id == current_user.org_id)
        .first()
    )

    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    return _serialize_finding(finding)


class CodeFindingTriageRequest(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None


@router.patch("/{finding_id}")
def triage_code_finding(
    finding_id: str,
    req: CodeFindingTriageRequest,
    current_user: User = Depends(
        require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager", "Developer"])
    ),
    db: Session = Depends(get_db),
):
    """Update triage status and assignee for a code finding."""
    finding = (
        db.query(CodeFinding)
        .join(Project, CodeFinding.project_id == Project.id)
        .filter(CodeFinding.id == finding_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if req.status is not None:
        if req.status not in VALID_TRIAGE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid triage status '{req.status}'. Valid values: {sorted(VALID_TRIAGE_STATUSES)}",
            )
        finding.status = req.status
        if req.status in ("Resolved", "Accepted Risk", "False Positive"):
            finding.resolved_at = finding.resolved_at or datetime.utcnow()
        else:
            finding.resolved_at = None

    if req.assigned_to is not None:
        if req.assigned_to == "":
            finding.assigned_to = None
        else:
            assignee = (
                db.query(User)
                .filter(User.id == req.assigned_to, User.org_id == current_user.org_id)
                .first()
            )
            if not assignee:
                raise HTTPException(status_code=400, detail="Assignee must belong to your organization")
            finding.assigned_to = assignee.id

    db.add(
        AuditLog(
            user_id=current_user.id,
            org_id=current_user.org_id,
            action="code_finding.triage",
            resource_type="code_finding",
            resource_id=finding.id,
            details={"status": finding.status, "assigned_to": finding.assigned_to},
        )
    )
    db.commit()
    db.refresh(finding)
    return _serialize_finding(finding)


@router.get("/project/{project_id}/quality-summary")
def get_project_quality_summary(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve quality score, defect density, and severity breakdown scoped strictly to the latest run."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_assessment = (
        db.query(Assessment)
        .filter(Assessment.project_id == project_id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )

    sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
    cat_hours: Dict[str, float] = {}
    total_hours = 0.0

    if latest_assessment:
        findings = db.query(CodeFinding).filter(CodeFinding.assessment_id == latest_assessment.id).all()
        for f in findings:
            sev = f.severity or "Medium"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
            cat = f.category or "maintainability"
            hours = float(f.estimated_remediation_hours or 1.0)
            cat_hours[cat] = round(cat_hours.get(cat, 0.0) + hours, 1)
            total_hours += hours
        loc = latest_assessment.lines_of_code or 0
        total_findings = len(findings)
    else:
        latest_snapshot = (
            db.query(RepositoryAnalysisSnapshot)
            .filter(RepositoryAnalysisSnapshot.project_id == project_id)
            .order_by(RepositoryAnalysisSnapshot.created_at.desc())
            .first()
        )
        if not latest_snapshot:
            return {
                "project_id": project_id,
                "quality_grade": "N/A",
                "total_findings": 0,
                "total_remediation_hours": 0.0,
                "defect_density_per_kloc": 0.0,
                "severity_breakdown": sev_counts,
                "category_remediation_hours": cat_hours,
                "lines_of_code": 0,
            }
        snap_findings = list(latest_snapshot.code_findings_json or [])
        for f in snap_findings:
            sev = f.get("severity") or "Medium"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
            cat = f.get("category") or "maintainability"
            hours = float(f.get("estimated_remediation_hours") or 1.0)
            cat_hours[cat] = round(cat_hours.get(cat, 0.0) + hours, 1)
            total_hours += hours
        loc = latest_snapshot.lines_of_code or 0
        total_findings = len(snap_findings)

    if loc <= 0 and total_findings == 0:
        return {
            "project_id": project_id,
            "quality_grade": "N/A",
            "total_findings": 0,
            "total_remediation_hours": 0.0,
            "defect_density_per_kloc": 0.0,
            "severity_breakdown": sev_counts,
            "category_remediation_hours": cat_hours,
            "lines_of_code": 0,
        }

    defect_density = round((total_findings / max(1, loc)) * 1000, 2)
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
        "total_findings": total_findings,
        "total_remediation_hours": round(total_hours, 1),
        "defect_density_per_kloc": defect_density,
        "severity_breakdown": sev_counts,
        "category_remediation_hours": cat_hours,
        "lines_of_code": loc,
    }


@router.post("/project/{project_id}/analyze")
def trigger_project_code_analysis(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve or execute static code analysis strictly for the target project's isolated
    snapshot or workspace. NEVER falls back to scanning the host server directory.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_snapshot = (
        db.query(RepositoryAnalysisSnapshot)
        .filter(RepositoryAnalysisSnapshot.project_id == project_id)
        .order_by(RepositoryAnalysisSnapshot.created_at.desc())
        .first()
    )
    if latest_snapshot is not None:
        fm = latest_snapshot.file_metrics_json or {}
        findings = latest_snapshot.code_findings_json or []
        return {
            "project_id": project_id,
            "snapshot_id": latest_snapshot.id,
            "commit_sha": latest_snapshot.commit_sha,
            "analyzer_version": latest_snapshot.analyzer_version,
            "status": "completed",
            "files_analyzed": latest_snapshot.files_analyzed or 0,
            "lines_of_code": latest_snapshot.lines_of_code or 0,
            "maintainability_index": latest_snapshot.maintainability_index,
            "quality_grade": latest_snapshot.quality_grade or "N/A",
            "defect_density": latest_snapshot.defect_density or 0.0,
            "findings_count": len(findings),
            "severity_breakdown": fm.get(
                "severity_breakdown",
                {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0},
            ),
            "hotspots": (fm.get("hotspots") or [])[:5],
        }

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    candidate_dir = None
    if conn and conn.local_path and os.path.exists(conn.local_path):
        candidate_dir = os.path.abspath(conn.local_path)
    else:
        legacy_dir = os.path.abspath(os.path.join("storage", "repos", project_id))
        if os.path.exists(legacy_dir):
            candidate_dir = legacy_dir

    if candidate_dir:
        from app.services.source_code_analyzer import SourceCodeAnalyzer

        analyzer = SourceCodeAnalyzer(root_dir=candidate_dir)
        result = analyzer.analyze_repository()
        return {
            "project_id": project_id,
            "status": "completed",
            "files_analyzed": result["files_analyzed"],
            "lines_of_code": result["lines_of_code"],
            "maintainability_index": result["maintainability_index"],
            "quality_grade": result["quality_grade"],
            "defect_density": result["defect_density"],
            "findings_count": len(result["findings"]),
            "severity_breakdown": result["severity_breakdown"],
            "hotspots": result["hotspots"][:5],
        }

    return {
        "project_id": project_id,
        "status": "no_source_available",
        "message": "No repository source or persisted analysis snapshot available for this project.",
        "files_analyzed": 0,
        "lines_of_code": 0,
        "maintainability_index": None,
        "quality_grade": "N/A",
        "defect_density": 0.0,
        "findings_count": 0,
        "severity_breakdown": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0},
        "hotspots": [],
    }
