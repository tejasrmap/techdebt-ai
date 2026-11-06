from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.all_models import Project, Technology, ProjectTechnology, Assessment, TechnologyScore, RiskFinding, HistoricalAssessment, User
from app.schemas.schemas import DashboardOverviewResponse
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org_id = current_user.org_id

    # 1. Total projects
    projects = db.query(Project).filter(Project.org_id == org_id).all()
    total_projects = len(projects)
    project_ids = [p.id for p in projects]

    if not project_ids:
        return DashboardOverviewResponse(
            total_projects=0,
            total_technologies=0,
            technologies_requiring_attention=0,
            outdated_dependencies=0,
            declining_maintenance=0,
            critical_risks=0,
            overall_health_score=None,
            health_distribution={"Healthy": 0, "Good": 0, "Needs Attention": 0, "High Risk": 0, "Critical": 0},
            risk_distribution={"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
            recent_assessments=[]
        )

    # 2. Total technologies across org projects
    total_technologies = (
        db.query(func.count(func.distinct(ProjectTechnology.technology_id)))
        .filter(ProjectTechnology.project_id.in_(project_ids))
        .scalar() or 0
    )

    # Latest completed assessments per project
    latest_assessments = (
        db.query(Assessment)
        .filter(Assessment.project_id.in_(project_ids), Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .limit(10)
        .all()
    )

    # 3. Technologies requiring attention & outdated dependencies
    scores = (
        db.query(TechnologyScore)
        .join(Assessment)
        .filter(Assessment.project_id.in_(project_ids))
        .all()
    )
    
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
    if valid_scores:
        overall_health = round(sum(valid_scores) / len(valid_scores), 1)
    else:
        overall_health = 100.0

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

    # Project health breakdown
    project_breakdown = []
    for p in projects:
        latest_a = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        tech_cnt = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == p.id).count()
        project_breakdown.append({
            "project_id": p.id,
            "project_name": p.name,
            "technology_count": tech_cnt,
            "health_score": latest_a.overall_health_score if latest_a else 100.0,
            "risk_classification": latest_a.risk_classification if latest_a else "Healthy"
        })

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
        project_health_breakdown=project_breakdown
    )

