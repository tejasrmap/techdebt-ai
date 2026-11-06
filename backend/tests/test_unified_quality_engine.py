import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.source_code_analyzer import SourceCodeAnalyzer
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def get_auth_headers():
    rate_limiter.reset()
    reg = client.post("/api/v1/auth/register", json={
        "email": f"quality_{uuid.uuid4().hex[:6]}@techdebt.ai",
        "password": "SecurePassword123!",
        "full_name": "Quality Lead",
        "organization_name": f"Quality Org {uuid.uuid4().hex[:4]}"
    }).json()
    return {"Authorization": f"Bearer {reg['access_token']}"}

def test_source_code_analyzer_unified_metrics(tmp_path):
    # Setup sample multi-language repository
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    # 1. Clean python file
    (repo_dir / "app.py").write_text("def hello(name):\n    return f'Hello {name}'\n", encoding="utf-8")

    # 2. Problematic python file
    (repo_dir / "calc.py").write_text("""
def calculate(a, b, c, d, e):
    try:
        if a:
            if b:
                if c:
                    return eval(d)
    except:
        pass
    return 0
""", encoding="utf-8")

    # 3. Clean JS file
    (repo_dir / "index.js").write_text("const sum = (x, y) => x + y;\nmodule.exports = { sum };\n", encoding="utf-8")

    analyzer = SourceCodeAnalyzer(root_dir=str(repo_dir))
    res = analyzer.analyze_repository()

    assert res["files_analyzed"] == 3
    assert res["lines_of_code"] > 0
    assert "quality_grade" in res
    assert res["quality_grade"] in ("A", "B", "C", "D", "F")
    assert "maintainability_index" in res
    assert "defect_density" in res
    assert "severity_breakdown" in res
    assert "category_remediation_hours" in res
    assert isinstance(res["hotspots"], list)
    if res["hotspots"]:
        assert "hotspot_score" in res["hotspots"][0]

def test_code_duplication_engine(tmp_path):
    repo_dir = tmp_path / "dup_repo"
    repo_dir.mkdir()

    dup_content = """
function sharedEnterpriseValidationRoutine(input) {
    if (!input || input.length === 0) {
        throw new Error("Invalid input payload");
    }
    const sanitized = input.trim().toLowerCase();
    const hash = computeSha256(sanitized);
    return { sanitized, hash };
}
"""
    (repo_dir / "moduleA.js").write_text(dup_content, encoding="utf-8")
    (repo_dir / "moduleB.js").write_text(dup_content, encoding="utf-8")

    analyzer = SourceCodeAnalyzer(root_dir=str(repo_dir))
    res = analyzer.analyze_repository()
    rules = [f["rule_id"] for f in res["findings"]]
    assert "CROSS_FILE_CODE_DUPLICATION" in rules

def test_api_quality_summary_and_analyze():
    headers = get_auth_headers()
    # 1. Create project
    p = client.post("/api/v1/projects", json={"name": f"Quality Proj {uuid.uuid4().hex[:6]}"}, headers=headers).json()
    proj_id = p["id"]

    # 2. Quality summary endpoint
    res = client.get(f"/api/v1/code-findings/project/{proj_id}/quality-summary", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == proj_id
    assert "quality_grade" in data
    assert "severity_breakdown" in data
    assert "category_remediation_hours" in data

    # 3. On-demand analyze endpoint
    a_res = client.post(f"/api/v1/code-findings/project/{proj_id}/analyze", headers=headers)
    assert a_res.status_code == 200
    a_data = a_res.json()
    assert a_data["project_id"] == proj_id
    assert "files_analyzed" in a_data
    assert "quality_grade" in a_data
