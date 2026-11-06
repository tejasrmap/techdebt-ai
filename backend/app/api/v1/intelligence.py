import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.database import get_db
from app.models.all_models import User, HistoricalAssessment, Project, ProjectTechnology, Technology
from app.schemas.schemas import TechnologyComparisonRequest, TechnologyComparisonResponse, ComparisonCategory
from app.services.auth_service import get_current_user
from app.services.firecrawl_service import FirecrawlIntelligenceService
from app.services.ai_analyzer import AITechnologyDebtAnalyzer
from app.services.memento_adapter import MementoMemoryAdapter
from app.services.vulnerability_service import VulnerabilityService
from pydantic import BaseModel

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

class VulnerabilityCheckRequest(BaseModel):
    package: Optional[str] = None
    version: Optional[str] = None
    ecosystem: Optional[str] = None
    dependencies: Optional[List[Dict[str, Any]]] = None

class LicenseAuditRequest(BaseModel):
    license: Optional[str] = None
    dependencies: Optional[List[Dict[str, Any]]] = None
    is_commercial: bool = True

@router.post("/vulnerabilities/check")
def check_vulnerabilities(
    req: VulnerabilityCheckRequest,
    current_user: User = Depends(get_current_user)
):
    if req.package and req.version:
        vulns = VulnerabilityService.check_package_vulnerabilities(
            package_name=req.package,
            version_str=req.version,
            ecosystem=req.ecosystem
        )
        return {
            "package": req.package,
            "version": req.version,
            "ecosystem": req.ecosystem,
            "vulnerabilities": vulns,
            "count": len(vulns),
            "highest_severity": max([v["severity"] for v in vulns], default="NONE")
        }
    elif req.dependencies:
        results = []
        for dep in req.dependencies:
            name = dep.get("name", "")
            ver = dep.get("version", "latest")
            eco = dep.get("ecosystem")
            vulns = VulnerabilityService.check_package_vulnerabilities(name, ver, eco)
            if vulns:
                results.extend(vulns)
        return {
            "vulnerabilities": results,
            "count": len(results),
            "highest_severity": max([v["severity"] for v in results], default="NONE")
        }
    else:
        raise HTTPException(status_code=400, detail="Provide either package + version or a dependencies list.")

@router.post("/licenses/audit")
def audit_licenses(
    req: LicenseAuditRequest,
    current_user: User = Depends(get_current_user)
):
    if req.license:
        audit = VulnerabilityService.audit_license(req.license, is_commercial_product=req.is_commercial)
        return audit
    elif req.dependencies:
        findings = []
        status_counts = {"COMPLIANT": 0, "WARNING": 0, "VIOLATION": 0}
        for dep in req.dependencies:
            lic = dep.get("license")
            res = VulnerabilityService.audit_license(lic, is_commercial_product=req.is_commercial)
            res["package"] = dep.get("name", "unknown")
            findings.append(res)
            st = res["compliance_status"]
            if st in status_counts:
                status_counts[st] += 1
        return {
            "findings": findings,
            "summary": status_counts,
            "has_violations": status_counts["VIOLATION"] > 0
        }
    else:
        raise HTTPException(status_code=400, detail="Provide either a license string or a dependencies list.")

@router.get("/project/{project_id}/security-audit")
def get_project_security_audit(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    links = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == project.id).all()
    dep_payloads = []
    for link in links:
        tech = db.query(Technology).filter(Technology.id == link.technology_id).first()
        if tech:
            dep_payloads.append({
                "name": tech.name,
                "version": link.installed_version or "latest",
                "ecosystem": tech.ecosystem or "",
                "license": getattr(tech, "license", "MIT") # Default permissive if not set
            })

    audit_result = VulnerabilityService.audit_project(dep_payloads, is_commercial_product=True)
    audit_result["project_id"] = project.id
    audit_result["project_name"] = project.name
    return audit_result

