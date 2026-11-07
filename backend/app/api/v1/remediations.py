"""
TechDebt AI v3.1.0 — Remediation Management & ROI API.

Endpoints for assignable Remediation Work Packages, multi-factor prioritization,
and configurable ROI simulation planning.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import case

from app.database import get_db
from app.models.all_models import (
    User,
    Project,
    Assessment,
    CodeFinding,
    RiskFinding,
    RemediationWorkPackage,
    AuditLog
)
from app.services.auth_service import get_current_user, require_roles
from app.services.remediation_roi_service import RemediationROIService

router = APIRouter(prefix="/remediations", tags=["Remediation & ROI Planning"])


class WorkPackageCreate(BaseModel):
    project_id: str
    title: str
    description: Optional[str] = ""
    finding_refs: List[Dict[str, Any]] = Field(default_factory=list)
    proposed_fix: Optional[str] = ""
    owner_user_id: Optional[str] = None
    target_date: Optional[datetime] = None
    status: Optional[str] = "Planned"
    verification_criteria: Optional[str] = ""


class WorkPackageUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    owner_user_id: Optional[str] = None
    target_date: Optional[datetime] = None
    proposed_fix: Optional[str] = None
    verification_criteria: Optional[str] = None


class ROIPlannerRequest(BaseModel):
    project_id: str
    hourly_rate: Optional[float] = RemediationROIService.DEFAULT_HOURLY_RATE
    team_size: Optional[int] = 5
    hours_per_week_per_dev: Optional[float] = 10.0
    planning_horizon_weeks: Optional[int] = 4
    budget_usd: Optional[float] = None


def _serialize_package(pkg: RemediationWorkPackage) -> Dict[str, Any]:
    return {
        "id": pkg.id,
        "org_id": pkg.org_id,
        "project_id": pkg.project_id,
        "title": pkg.title,
        "description": pkg.description or "",
        "priority": pkg.priority or "Medium",
        "priority_score": pkg.priority_score or 50.0,
        "priority_rationale": pkg.priority_rationale or "",
        "finding_refs": pkg.finding_refs_json or [],
        "proposed_fix": pkg.proposed_fix or "",
        "dependencies": pkg.dependencies_json or [],
        "estimated_hours": pkg.estimated_hours or 2.0,
        "owner_user_id": pkg.owner_user_id,
        "target_date": pkg.target_date.isoformat() if pkg.target_date else None,
        "status": pkg.status or "Planned",
        "verification_criteria": pkg.verification_criteria or "",
        "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
        "updated_at": pkg.updated_at.isoformat() if pkg.updated_at else None,
    }


@router.get("/packages")
def list_work_packages(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = (
        db.query(RemediationWorkPackage)
        .join(Project, RemediationWorkPackage.project_id == Project.id)
        .filter(Project.org_id == current_user.org_id)
    )
    if project_id:
        query = query.filter(RemediationWorkPackage.project_id == project_id)
    if status:
        query = query.filter(RemediationWorkPackage.status == status)
    if priority:
        query = query.filter(RemediationWorkPackage.priority == priority)

    packages = query.order_by(RemediationWorkPackage.priority_score.desc(), RemediationWorkPackage.created_at.desc()).all()
    return [_serialize_package(p) for p in packages]


@router.post("/packages", status_code=status.HTTP_201_CREATED)
def create_work_package(
    req: WorkPackageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    # Calculate aggregate hours and priority score from findings
    total_hours = sum(float(f.get("estimated_remediation_hours", 1.5) or 1.5) for f in req.finding_refs)
    if not total_hours:
        total_hours = 2.0

    # Derive highest priority from included findings
    highest_score = 50.0
    highest_tier = "Medium"
    highest_rationale = "Created work package."

    for f in req.finding_refs:
        p_calc = RemediationROIService.calculate_priority_score(f)
        if p_calc["priority_score"] > highest_score:
            highest_score = p_calc["priority_score"]
            highest_tier = p_calc["priority_tier"]
            highest_rationale = p_calc["priority_rationale"]

    pkg = RemediationWorkPackage(
        org_id=current_user.org_id,
        project_id=req.project_id,
        title=req.title,
        description=req.description,
        priority=highest_tier,
        priority_score=highest_score,
        priority_rationale=highest_rationale,
        finding_refs_json=req.finding_refs,
        proposed_fix=req.proposed_fix,
        estimated_hours=round(total_hours, 1),
        owner_user_id=req.owner_user_id,
        target_date=req.target_date,
        status=req.status or "Planned",
        verification_criteria=req.verification_criteria
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return _serialize_package(pkg)


@router.put("/packages/{package_id}")
def update_work_package(
    package_id: str,
    req: WorkPackageUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pkg = (
        db.query(RemediationWorkPackage)
        .join(Project, RemediationWorkPackage.project_id == Project.id)
        .filter(RemediationWorkPackage.id == package_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Work package not found or unauthorized")

    if req.title is not None:
        pkg.title = req.title
    if req.description is not None:
        pkg.description = req.description
    if req.status is not None:
        pkg.status = req.status
    if req.owner_user_id is not None:
        pkg.owner_user_id = req.owner_user_id
    if req.target_date is not None:
        pkg.target_date = req.target_date
    if req.proposed_fix is not None:
        pkg.proposed_fix = req.proposed_fix
    if req.verification_criteria is not None:
        pkg.verification_criteria = req.verification_criteria

    db.commit()
    db.refresh(pkg)
    return _serialize_package(pkg)


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_package(
    package_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pkg = (
        db.query(RemediationWorkPackage)
        .join(Project, RemediationWorkPackage.project_id == Project.id)
        .filter(RemediationWorkPackage.id == package_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Work package not found or unauthorized")

    db.delete(pkg)
    db.commit()
    return None


@router.post("/roi-planner")
def plan_remediation_roi(
    req: ROIPlannerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Simulates multi-factor priority allocation and calculates expected ROI within engineering capacity."""
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    # Fetch latest completed assessment findings
    latest_asmt = (
        db.query(Assessment)
        .filter(Assessment.project_id == project.id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )

    findings: List[Dict[str, Any]] = []
    if latest_asmt and hasattr(latest_asmt, "code_findings") and latest_asmt.code_findings:
        for cf in latest_asmt.code_findings:
            findings.append({
                "id": cf.id,
                "type": "code_finding",
                "file_path": cf.file_path,
                "title": cf.title,
                "severity": cf.severity,
                "category": cf.category,
                "confidence": cf.confidence,
                "estimated_remediation_hours": cf.estimated_remediation_hours,
                "created_at": cf.created_at
            })

    # Also add RiskFindings
    risks = db.query(RiskFinding).filter(RiskFinding.project_id == project.id, RiskFinding.status != "Resolved").all()
    for rf in risks:
        findings.append({
            "id": rf.id,
            "type": "risk_finding",
            "file_path": rf.technology.name if rf.technology else "dependency",
            "title": rf.title,
            "severity": rf.severity,
            "category": "security",
            "confidence": "High",
            "estimated_remediation_hours": rf.estimated_remediation_hours,
            "created_at": rf.created_at
        })

    simulation = RemediationROIService.calculate_remediation_roi(
        findings=findings,
        hourly_rate=req.hourly_rate or RemediationROIService.DEFAULT_HOURLY_RATE,
        team_size=req.team_size or 5,
        hours_per_week_per_dev=req.hours_per_week_per_dev or 10.0,
        planning_horizon_weeks=req.planning_horizon_weeks or 4,
        budget_usd=req.budget_usd
    )
    simulation["project_id"] = project.id
    simulation["project_name"] = project.name
    return simulation


@router.get("/prioritized-findings/{project_id}")
def get_prioritized_findings(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns all project findings ranked by multi-factor priority score with transparent explanations."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    latest_asmt = (
        db.query(Assessment)
        .filter(Assessment.project_id == project.id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )

    findings: List[Dict[str, Any]] = []
    if latest_asmt and hasattr(latest_asmt, "code_findings") and latest_asmt.code_findings:
        for cf in latest_asmt.code_findings:
            f_dict = {
                "id": cf.id,
                "type": "code_finding",
                "file_path": cf.file_path,
                "line_start": cf.line_start,
                "title": cf.title,
                "severity": cf.severity,
                "category": cf.category,
                "confidence": cf.confidence,
                "estimated_remediation_hours": cf.estimated_remediation_hours,
                "created_at": cf.created_at
            }
            p_calc = RemediationROIService.calculate_priority_score(f_dict)
            f_dict.update(p_calc)
            findings.append(f_dict)

    risks = db.query(RiskFinding).filter(RiskFinding.project_id == project.id, RiskFinding.status != "Resolved").all()
    for rf in risks:
        f_dict = {
            "id": rf.id,
            "type": "risk_finding",
            "file_path": rf.technology.name if rf.technology else "dependency",
            "line_start": 1,
            "title": rf.title,
            "severity": rf.severity,
            "category": "security",
            "confidence": "High",
            "estimated_remediation_hours": rf.estimated_remediation_hours,
            "created_at": rf.created_at
        }
        p_calc = RemediationROIService.calculate_priority_score(f_dict)
        f_dict.update(p_calc)
        findings.append(f_dict)

    findings.sort(key=lambda x: x["priority_score"], reverse=True)
    return findings[:limit]
