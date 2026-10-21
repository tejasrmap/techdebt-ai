import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.database import get_db
from app.models.all_models import User, HistoricalAssessment, Project
from app.schemas.schemas import TechnologyComparisonRequest, TechnologyComparisonResponse, ComparisonCategory
from app.services.auth_service import get_current_user
from app.services.firecrawl_service import FirecrawlIntelligenceService
from app.services.ai_analyzer import AITechnologyDebtAnalyzer
from app.services.memento_adapter import MementoMemoryAdapter

router = APIRouter(prefix="/intelligence", tags=["Intelligence & Memory"])

@router.post("/crawl")
async def crawl_technology(
    technology: str,
    ecosystem: str = "npm",
    installed_version: Optional[str] = "latest",
    current_user: User = Depends(get_current_user)
):
    service = FirecrawlIntelligenceService()
    intel = await service.gather_technology_intelligence(
        tech_name=technology,
        ecosystem=ecosystem,
        installed_version=installed_version
    )
    return intel

@router.post("/compare", response_model=TechnologyComparisonResponse)
async def compare_technologies(
    req: TechnologyComparisonRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compare 2 to 4 technologies across all 8 evaluation categories with balanced synthesis.
    """
    tech_names = [t.strip() for t in req.technology_names if t.strip()]
    if len(tech_names) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two technologies to compare.")

    firecrawl_svc = FirecrawlIntelligenceService()
    analyzer = AITechnologyDebtAnalyzer()

    gathered_techs = {}
    for name in tech_names:
        intel = await firecrawl_svc.gather_technology_intelligence(name, "npm")
        analysis = await analyzer.analyze_technology(
            tech_name=name,
            installed_version="latest",
            latest_version=intel.get("latest_stable_version", "latest"),
            is_deprecated=intel.get("is_deprecated", False),
            evidence_sources=intel.get("evidence_sources", [])
        )
        gathered_techs[name] = analysis

    categories_list = [
        ("Maintenance Health", "maintenance_health", "Frequency of official patches, vulnerability fixes, and release cadence."),
        ("Security Exposure", "security_exposure", "Known CVE advisories, patch responsiveness, and threat surface."),
        ("Version Currency", "version_currency", "Active releases and alignment with current LTS/stable branches."),
        ("Community Activity", "community_activity", "Downstream adoption, ecosystem activity, and developer community size."),
        ("Documentation Quality", "documentation_quality", "Depth of official guides, migration tutorials, and API references."),
        ("Ecosystem Compatibility", "ecosystem_compatibility", "Interoperability with standard toolchains, bundlers, and cloud environments."),
        ("Upgrade Complexity", "upgrade_complexity", "Impact of breaking changes across major revisions."),
        ("Long-term Sustainability", "sustainability", "Institutional backing, foundation stewardship, and long-term roadmap visibility.")
    ]

    categories_out = []
    tradeoffs_out = {}

    for cat_name, key, description in categories_list:
        scores_map = {}
        for name in tech_names:
            tech_analysis = gathered_techs[name]
            scores_map[name] = float(tech_analysis.get(key, 85.0))
        
        # Determine highest/lowest for balanced context
        sorted_by_score = sorted(scores_map.items(), key=lambda x: x[1], reverse=True)
        top_name, top_score = sorted_by_score[0]
        runner_name, runner_score = sorted_by_score[-1]
        
        if top_score == runner_score:
            analysis_text = f"Both technologies exhibit comparable strength in {cat_name.lower()}."
        else:
            analysis_text = (
                f"{top_name} leads in {cat_name.lower()} ({top_score}/100), "
                f"while {runner_name} demonstrates trade-offs or slightly higher migration considerations ({runner_score}/100)."
            )

        categories_out.append(ComparisonCategory(
            category=cat_name,
            scores=scores_map,
            analysis=analysis_text
        ))

    for name in tech_names:
        score = gathered_techs[name].get("overall_score", 85.0)
        tradeoffs_out[name] = [
            f"Overall Architecture Fit Score: {score}/100",
            f"Upgrade Path: {gathered_techs[name].get('upgrade_complexity_level', 'Moderate')} complexity",
            gathered_techs[name].get('recommended_action', 'Evaluate project requirements and ecosystem synergy.')
        ]

    summary = (
        f"Comparative review between {', '.join(tech_names)}. "
        "Neither technology is universally superior; selection should align with your team's existing skill sets, "
        "cloud infrastructure, and maintenance constraints."
    )

    recommendations = (
        "Recommendations: Validate licensing and backward compatibility. "
        "Prioritize the option with closer ecosystem alignment to minimize integration friction."
    )

    return TechnologyComparisonResponse(
        technologies=tech_names,
        categories=categories_out,
        balanced_summary=summary,
        tradeoffs=tradeoffs_out,
        recommendations=recommendations
    )

@router.get("/history")
async def get_historical_memory(
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    memento = MementoMemoryAdapter()
    query = (
        db.query(HistoricalAssessment)
        .join(Project)
        .filter(Project.org_id == current_user.org_id)
    )
    if project_id:
        query = query.filter(HistoricalAssessment.project_id == project_id)

    history = query.order_by(HistoricalAssessment.created_at.desc()).limit(30).all()
    
    return {
        "memory_provider": memento.mode,
        "records": [
            {
                "id": h.id,
                "project_id": h.project_id,
                "project_name": h.snapshot_data.get("project_name", ""),
                "health_score": h.health_score,
                "score_delta": h.score_delta,
                "risk_classification": h.risk_classification,
                "summary_of_changes": h.summary_of_changes,
                "new_risks_count": h.new_risks_count,
                "resolved_risks_count": h.resolved_risks_count,
                "created_at": h.created_at
            }
            for h in history
        ]
    }

