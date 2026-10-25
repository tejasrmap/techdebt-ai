import asyncio
import pytest
from pydantic import ValidationError
from app.services.ai_analyzer import (
    calculate_weighted_score,
    classify_risk,
    compare_semantic_versions,
    LLMAnalysisOutput,
    LLMRiskItem,
    AITechnologyDebtAnalyzer
)
from app.services.scheduler_service import validate_and_compute_next_run
from app.services.firecrawl_service import FirecrawlIntelligenceService
from app.services.memento_adapter import MementoMemoryAdapter

def test_semantic_version_comparison():
    # Major version lag
    v1 = compare_semantic_versions("18.2.0", "19.0.0")
    assert v1["status"] == "major_behind"
    assert v1["is_major_behind"] is True

    # Minor version lag
    v2 = compare_semantic_versions("0.100.0", "0.115.6")
    assert v2["status"] == "minor_behind"
    assert v2["is_minor_behind"] is True

    # Patch version lag
    v3 = compare_semantic_versions("4.17.15", "4.17.21")
    assert v3["status"] == "patch_behind"

    # Current / identical
    v4 = compare_semantic_versions("2.0.0", "2.0.0")
    assert v4["status"] == "current"

    # Unpinned / unknown
    v5 = compare_semantic_versions("latest", "unknown")
    assert v5["status"] == "unknown"

def test_llm_pydantic_schema_validation():
    # Valid output
    valid_data = {
        "maintenance_health": 80.0,
        "security_exposure": 85.0,
        "version_currency": 90.0,
        "community_activity": 75.0,
        "documentation_quality": 80.0,
        "ecosystem_compatibility": 85.0,
        "sustainability": 80.0,
        "upgrade_complexity": 90.0,
        "upgrade_complexity_level": "Low",
        "confidence_level": "High",
        "identified_problems": ["Minor patch lag"],
        "recommended_action": "Update to latest patch release in next cycle.",
        "risks": [
            {
                "severity": "Low",
                "title": "Patch Drift",
                "description": "Minor patch update available."
            }
        ]
    }
    output = LLMAnalysisOutput.model_validate(valid_data)
    assert output.maintenance_health == 80.0

    # Invalid score > 100 must be rejected
    invalid_data = valid_data.copy()
    invalid_data["maintenance_health"] = 150.0
    with pytest.raises(ValidationError):
        LLMAnalysisOutput.model_validate(invalid_data)

    # Invalid score < 0 must be rejected
    invalid_data2 = valid_data.copy()
    invalid_data2["security_exposure"] = -10.0
    with pytest.raises(ValidationError):
        LLMAnalysisOutput.model_validate(invalid_data2)

    # Invalid severity must be rejected
    invalid_data3 = valid_data.copy()
    invalid_data3["risks"] = [{"severity": "SuperCritical", "title": "Bad", "description": "Desc"}]
    with pytest.raises(ValidationError):
        LLMAnalysisOutput.model_validate(invalid_data3)

def test_cron_validation_and_next_run():
    # Valid weekly cron
    next_weekly = validate_and_compute_next_run("0 0 * * 1")
    assert next_weekly is not None

    # Valid daily cron
    next_daily = validate_and_compute_next_run("0 0 * * *")
    assert next_daily is not None

    # Invalid cron string must raise ValueError
    with pytest.raises(ValueError):
        validate_and_compute_next_run("invalid * cron string")

def test_firecrawl_connectivity_verification():
    # When no key is configured, truthfully reports fallback_active
    async def _run():
        svc = FirecrawlIntelligenceService(api_key="")
        res = await svc.verify_connectivity()
        assert res["status"] == "fallback_active"
        assert res["connected"] is False
    asyncio.run(_run())

def test_memento_connectivity_verification():
    # Truthfully reports PostgreSQL as authoritative storage and notes Memento MCP architecture
    async def _run():
        mem = MementoMemoryAdapter(api_key="")
        res = await mem.verify_connectivity()
        assert res["status"] == "postgresql_authoritative"
        assert res["mode"] == "postgresql"
        assert res["connected"] is True
        assert "runmemento.com" in res["message"]
    asyncio.run(_run())

