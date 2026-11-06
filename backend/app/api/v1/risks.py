from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.models.all_models import RiskFinding, Project, User, Technology, AuditLog
from app.schemas.schemas import RiskResponse, RiskUpdate
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/risks", tags=["Risk Management"])

@router.get("", response_model=List[RiskResponse])
def get_risks(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = (
        db.query(RiskFinding)
        .join(Project)
        .filter(Project.org_id == current_user.org_id)
    )
    if project_id:
        # Validate project belongs to organization
        proj = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        query = query.filter(RiskFinding.project_id == project_id)
    if status:
        query = query.filter(RiskFinding.status == status)
    if severity:
        query = query.filter(RiskFinding.severity == severity)

    risks = query.order_by(RiskFinding.created_at.desc()).all()
    results = []
    for r in risks:
        results.append({
            "id": r.id,
            "project_id": r.project_id,
            "project_name": r.project.name if r.project else "",
            "technology_id": r.technology_id,
            "technology_name": r.technology.name if r.technology else "",
            "severity": r.severity,
            "title": r.title,
            "description": r.description or "",
            "business_impact": r.business_impact or "",
            "technical_impact": r.technical_impact or "",
            "status": r.status,
            "assigned_to": r.assigned_to,
            "assignee_name": r.assignee.full_name if r.assignee else None,
            "resolution_notes": r.resolution_notes or "",
            "resolved_at": r.resolved_at,
            "created_at": r.created_at
        })
    return results

@router.put("/{risk_id}", response_model=RiskResponse)
def update_risk(
    risk_id: str,
    req: RiskUpdate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    r = (
        db.query(RiskFinding)
        .join(Project)
        .filter(RiskFinding.id == risk_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Risk finding not found or unauthorized")

    if req.status is not None:
        r.status = req.status
        if req.status in ["Resolved", "Accepted Risk"] and not r.resolved_at:
            r.resolved_at = datetime.utcnow()
        elif req.status not in ["Resolved", "Accepted Risk"]:
            r.resolved_at = None

    if req.severity is not None:
        r.severity = req.severity

    if req.assigned_to is not None:
        # If assigned, verify assignee is member of same org
        if req.assigned_to != "":
            assignee = db.query(User).filter(User.id == req.assigned_to, User.org_id == current_user.org_id).first()
            if not assignee:
                raise HTTPException(status_code=400, detail="Assignee must be an active member of your organization")
            r.assigned_to = assignee.id
        else:
            r.assigned_to = None

    if req.resolution_notes is not None:
        r.resolution_notes = req.resolution_notes

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="risk.update",
        resource_type="risk_finding",
        resource_id=r.id,
        details={"status": r.status, "severity": r.severity}
    )
    db.add(audit)
    db.commit()
    db.refresh(r)

    return {
        "id": r.id,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else "",
        "technology_id": r.technology_id,
        "technology_name": r.technology.name if r.technology else "",
        "severity": r.severity,
        "title": r.title,
        "description": r.description or "",
        "business_impact": r.business_impact or "",
        "technical_impact": r.technical_impact or "",
        "status": r.status,
        "assigned_to": r.assigned_to,
        "assignee_name": r.assignee.full_name if r.assignee else None,
        "resolution_notes": r.resolution_notes or "",
        "resolved_at": r.resolved_at,
        "created_at": r.created_at
    }

@router.post("/{risk_id}/resolve", response_model=RiskResponse)
def resolve_risk(
    risk_id: str,
    resolution_notes: Optional[str] = "",
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    update_data = RiskUpdate(status="Resolved", resolution_notes=resolution_notes or "Marked resolved by engineer.")
    return update_risk(risk_id, update_data, current_user, db)

@router.patch("/{risk_id}/remediation-status", response_model=RiskResponse)
def update_remediation_status(
    risk_id: str,
    req: RiskUpdate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    r = (
        db.query(RiskFinding)
        .join(Project)
        .filter(RiskFinding.id == risk_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Risk finding not found or unauthorized")

    action = "risk.remediation_updated"
    old_status = r.status

    if req.status is not None:
        valid_statuses = {"Open", "Investigating", "Planned", "In Progress", "Resolved", "Accepted Risk"}
        if req.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{req.status}'. Must be one of: {', '.join(sorted(valid_statuses))}"
            )
        
        # Check for reopened transition
        if old_status in ("Resolved", "Accepted Risk") and req.status in ("Open", "Investigating", "In Progress"):
            action = "risk.reopened"
            r.resolved_at = None
        elif req.status in ("Resolved", "Accepted Risk") and not r.resolved_at:
            r.resolved_at = datetime.utcnow()
        elif req.status not in ("Resolved", "Accepted Risk"):
            r.resolved_at = None

        r.status = req.status

    if req.severity is not None:
        r.severity = req.severity

    if req.assigned_to is not None:
        if req.assigned_to != "":
            assignee = db.query(User).filter(User.id == req.assigned_to, User.org_id == current_user.org_id).first()
            if not assignee:
                raise HTTPException(status_code=400, detail="Assignee must be an active member of your organization")
            r.assigned_to = assignee.id
        else:
            r.assigned_to = None

    if req.resolution_notes is not None:
        r.resolution_notes = req.resolution_notes

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action=action,
        resource_type="risk_finding",
        resource_id=r.id,
        details={"old_status": old_status, "new_status": r.status, "severity": r.severity}
    )
    db.add(audit)
    db.commit()
    db.refresh(r)

    return {
        "id": r.id,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else "",
        "technology_id": r.technology_id,
        "technology_name": r.technology.name if r.technology else "",
        "severity": r.severity,
        "title": r.title,
        "description": r.description or "",
        "business_impact": r.business_impact or "",
        "technical_impact": r.technical_impact or "",
        "status": r.status,
        "assigned_to": r.assigned_to,
        "assignee_name": r.assignee.full_name if r.assignee else None,
        "resolution_notes": r.resolution_notes or "",
        "resolved_at": r.resolved_at,
        "created_at": r.created_at
    }

@router.get("/project/{project_id}/remediation-metrics")
def get_project_remediation_metrics(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    risks = db.query(RiskFinding).filter(RiskFinding.project_id == project.id).all()
    total = len(risks)
    
    status_counts = {
        "Open": 0,
        "Investigating": 0,
        "Planned": 0,
        "In Progress": 0,
        "Resolved": 0,
        "Accepted Risk": 0
    }
    
    severity_map = {
        "Critical": {"total": 0, "open": 0, "resolved": 0},
        "High": {"total": 0, "open": 0, "resolved": 0},
        "Medium": {"total": 0, "open": 0, "resolved": 0},
        "Low": {"total": 0, "open": 0, "resolved": 0}
    }

    mttr_durations = []
    assignee_stats = {}

    for r in risks:
        st = r.status if r.status in status_counts else "Open"
        status_counts[st] += 1

        sev = r.severity if r.severity in severity_map else "Medium"
        severity_map[sev]["total"] += 1
        if st in ("Resolved", "Accepted Risk"):
            severity_map[sev]["resolved"] += 1
        else:
            severity_map[sev]["open"] += 1

        # Calculate MTTR if resolved
        if r.resolved_at and r.created_at:
            delta_hours = max(0.1, (r.resolved_at - r.created_at).total_seconds() / 3600.0)
            mttr_durations.append(delta_hours)

        # Assignee stats
        if r.assigned_to:
            uid = r.assigned_to
            name = r.assignee.full_name if r.assignee else "Unknown"
            if uid not in assignee_stats:
                assignee_stats[uid] = {"user_id": uid, "name": name, "open_count": 0, "resolved_count": 0}
            if st in ("Resolved", "Accepted Risk"):
                assignee_stats[uid]["resolved_count"] += 1
            else:
                assignee_stats[uid]["open_count"] += 1

    resolved_total = status_counts["Resolved"] + status_counts["Accepted Risk"]
    res_rate = round((resolved_total / total * 100.0) if total > 0 else 100.0, 1)
    mttr = round((sum(mttr_durations) / len(mttr_durations)) if mttr_durations else 0.0, 1)

    # Reopened count from audit logs
    reopened_count = db.query(AuditLog).filter(
        AuditLog.org_id == current_user.org_id,
        AuditLog.action == "risk.reopened",
        AuditLog.resource_type == "risk_finding"
    ).count()

    return {
        "project_id": project.id,
        "project_name": project.name,
        "total_findings": total,
        "resolved_findings": resolved_total,
        "open_findings": total - resolved_total,
        "resolution_rate_pct": res_rate,
        "mean_time_to_remediate_hours": mttr,
        "reopened_findings_count": reopened_count,
        "status_breakdown": status_counts,
        "severity_breakdown": severity_map,
        "assignee_leaderboard": list(assignee_stats.values())
    }

