import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.debt_scoring_engine import CommercialDebtScoringEngine
from app.database import get_db
from app.models.all_models import Project, Assessment, User, TechnologyScore, RiskFinding

client = TestClient(app)

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"scoring_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Scoring Tester",
        "organization_name": f"Scoring Org {uid}"
    })
    if reg.status_code in (200, 201):
        token = reg.json()["access_token"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_explainable_debt_score_pillars_and_penalties():
    code_metrics = {
        "lines_of_code": 10000,
        "files_analyzed": 50,
        "test_files_count": 12,
        "avg_cyclomatic_complexity": 3.2,
        "max_cyclomatic_complexity": 28,  # > 20 triggers penalty
        "code_duplication_percentage": 6.5, # > 3% triggers duplication penalty
        "maintainability_index": 72.0
    }
    code_findings = [
        {"category": "architecture", "severity": "High", "rule_id": "ARCH_HOTSPOT", "estimated_remediation_hours": 3.0},
        {"category": "security", "severity": "Critical", "rule_id": "SEC_EVAL", "estimated_remediation_hours": 6.0},
        {"category": "complexity", "severity": "Medium", "rule_id": "HIGH_COMPLEXITY", "estimated_remediation_hours": 1.5}
    ]
    risk_findings = [
        {"severity": "Critical", "title": "Critical CVE in log4j"}
    ]

    breakdown = CommercialDebtScoringEngine.explain_debt_score(
        code_metrics=code_metrics,
        code_findings=code_findings,
        risk_findings=risk_findings,
        hourly_rate=120.0
    )

    assert breakdown["scoring_version"] in ("v3.0.0", "v3.1.0")
    assert "pillars" in breakdown
    pillars = breakdown["pillars"]
    assert len(pillars) == 5
    assert "architecture_debt" in pillars
    assert "security_debt" in pillars
    assert "code_quality_debt" in pillars
    assert "dependency_debt" in pillars
    assert "testing_debt" in pillars

    # Security penalty verification: critical findings penalized score
    assert len(pillars["security_debt"]["penalty_factors"]) >= 1
    assert any("critical" in p.lower() for p in pillars["security_debt"]["penalty_factors"])
    assert pillars["security_debt"]["financial_cost_usd"] > 0

    # Architecture penalty verification: max complexity > 20
    assert any("cyclomatic" in p.lower() for p in pillars["architecture_debt"]["penalty_factors"])

    # Financial cost verification
    assert breakdown["blended_hourly_rate_usd"] == 120.0
    expected_cost = breakdown["total_remediation_hours"] * 120.0
    assert abs(breakdown["total_financial_cost_usd"] - expected_cost) < 0.1
    assert "executive_summary" in breakdown

def test_explain_score_api_endpoints():
    headers = get_test_headers()

    # 1. Standalone explain-score endpoint
    req_body = {
        "code_metrics": {
            "lines_of_code": 5000,
            "files_analyzed": 20,
            "test_files_count": 5,
            "maintainability_index": 85.0
        },
        "code_findings": [
            {"category": "security", "severity": "High", "estimated_remediation_hours": 3.0}
        ],
        "hourly_rate": 150.0
    }
    resp = client.post("/api/v1/assessments/explain-score", json=req_body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["blended_hourly_rate_usd"] == 150.0
    assert "pillars" in data
    assert data["pillars"]["security_debt"]["remediation_hours"] >= 3.0

    # 2. Project Assessment Breakdown endpoint
    p_name = f"Explain Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/explain"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    # Directly create an assessment record in DB to test the debt-breakdown route
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        assessment = Assessment(
            project_id=proj_id,
            status="completed",
            overall_health_score=82.5,
            risk_classification="Good",
            lines_of_code=4000,
            files_analyzed=25,
            estimated_remediation_hours=12.5,
            raw_output={
                "code_metrics": {"lines_of_code": 4000, "files_analyzed": 25, "maintainability_index": 80.0},
                "code_findings": [{"category": "maintainability", "severity": "Medium", "estimated_remediation_hours": 1.5}]
            }
        )
        db.add(assessment)
        db.commit()
        db.refresh(assessment)
        asmt_id = assessment.id
    finally:
        db.close()

    breakdown_res = client.get(f"/api/v1/assessments/{asmt_id}/debt-breakdown?hourly_rate=125.0", headers=headers)
    assert breakdown_res.status_code == 200
    b_data = breakdown_res.json()
    assert b_data["assessment_id"] == asmt_id
    assert b_data["project_id"] == proj_id
    assert b_data["blended_hourly_rate_usd"] == 125.0
    assert "pillars" in b_data
    assert "executive_summary" in b_data
