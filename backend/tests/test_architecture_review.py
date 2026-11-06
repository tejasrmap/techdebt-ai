import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.architecture_review_engine import ArchitectureReviewEngine
from app.database import SessionLocal
from app.models.all_models import Project, Assessment

client = TestClient(app)

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"arch_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Arch Tester",
        "organization_name": f"Arch Org {uid}"
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

def test_architecture_engine_antipattern_and_twelve_factor_analysis():
    files = [
        "src/api/routes.py",
        "src/services/billing_service.py",
        "src/models/invoice.py",
        "tests/test_billing.py"
    ]
    code_findings = [
        {
            "rule_id": "EXCESSIVE_METHOD_LENGTH",
            "title": "God Method in Billing Engine",
            "severity": "High",
            "file_path": "src/services/billing_service.py"
        },
        {
            "rule_id": "MUTABLE_GLOBAL_STATE",
            "title": "Global state dictionary mutated across requests",
            "severity": "Medium",
            "file_path": "src/services/billing_service.py"
        }
    ]

    result = ArchitectureReviewEngine.analyze_architecture(
        files=files,
        code_findings=code_findings
    )

    assert "pattern_compliance_score" in result
    assert "twelve_factor_readiness_score" in result
    assert result["anti_patterns_count"] >= 1
    assert any(ap["rule_id"] == "GOD_MODULE_BLOAT" for ap in result["anti_patterns"])

    # Verify blueprint and migration plan
    assert "target_architecture_blueprint" in result
    assert len(result["target_architecture_blueprint"]["layers"]) == 4
    assert "migration_plan" in result
    assert len(result["migration_plan"]) == 3

def test_missing_layers_anti_pattern():
    # Only loose script files with no architecture layers
    files = ["script1.py", "script2.py"]
    result = ArchitectureReviewEngine.analyze_architecture(files=files)
    assert any(ap["rule_id"] == "LACK_OF_TIERED_ABSTRACTION" for ap in result["anti_patterns"])
    assert result["pattern_compliance_score"] < 80.0

def test_architecture_review_api_endpoints():
    headers = get_test_headers()

    # 1. Direct POST review
    post_res = client.post("/api/v1/intelligence/architecture-review", json={
        "files": ["app/api/auth.py", "app/services/auth.py", "app/models/user.py"],
        "code_findings": []
    }, headers=headers)
    assert post_res.status_code == 200
    p_data = post_res.json()
    assert p_data["pattern_compliance_score"] >= 80.0
    assert "target_architecture_blueprint" in p_data

    # 2. Project Architecture Review GET endpoint
    p_name = f"Arch Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/arch"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    # Insert assessment
    db = SessionLocal()
    try:
        asmt = Assessment(
            project_id=proj_id,
            status="completed",
            overall_health_score=85.0,
            raw_output={
                "analyzed_files": ["api/v1/users.py", "services/user_service.py", "models/user.py"],
                "code_findings": []
            }
        )
        db.add(asmt)
        db.commit()
    finally:
        db.close()

    get_res = client.get(f"/api/v1/intelligence/project/{proj_id}/architecture-review", headers=headers)
    assert get_res.status_code == 200
    g_data = get_res.json()
    assert g_data["project_id"] == proj_id
    assert "architecture_grade" in g_data
    assert "migration_plan" in g_data