class AIProviderTestRequest(BaseModel):
    provider: Optional[str] = None
    prompt: Optional[str] = "Evaluate technical debt architecture"
    force_fallback: bool = False

@router.get("/ai-providers")
async def get_ai_providers_status(
    current_user: User = Depends(get_current_user)
):
    from app.services.modular_ai_engine import modular_ai_engine
    return await modular_ai_engine.get_providers_status()

@router.post("/ai-providers/test")
async def test_ai_provider(
    req: AIProviderTestRequest,
    current_user: User = Depends(get_current_user)
):
    from app.services.modular_ai_engine import modular_ai_engine
    preferred = "deterministic" if req.force_fallback else req.provider
    resp = await modular_ai_engine.generate_completion(
        prompt=req.prompt or "Provide a software engineering architecture recommendation.",
        preferred_provider=preferred
    )
    return {
        "status": "success",
        "provider": resp.provider,
        "model": resp.model,
        "content_length": len(resp.content),
        "content_preview": resp.content[:200],
        "latency_ms": resp.latency_ms,
        "fallback_used": resp.fallback_used
    }

class PromptInspectionRequest(BaseModel):
    text: str
    mode: str = "STRICT"  # STRICT, SANITIZE, PERMISSIVE

@router.post("/prompt-defense/inspect")
def inspect_prompt(
    req: PromptInspectionRequest,
    current_user: User = Depends(get_current_user)
):
    from app.services.prompt_defense_service import PromptDefenseService
    result = PromptDefenseService.inspect_input(req.text, mode=req.mode.upper())
    fenced_example, boundary_nonce = PromptDefenseService.wrap_untrusted_input(req.text)
    result["fenced_example"] = fenced_example
    result["boundary_nonce"] = boundary_nonce
    return result

class AssistantChatRequest(BaseModel):
    project_id: str
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None

class AssistantRecommendationsRequest(BaseModel):
    project_id: str

