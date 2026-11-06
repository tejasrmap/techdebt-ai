import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.dependency_health_service import DependencyHealthService, VersionInfo

client = TestClient(app)

def test_semver_parsing_and_diffing():
    v1 = DependencyHealthService.parse_semver("1.2.3")
    assert v1.major == 1 and v1.minor == 2 and v1.patch == 3

    v2 = DependencyHealthService.parse_semver("^2.0.0-beta.1")
    assert v2.major == 2 and v2.minor == 0 and v2.patch == 0

    diff_patch = DependencyHealthService.compare_versions(
        DependencyHealthService.parse_semver("1.2.3"),
        DependencyHealthService.parse_semver("1.2.4")
    )
    assert diff_patch["diff_type"] == "PATCH"
    assert diff_patch["is_outdated"] is True

    diff_minor = DependencyHealthService.compare_versions(
        DependencyHealthService.parse_semver("1.2.3"),
        DependencyHealthService.parse_semver("1.5.0")
    )
    assert diff_minor["diff_type"] == "MINOR"
    assert diff_minor["is_outdated"] is True

    diff_major = DependencyHealthService.compare_versions(
        DependencyHealthService.parse_semver("1.2.3"),
        DependencyHealthService.parse_semver("2.0.0")
    )
    assert diff_major["diff_type"] == "MAJOR"
    assert diff_major["is_outdated"] is True
    assert diff_major["major_diff"] == 1

def test_deprecated_package_detection():
    # 'request' is deprecated
    res = DependencyHealthService.evaluate_dependency("request", "2.88.2")
    assert res["is_deprecated"] is True
    assert res["breaking_risk"] == "CRITICAL"
    assert "MIGRATE_REPLACE" in res["upgrade_strategy"]

    # 'moment' is in maintenance mode
    res_moment = DependencyHealthService.evaluate_dependency("moment", "2.29.4")
    assert res_moment["is_deprecated"] is True
    assert "date-fns" in res_moment["deprecation_info"]["replacement"]

def test_breaking_migration_notes():
    # Pydantic v1 to v2 migration
    res = DependencyHealthService.evaluate_dependency("pydantic", "1.10.8", "2.9.2")
    assert res["diff_type"] == "MAJOR"
    assert res["breaking_risk"] == "HIGH"
    assert any("model_dump" in note for note in res["breaking_notes"])

    # SQLAlchemy 1.4 to 2.0
    res_sql = DependencyHealthService.evaluate_dependency("sqlalchemy", "1.4.40", "2.0.35")
    assert res_sql["diff_type"] == "MAJOR"
    assert any("Implicit commits" in note for note in res_sql["breaking_notes"])

def test_project_aggregate_health_scoring():
    deps = [
        {"name": "fastapi", "version": "0.115.0", "target_version": "0.115.0"}, # up to date
        {"name": "request", "version": "2.88.2"}, # deprecated critical
        {"name": "pydantic", "version": "1.10.0", "target_version": "2.9.2"}, # major outdated
        {"name": "axios", "version": "1.7.0", "target_version": "1.7.7"} # patch outdated
    ]
    report = DependencyHealthService.evaluate_project_dependencies(deps)
    assert report["total_dependencies"] == 4
    assert report["up_to_date_count"] == 1
    assert report["deprecated_count"] == 1
    assert report["major_outdated_count"] == 1
    assert report["patch_outdated_count"] == 1
    assert report["health_score"] < 80.0
    assert len(report["recommendations"]) >= 2
    # Critical should be first recommendation
    assert report["recommendations"][0]["breaking_risk"] == "CRITICAL"

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"health_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Health Tester",
        "organization_name": f"Health Org {uid}"
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

def test_dependency_health_api_evaluation():
    headers = get_test_headers()

    # Evaluate via direct payload
    eval_res = client.post("/api/v1/technologies/evaluate-health", json={
        "dependencies": [
            {"name": "react", "version": "17.0.2", "target_version": "18.3.1"},
            {"name": "lodash", "version": "4.17.21", "target_version": "4.17.21"}
        ]
    }, headers=headers)
    assert eval_res.status_code == 200
    data = eval_res.json()
    assert data["total_dependencies"] == 2
    assert data["up_to_date_count"] == 1
    assert data["major_outdated_count"] == 1

    # Evaluate via manifest content
    package_json = '{"dependencies": {"moment": "2.29.4", "axios": "1.7.0"}}'
    manifest_res = client.post("/api/v1/technologies/evaluate-health", json={
        "file_name": "package.json",
        "manifest_content": package_json
    }, headers=headers)
    assert manifest_res.status_code == 200
    m_data = manifest_res.json()
    assert m_data["deprecated_count"] == 1

    # Create project and test project endpoint
    p_name = f"Health Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/health"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    # Import dependencies into project
    import_res = client.post("/api/v1/technologies/import", json={
        "project_id": proj_id,
        "file_name": "package.json",
        "content": '{"dependencies": {"fastapi": "0.115.0"}}'
    }, headers=headers)
    assert import_res.status_code == 200

    proj_health = client.get(f"/api/v1/technologies/project/{proj_id}/health", headers=headers)
    assert proj_health.status_code == 200
    p_health_data = proj_health.json()
    assert p_health_data["project_id"] == proj_id
    assert p_health_data["total_dependencies"] == 1
    assert p_health_data["grade"] in ("A", "A+")
