from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.all_models import (
    Project, Technology, ProjectTechnology, Assessment,
    TechnologyScore, RiskFinding, HistoricalAssessment, User
)
from app.schemas.schemas import (
    DashboardOverviewResponse, ExecutiveKPIsResponse,
    RemediationVelocityResponse, PortfolioMatrixResponse, PortfolioProjectItem
)
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

SEVERITY_COST_MAP = {
    "Critical": 1500.0,
    "High": 600.0,
    "Medium": 250.0,
    "Low": 75.0
}

SLA_DAYS_MAP = {
    "Critical": 7,
    "High": 30,
    "Medium": 90,
    "Low": 180
}

@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieve comprehensive customer dashboard overview."""
    org_id = current_user.org_id

    projects = db.query(Project).filter(Project.org_id == org_id, Project.is_archived == False).all()
    total_projects = len(projects)
    project_ids = [p.id for p in projects]

    if not project_ids:
        return DashboardOverviewResponse(
            total_projects=0,
            total_technologies=0,
            technologies_requiring_attention=0,
            critical_technology_risks=0,
            overall_health_score=None,
            outdated_dependencies=0,
            declining_maintenance_count=0,
            health_distribution={"Healthy": 0, "Good": 0, "Needs Attention": 0, "High Risk": 0, "Critical": 0},
            risk_distribution={"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
            recent_assessments=[],
            historical_trend=[{"date": "Baseline", "health_score": 100.0, "score_delta": 0.0}],
            project_health_breakdown=[],
            total_financial_liability_usd=0.0,
            average_technical_debt_ratio=0.0,
            total_lines_of_code=0,
            remediation_mttr_days=0.0
        )

    # 2. Total technologies across org projects
    total_technologies = (
        db.query(func.count(func.distinct(ProjectTechnology.technology_id)))
        .filter(ProjectTechnology.project_id.in_(project_ids))
        .scalar() or 0
    )

    # Determine latest completed assessment per active project to avoid historical double-counting
    latest_assessment_ids = []
    latest_assessments = []
    for p in projects:
        la = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        if la:
            latest_assessment_ids.append(la.id)
            latest_assessments.append(la)

    # 3. Technologies requiring attention & outdated dependencies from latest active assessments
    scores = (
        db.query(TechnologyScore)
        .filter(TechnologyScore.assessment_id.in_(latest_assessment_ids))
        .all()
    ) if latest_assessment_ids else []
    
    attention_count = sum(1 for s in scores if s.overall_score < 70)
    outdated_count = sum(1 for s in scores if s.version_currency < 80)
    declining_maint_count = sum(1 for s in scores if s.maintenance_health < 70)

    # 4. Critical risks
    critical_risks = (
        db.query(RiskFinding)
        .filter(
            RiskFinding.project_id.in_(project_ids),
            RiskFinding.severity.in_(["Critical", "High"]),
            RiskFinding.status.in_(["Open", "Investigating", "In Progress"])
        )
        .count()
    )

    # 5. Overall health score average
    valid_scores = [a.overall_health_score for a in latest_assessments if a.overall_health_score is not None]
    overall_health = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 100.0

    # Distributions
    health_dist = {"Healthy": 0, "Good": 0, "Needs Attention": 0, "High Risk": 0, "Critical": 0}
    for s in scores:
        c = s.risk_classification
        if c in health_dist:
            health_dist[c] += 1
        else:
            health_dist["Good"] += 1

    risk_dist = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    all_risks = db.query(RiskFinding).filter(RiskFinding.project_id.in_(project_ids)).all()
    for r in all_risks:
        if r.severity in risk_dist:
            risk_dist[r.severity] += 1

    # Project health breakdown & Commercial calculations
    project_breakdown = []
    total_liability = 0.0
    tdr_sum = 0.0
    tdr_count = 0
    total_loc = 0

    for p in projects:
        latest_a = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        tech_cnt = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == p.id).count()
        p_health = latest_a.overall_health_score if latest_a and latest_a.overall_health_score is not None else 100.0
        p_risk = latest_a.risk_classification if latest_a else "Healthy"
        
        if latest_a:
            if latest_a.technical_debt_ratio is not None:
                tdr_sum += latest_a.technical_debt_ratio
                tdr_count += 1
            if latest_a.lines_of_code:
                total_loc += latest_a.lines_of_code
            if latest_a.estimated_remediation_hours:
                total_liability += latest_a.estimated_remediation_hours * 120.0
        
        project_breakdown.append({
            "project_id": p.id,
            "project_name": p.name,
            "technology_count": tech_cnt,
            "health_score": p_health,
            "risk_classification": p_risk
        })

    # If no assessment hours were populated, calculate liability from open risk findings
    if total_liability == 0.0:
        for r in all_risks:
            if r.status not in ["Resolved", "Accepted Risk"]:
                total_liability += SEVERITY_COST_MAP.get(r.severity, 150.0)

    # MTTR calculation
    resolved_risks = [r for r in all_risks if r.status == "Resolved" and r.resolved_at and r.created_at]
    if resolved_risks:
        durations = [(r.resolved_at - r.created_at).total_seconds() / 86400.0 for r in resolved_risks]
        mttr = round(sum(durations) / len(durations), 1)
    else:
        mttr = 0.0

    avg_tdr = round(tdr_sum / tdr_count, 1) if tdr_count > 0 else 0.0

    # Historical trend
    history_entries = (
        db.query(HistoricalAssessment)
        .filter(HistoricalAssessment.project_id.in_(project_ids))
        .order_by(HistoricalAssessment.created_at.asc())
        .limit(20)
        .all()
    )
    historical_trend = [
        {
            "date": h.created_at.strftime("%b %d"),
            "health_score": h.health_score,
            "score_delta": h.score_delta,
            "project_id": h.project_id
        }
        for h in history_entries
    ]
    if not historical_trend:
        historical_trend = [
            {"date": "Baseline", "health_score": overall_health, "score_delta": 0.0}
        ]

    recent_assessments_data = [
        {
            "id": a.id,
            "project_name": a.project.name if a.project else "",
            "overall_health_score": a.overall_health_score,
            "risk_classification": a.risk_classification,
            "confidence_level": a.confidence_level,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for a in latest_assessments
    ]

    return DashboardOverviewResponse(
        total_projects=total_projects,
        total_technologies=total_technologies,
        technologies_requiring_attention=attention_count,
        critical_technology_risks=critical_risks,
        overall_health_score=overall_health,
        outdated_dependencies=outdated_count,
        declining_maintenance_count=declining_maint_count,
        health_distribution=health_dist,
        risk_distribution=risk_dist,
        recent_assessments=recent_assessments_data,
        historical_trend=historical_trend,
        project_health_breakdown=project_breakdown,
        total_financial_liability_usd=round(total_liability, 2),
        average_technical_debt_ratio=avg_tdr,
        total_lines_of_code=total_loc,
        remediation_mttr_days=mttr
    )

@router.get("/executive-kpis", response_model=ExecutiveKPIsResponse)
def get_executive_kpis(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieve executive-level KPIs: financial liability, TDR, SLA compliance, and pillar breakdown."""
    org_id = current_user.org_id
    projects = db.query(Project).filter(Project.org_id == org_id, Project.is_archived == False).all()
    project_ids = [p.id for p in projects]

    if not project_ids:
        return ExecutiveKPIsResponse(
            total_financial_liability_usd=0.0,
            average_technical_debt_ratio=0.0,
            remediation_mttr_days=0.0,
            sla_compliance_rate=100.0,
            total_vulnerabilities=0,
            critical_vulnerabilities=0,
            high_vulnerabilities=0,
            total_lines_of_code=0,
            portfolio_status="Healthy",
            pillar_breakdown={
                "code_quality": 100.0,
                "architecture": 100.0,
                "security": 100.0,
                "dependencies": 100.0,
                "maintainability": 100.0
            },
            top_hotspots=[]
        )

    all_risks = db.query(RiskFinding).filter(RiskFinding.project_id.in_(project_ids)).all()
    
    # Financial liability & counts
    total_liability = 0.0
    crit_count = 0
    high_count = 0
    now = datetime.utcnow()
    sla_compliant_count = 0

    for r in all_risks:
        if r.status not in ["Resolved", "Accepted Risk"]:
            total_liability += SEVERITY_COST_MAP.get(r.severity, 150.0)
            if r.severity == "Critical":
                crit_count += 1
            elif r.severity == "High":
                high_count += 1
            
            allowed_days = SLA_DAYS_MAP.get(r.severity, 90)
            age_days = (now - r.created_at).total_seconds() / 86400.0 if r.created_at else 0
            if age_days <= allowed_days:
                sla_compliant_count += 1
        else:
            # Resolved within SLA
            if r.resolved_at and r.created_at:
                dur_days = (r.resolved_at - r.created_at).total_seconds() / 86400.0
                allowed_days = SLA_DAYS_MAP.get(r.severity, 90)
                if dur_days <= allowed_days:
                    sla_compliant_count += 1
            else:
                sla_compliant_count += 1

    sla_compliance_rate = round((sla_compliant_count / len(all_risks)) * 100.0, 1) if all_risks else 100.0

    # Resolved MTTR
    resolved_risks = [r for r in all_risks if r.status == "Resolved" and r.resolved_at and r.created_at]
    mttr = round(sum((r.resolved_at - r.created_at).total_seconds() / 86400.0 for r in resolved_risks) / len(resolved_risks), 1) if resolved_risks else 0.0

    # Aggregate metrics strictly from the latest completed assessment per project
    latest_assessments = []
    for p in projects:
        la = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        if la:
            latest_assessments.append(la)

    total_loc = sum(a.lines_of_code or 0 for a in latest_assessments)
    valid_tdr = [a.technical_debt_ratio for a in latest_assessments if a.technical_debt_ratio is not None]
    avg_tdr = round(sum(valid_tdr) / len(valid_tdr), 1) if valid_tdr else 0.0

    # 5 Pillars from latest assessments without fabricated default scores
    code_scores = [a.code_maintainability_score for a in latest_assessments if a.code_maintainability_score is not None]
    arch_scores = [a.architecture_score for a in latest_assessments if a.architecture_score is not None]
    sec_scores = [a.security_score for a in latest_assessments if a.security_score is not None]
    dep_scores = [a.dependency_score for a in latest_assessments if a.dependency_score is not None]
    maint_scores = [a.reliability_score for a in latest_assessments if a.reliability_score is not None]

    pillar_breakdown = {
        "code_quality": round(sum(code_scores) / len(code_scores), 1) if code_scores else 0.0,
        "architecture": round(sum(arch_scores) / len(arch_scores), 1) if arch_scores else 0.0,
        "security": round(sum(sec_scores) / len(sec_scores), 1) if sec_scores else 0.0,
        "dependencies": round(sum(dep_scores) / len(dep_scores), 1) if dep_scores else 0.0,
        "maintainability": round(sum(maint_scores) / len(maint_scores), 1) if maint_scores else 0.0,
    }

    avg_pillar = sum(pillar_breakdown.values()) / 5.0
    if avg_pillar >= 80 and crit_count == 0:
        portfolio_status = "Healthy"
    elif avg_pillar >= 60 and crit_count <= 2:
        portfolio_status = "At Risk"
    else:
        portfolio_status = "Critical"

    # Top hotspots from open risks
    open_risks = [r for r in all_risks if r.status not in ["Resolved", "Accepted Risk"]]
    open_risks.sort(key=lambda x: (0 if x.severity == "Critical" else (1 if x.severity == "High" else 2)))
    top_hotspots = [
        {
            "risk_id": r.id,
            "project_name": r.project.name if r.project else "Unknown",
            "title": r.title,
            "severity": r.severity,
            "status": r.status,
            "business_impact": r.business_impact or "High debt exposure"
        }
        for r in open_risks[:5]
    ]

    return ExecutiveKPIsResponse(
        total_financial_liability_usd=round(total_liability, 2),
        average_technical_debt_ratio=avg_tdr,
        remediation_mttr_days=mttr,
        sla_compliance_rate=sla_compliance_rate,
        total_vulnerabilities=len(open_risks),
        critical_vulnerabilities=crit_count,
        high_vulnerabilities=high_count,
        total_lines_of_code=total_loc,
        portfolio_status=portfolio_status,
        pillar_breakdown=pillar_breakdown,
        top_hotspots=top_hotspots
    )