@router.post("/assistant/chat")
async def assistant_chat(
    req: AssistantChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    from app.services.billing_service import BillingService
    allowed, _, _ = BillingService.check_entitlement(db, current_user.org_id, "ai_recommendations")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if hasattr(status, "HTTP_402_PAYMENT_REQUIRED") else 402,
            detail="AI Assistant and refactoring recommendations require a Team Starter or higher subscription plan."
        )

    from app.services.ai_engineering_assistant import AIEngineeringAssistant
    from app.models.all_models import Assessment, RiskFinding, ProjectTechnology, Technology

    # Gather project telemetry
    latest_asmt = (
        db.query(Assessment)
        .filter(Assessment.project_id == project.id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )
    raw = latest_asmt.raw_output if latest_asmt and latest_asmt.raw_output else {}
    hotspots = raw.get("hotspots", [])
    code_findings = raw.get("code_findings", [])
    
    risks = db.query(RiskFinding).filter(RiskFinding.project_id == project.id).all()
    risk_list = [{"title": r.title, "severity": r.severity} for r in risks]

    links = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == project.id).all()
    dep_list = []
    for l in links:
        t = db.query(Technology).filter(Technology.id == l.technology_id).first()
        if t:
            dep_list.append({"name": t.name, "version": l.installed_version or "latest"})

    telemetry = {
        "health_score": latest_asmt.overall_health_score if latest_asmt else 80.0,
        "risk_classification": latest_asmt.risk_classification if latest_asmt else "Good",
        "findings": risk_list + code_findings,
        "hotspots": hotspots,
        "dependencies": dep_list
    }

    assistant = AIEngineeringAssistant()
    chat_result = await assistant.chat(
        project_name=project.name,
        user_message=req.message,
        conversation_history=req.conversation_history,
        telemetry=telemetry
    )
    chat_result["project_id"] = project.id

    # Record AI usage in metering ledger
    from app.services.ai_usage_service import AIUsageMeteringService
    AIUsageMeteringService.record_usage(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        provider=chat_result.get("provider_used", "deterministic"),
        model="assistant-chat-v3",
        prompt_tokens=max(10, len(req.message) // 4 + 150),
        completion_tokens=max(10, len(chat_result.get("response", "")) // 4),
        latency_ms=chat_result.get("latency_ms", 10.0),
        operation_type="assistant_chat"
    )

    return chat_result

@router.post("/assistant/recommendations")
async def get_assistant_recommendations(
    req: AssistantRecommendationsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    from app.services.billing_service import BillingService
    allowed, _, _ = BillingService.check_entitlement(db, current_user.org_id, "ai_recommendations")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if hasattr(status, "HTTP_402_PAYMENT_REQUIRED") else 402,
            detail="AI Assistant and refactoring recommendations require a Team Starter or higher subscription plan."
        )

    from app.services.ai_engineering_assistant import AIEngineeringAssistant
    from app.models.all_models import Assessment, ProjectTechnology, Technology

    latest_asmt = (
        db.query(Assessment)
        .filter(Assessment.project_id == project.id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )
    raw = latest_asmt.raw_output if latest_asmt and latest_asmt.raw_output else {}
    hotspots = raw.get("hotspots", [])
    code_findings = raw.get("code_findings", [])

    links = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == project.id).all()
    dep_list = [{"name": l.technology_id, "version": l.installed_version or "latest"} for l in links]

    score = latest_asmt.overall_health_score if latest_asmt else 80.0
    risk_class = latest_asmt.risk_classification if latest_asmt else "Good"
    hours = latest_asmt.estimated_remediation_hours if latest_asmt else 10.0

    assistant = AIEngineeringAssistant()
    recs = await assistant.generate_engineering_recommendations(
        project_name=project.name,
        overall_score=score,
        risk_classification=risk_class,
        hotspots=hotspots,
        code_findings=code_findings,
        dependencies=dep_list,
        total_remediation_hours=hours
    )
    recs["project_id"] = project.id
    return recs

class ArchitectureReviewRequest(BaseModel):
    files: List[str]
    code_findings: Optional[List[Dict[str, Any]]] = None
    code_metrics: Optional[Dict[str, Any]] = None

@router.post("/architecture-review")
def review_architecture(
    req: ArchitectureReviewRequest,
    current_user: User = Depends(get_current_user)
):
    from app.services.architecture_review_engine import ArchitectureReviewEngine
    return ArchitectureReviewEngine.analyze_architecture(
        files=req.files,
        code_findings=req.code_findings,
        code_metrics=req.code_metrics
    )

@router.get("/project/{project_id}/architecture-review")
def get_project_architecture_review(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    from app.services.architecture_review_engine import ArchitectureReviewEngine
    from app.models.all_models import Assessment

    latest_asmt = (
        db.query(Assessment)
        .filter(Assessment.project_id == project.id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )
    raw = latest_asmt.raw_output if latest_asmt and latest_asmt.raw_output else {}
    files = raw.get("analyzed_files", ["src/api/routes.py", "src/services/app.py", "src/models/user.py"])
    code_findings = raw.get("code_findings", [])
    code_metrics = raw.get("code_metrics", {})

    review = ArchitectureReviewEngine.analyze_architecture(
        files=files,
        code_findings=code_findings,
        code_metrics=code_metrics
    )
    review["project_id"] = project.id
    review["project_name"] = project.name
    return review

@router.get("/ai-usage/summary")
def get_ai_usage_summary(
    period: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.ai_usage_service import AIUsageMeteringService
    return AIUsageMeteringService.get_usage_summary(db=db, org_id=current_user.org_id, period=period)

@router.get("/ai-usage/records")
def get_ai_usage_records(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.ai_usage_service import AIUsageMeteringService
    return AIUsageMeteringService.get_usage_records(db=db, org_id=current_user.org_id, limit=limit)