def test_deterministic_scoring_without_hallucination():
    async def _run():
        analyzer = AITechnologyDebtAnalyzer()
        
        # 1. Deprecated package must have low maintenance score
        res_dep = await analyzer.analyze_technology(
            tech_name="deprecated-lib",
            installed_version="1.0.0",
            latest_version="1.0.0",
            is_deprecated=True,
            evidence_sources=[{"source_type": "documentation", "url": "https://example.com", "snippet": "deprecated"}]
        )
        assert res_dep["maintenance_health"] == 20.0
        assert res_dep["overall_score"] < 60.0
        assert any("deprecated" in p.lower() for p in res_dep["identified_problems"])

        # 2. Package with missing evidence must be marked Insufficient Evidence and not optimistic 100
        res_clean = await analyzer.analyze_technology(
            tech_name="clean-lib",
            installed_version="2.0.0",
            latest_version="2.0.0",
            is_deprecated=False,
            evidence_sources=[]
        )
        assert res_clean["security_exposure"] <= 60.0  # Missing security information is not assumed safe!
        assert res_clean["confidence_level"] == "Insufficient Evidence"
    asyncio.run(_run())

def test_memento_authoritative_postgresql_provenance():
    """Verify that snapshot creation authoritatively records postgresql provenance without unverified cloud claims."""
    async def _run():
        mem = MementoMemoryAdapter()
        from app.database import SessionLocal
        from app.models.all_models import Project, Assessment, Organization
        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            if not org:
                org = Organization(name="Memento Provenance Org", slug="memento-prov-org")
                db.add(org)
                db.commit()

            proj = db.query(Project).filter(Project.org_id == org.id).first()
            if not proj:
                proj = Project(org_id=org.id, name="Memento Test Project")
                db.add(proj)
                db.commit()

            ass = Assessment(project_id=proj.id, status="completed", overall_health_score=78.0)
            db.add(ass)
            db.commit()

            hist = await mem.record_assessment_snapshot(
                db=db,
                project_id=proj.id,
                assessment_id=ass.id,
                overall_score=78.0,
                risk_classification="Good",
                tech_scores=[],
                identified_risks=[]
            )
            # Must authoritatively report postgresql storage provider
            assert hist.storage_provider == "postgresql"
            assert hist.sync_status == "authoritative_postgresql"
            assert hist.sync_error == ""
        finally:
            db.close()
    asyncio.run(_run())

def test_firecrawl_publication_dates_and_maintenance_status():
    """Verify publication date remains None when missing, and statuses are distinguished."""
    async def _run():
        svc = FirecrawlIntelligenceService(api_key="")
        # Query known package via official registry
        intel = await svc.gather_technology_intelligence("react", "npm", "18.2.0")
        assert intel["maintenance_status"] in ["Active", "Deprecated", "Unmaintained", "End of life", "Unknown"]
        # Evidence sources must never have fake today's publication date if missing from source
        for ev in intel["evidence_sources"]:
            assert ev["publication_date"] is None or len(ev["publication_date"]) >= 4
            assert ev["is_official"] is True or ev["reliability_score"] <= 0.8
    asyncio.run(_run())

def test_scheduler_update_and_disable():
    """Verify updating schedule frequency and disabling recurring execution."""
    from fastapi.testclient import TestClient
    from app.main import app
    import uuid
    client = TestClient(app)

    uid = uuid.uuid4().hex[:6]
    reg = client.post("/api/v1/auth/register", json={
        "email": f"sched_mgr_{uid}@test.com",
        "password": "Password123!",
        "full_name": "Schedule Manager",
        "organization_name": f"Schedule Org {uid}"
    }).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    proj = client.post("/api/v1/projects", headers=headers, json={"name": "Sched Project"}).json()
    
    # 1. Create schedule
    sch = client.post("/api/v1/scheduler", headers=headers, json={
        "project_id": proj["id"],
        "frequency": "Weekly",
        "is_active": True
    }).json()
    assert sch["frequency"] == "Weekly"
    assert sch["is_active"] is True
    sch_id = sch["id"]

    # 2. Update to Monthly and disable
    updated = client.patch(f"/api/v1/scheduler/{sch_id}", headers=headers, json={
        "frequency": "Monthly",
        "is_active": False
    })
    assert updated.status_code == 200
    up_data = updated.json()
    assert up_data["frequency"] == "Monthly"
    assert up_data["is_active"] is False
    assert up_data["next_run_at"] is None
