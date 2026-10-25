import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_login_and_me():
    # Login with seeded admin
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "admin@techdebt.ai",
        "password": "AdminPass123!"
    })
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    token = token_data["access_token"]

    # Call /auth/me
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "admin@techdebt.ai"

def test_dashboard_overview():
    # Login
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "admin@techdebt.ai",
        "password": "AdminPass123!"
    })
    token = login_resp.json()["access_token"]

    resp = client.get("/api/v1/dashboard/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_projects" in data
    assert data["total_projects"] >= 2
    assert "overall_health_score" in data
    assert "health_distribution" in data

def test_projects_crud():
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "admin@techdebt.ai",
        "password": "AdminPass123!"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # List
    list_resp = client.get("/api/v1/projects", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 2

    # Create
    create_resp = client.post("/api/v1/projects", headers=headers, json={
        "name": "Integration Test Service",
        "description": "Created during automated testing",
        "languages": ["Python", "Rust"],
        "frameworks": ["FastAPI"]
    })
    assert create_resp.status_code == 201
    new_proj = create_resp.json()
    proj_id = new_proj["id"]

    # Get
    get_resp = client.get(f"/api/v1/projects/{proj_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Integration Test Service"

    # Delete
    del_resp = client.delete(f"/api/v1/projects/{proj_id}", headers=headers)
    assert del_resp.status_code == 204

def test_technology_comparison():
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "admin@techdebt.ai",
        "password": "AdminPass123!"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/v1/intelligence/compare", headers=headers, json={
        "technology_names": ["react", "axios"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert len(data["categories"]) == 8
    assert "balanced_summary" in data

def test_risk_management():
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "admin@techdebt.ai",
        "password": "AdminPass123!"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    risks_resp = client.get("/api/v1/risks", headers=headers)
    assert risks_resp.status_code == 200
    risks = risks_resp.json()
    assert len(risks) > 0
    first_risk = risks[0]

    # Update risk status
    update_resp = client.put(f"/api/v1/risks/{first_risk['id']}", headers=headers, json={
        "status": "In Progress",
        "resolution_notes": "Security patch assigned to sprint."
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "In Progress"

