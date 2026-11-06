import uuid
import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.ai_engineering_assistant import AIEngineeringAssistant
from app.database import SessionLocal
from app.models.all_models import Project, Assessment

client = TestClient(app)

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"chat_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Chat Tester",
        "organization_name": f"Chat Org {uid}"
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

def test_conversational_assistant_grounding():
    async def _run():
        assistant = AIEngineeringAssistant()
        telemetry = {
            "health_score": 74.5,
            "risk_classification": "Good",
            "findings": [
                {"title": "Outdated express package", "severity": "Medium"},
                {"title": "Unsanitized user input in auth controller", "severity": "High"}
            ],
            "hotspots": [
                {"file_path": "backend/app/api/auth.py", "complexity": 18, "loc": 350}
            ],
            "dependencies": [
                {"name": "express", "version": "4.17.1"},
                {"name": "jsonwebtoken", "version": "8.5.1"}
            ]
        }

        # 1. Ask about refactoring
        res_refactor = await assistant.chat(
            project_name="Acme Backend",
            user_message="How should we refactor the primary hotspot?",
            telemetry=telemetry
        )
        assert res_refactor["project_name"] == "Acme Backend"
        assert len(res_refactor["grounding_evidence"]) >= 3
        assert len(res_refactor["suggested_followups"]) == 3
        assert "refactor" in res_refactor["response"].lower() or "auth.py" in res_refactor["response"].lower()

        # 2. Multi-turn conversation context
        history = [
            {"role": "user", "content": "How should we refactor the primary hotspot?"},
            {"role": "assistant", "content": res_refactor["response"]}
        ]
        res_sec = await assistant.chat(
            project_name="Acme Backend",
            user_message="What security risks should we patch next?",
            conversation_history=history,
            telemetry=telemetry
        )
        assert "security" in res_sec["response"].lower() or "finding" in res_sec["response"].lower()

    asyncio.run(_run())

def test_conversational_assistant_api_endpoints():
    headers = get_test_headers()

    # 1. Create a project
    p_name = f"Assistant Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/asst"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    # Insert mock completed assessment
    db = SessionLocal()
    try:
        asmt = Assessment(
            project_id=proj_id,
            status="completed",
            overall_health_score=82.0,
            risk_classification="Good",
            estimated_remediation_hours=14.0,
            raw_output={
                "hotspots": [{"file_path": "src/core/router.ts", "complexity": 15, "loc": 220}],
                "code_findings": [{"title": "Deep nesting in route parser", "severity": "Medium"}]
            }
        )
        db.add(asmt)
        db.commit()
    finally:
        db.close()

    # 2. Chat endpoint
    chat_resp = client.post("/api/v1/intelligence/assistant/chat", json={
        "project_id": proj_id,
        "message": "What is our current technical debt score and how do we improve it?"
    }, headers=headers)
    assert chat_resp.status_code == 200
    c_data = chat_resp.json()
    assert c_data["project_id"] == proj_id
    assert len(c_data["response"]) > 0
    assert len(c_data["suggested_followups"]) > 0

    # 3. Recommendations & Roadmap endpoint
    rec_resp = client.post("/api/v1/intelligence/assistant/recommendations", json={
        "project_id": proj_id
    }, headers=headers)
    assert rec_resp.status_code == 200
    r_data = rec_resp.json()
    assert r_data["project_id"] == proj_id
    assert "executive_summary" in r_data
    assert "modernization_roadmap" in r_data
    assert "immediate_30_days" in r_data["modernization_roadmap"]
    assert "refactoring_recipes" in r_data