@router.get("/remediation-velocity", response_model=RemediationVelocityResponse)
def get_remediation_velocity(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieve velocity metrics: open vs resolved debt, MTTR breakdown, and monthly trajectory."""
    org_id = current_user.org_id
    projects = db.query(Project).filter(Project.org_id == org_id, Project.is_archived == False).all()
    project_ids = [p.id for p in projects]

    if not project_ids:
        return RemediationVelocityResponse(
            total_open_risks=0,
            total_resolved_risks=0,
            total_accepted_risks=0,
            overall_mttr_days=0.0,
            mttr_by_severity={"Critical": 0.0, "High": 0.0, "Medium": 0.0, "Low": 0.0},
            monthly_trend=[]
        )

    all_risks = db.query(RiskFinding).filter(RiskFinding.project_id.in_(project_ids)).all()
    open_risks = [r for r in all_risks if r.status not in ["Resolved", "Accepted Risk"]]
    resolved_risks = [r for r in all_risks if r.status == "Resolved"]
    accepted_risks = [r for r in all_risks if r.status == "Accepted Risk"]

    # MTTR overall and by severity
    durations_by_sev = {"Critical": [], "High": [], "Medium": [], "Low": []}
    all_durations = []
    for r in resolved_risks:
        if r.resolved_at and r.created_at:
            d = (r.resolved_at - r.created_at).total_seconds() / 86400.0
            all_durations.append(d)
            if r.severity in durations_by_sev:
                durations_by_sev[r.severity].append(d)

    overall_mttr = round(sum(all_durations) / len(all_durations), 1) if all_durations else 0.0
    mttr_by_sev = {
        sev: round(sum(durs) / len(durs), 1) if durs else 0.0
        for sev, durs in durations_by_sev.items()
    }

    # Monthly trend calculation
    # Bucket risks into the last 6 months
    now = datetime.utcnow()
    monthly_trend = []
    for i in range(5, -1, -1):
        m_start = datetime(now.year, now.month, 1) - timedelta(days=i * 30)
        m_label = m_start.strftime("%b %Y")
        
        opened_in_m = sum(1 for r in all_risks if r.created_at and r.created_at.year == m_start.year and r.created_at.month == m_start.month)
        resolved_in_m = sum(1 for r in resolved_risks if r.resolved_at and r.resolved_at.year == m_start.year and r.resolved_at.month == m_start.month)
        
        monthly_trend.append({
            "month": m_label,
            "risks_opened": opened_in_m,
            "risks_resolved": resolved_in_m,
            "net_debt_change": opened_in_m - resolved_in_m
        })

    return RemediationVelocityResponse(
        total_open_risks=len(open_risks),
        total_resolved_risks=len(resolved_risks),
        total_accepted_risks=len(accepted_risks),
        overall_mttr_days=overall_mttr,
        mttr_by_severity=mttr_by_sev,
        monthly_trend=monthly_trend
    )

@router.get("/portfolio-matrix", response_model=PortfolioMatrixResponse)
def get_portfolio_matrix(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieve detailed project-by-project health and debt portfolio matrix."""
    org_id = current_user.org_id
    projects = db.query(Project).filter(Project.org_id == org_id, Project.is_archived == False).all()

    items: List[PortfolioProjectItem] = []
    total_liability = 0.0
    tdr_sum = 0.0

    for p in projects:
        latest_a = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        crit_count = (
            db.query(RiskFinding)
            .filter(
                RiskFinding.project_id == p.id,
                RiskFinding.severity == "Critical",
                RiskFinding.status.notin_(["Resolved", "Accepted Risk"])
            )
            .count()
        )

        h_score = latest_a.overall_health_score if latest_a and latest_a.overall_health_score is not None else 100.0
        tdr = latest_a.technical_debt_ratio if latest_a and latest_a.technical_debt_ratio is not None else 0.0
        loc = latest_a.lines_of_code if latest_a and latest_a.lines_of_code else 0
        hours = latest_a.estimated_remediation_hours if latest_a and latest_a.estimated_remediation_hours else 0.0
        liability = round(hours * 120.0, 2)
        if liability == 0.0:
            # Fallback to open risk finding costs
            open_p_risks = db.query(RiskFinding).filter(RiskFinding.project_id == p.id, RiskFinding.status.notin_(["Resolved", "Accepted Risk"])).all()
            liability = sum(SEVERITY_COST_MAP.get(r.severity, 150.0) for r in open_p_risks)

        risk_level = "Critical" if h_score < 60 or crit_count > 2 else ("High Risk" if h_score < 75 else ("Needs Attention" if h_score < 85 else "Healthy"))
        last_date = latest_a.created_at.strftime("%Y-%m-%d %H:%M") if latest_a and latest_a.created_at else None

        items.append(PortfolioProjectItem(
            project_id=p.id,
            project_name=p.name,
            health_score=h_score,
            technical_debt_ratio=tdr,
            financial_liability_usd=round(liability, 2),
            lines_of_code=loc,
            risk_level=risk_level,
            critical_risks_count=crit_count,
            last_assessed_at=last_date
        ))

        total_liability += liability
        tdr_sum += tdr

    avg_tdr = round(tdr_sum / len(projects), 1) if projects else 0.0

    return PortfolioMatrixResponse(
        total_projects=len(projects),
        total_portfolio_liability_usd=round(total_liability, 2),
        average_tdr=avg_tdr,
        projects=items
    )
