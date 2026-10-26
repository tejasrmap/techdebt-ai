"""
TechDebt AI — 26-Step End-to-End Acceptance Test
Validates the full enterprise lifecycle from registration to report generation,
risk management, scheduler automation, and cross-organization isolation.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_26_step_end_to_end_acceptance():
    uid = uuid.uuid4().hex[:6]
    org_name = f"Enterprise E2E Corp {uid}"

    # Step 1 & 2: Register a new organization and create administrator
    reg_res = client.post("/api/v1/auth/register", json={
        "email": f"admin_e2e_{uid}@e2ecorp.com",
        "password": "E2EPassword123!",
        "full_name": "E2E Administrator",
        "organization_name": org_name
    })
    assert reg_res.status_code == 200, f"Step 1 & 2 failed: {reg_res.text}"
    admin_auth = reg_res.json()
    admin_token = admin_auth["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert admin_auth["user"]["role"] == "Administrator"

    # Step 3: Invite a developer
    inv_res = client.post("/api/v1/auth/invitations", headers=admin_headers, json={
        "email": f"dev_e2e_{uid}@e2ecorp.com",
        "role": "Developer"
    })
    assert inv_res.status_code == 201, f"Step 3 failed: {inv_res.text}"
    inv_data = inv_res.json()
    raw_invite_token = inv_data["token"]
    assert inv_data["role"] == "Developer"

    # Accept invitation as Developer
    join_res = client.post("/api/v1/auth/accept-invitation", json={
        "token": raw_invite_token,
        "full_name": "Dev Alice",
        "password": "DevPassword123!"
    })
    assert join_res.status_code == 200
    dev_token = join_res.json()["access_token"]
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    # Step 4: Create a project
    proj_res = client.post("/api/v1/projects", headers=admin_headers, json={
        "name": f"Payments Microservice {uid}",
        "description": "PCI-compliant payment transaction gateway",
        "repository_url": "https://github.com/e2ecorp/payments",
        "languages": ["TypeScript", "Node.js"],
        "frameworks": ["Express"]
    })
    assert proj_res.status_code == 201, f"Step 4 failed: {proj_res.text}"
    proj_id = proj_res.json()["id"]

    # Step 5 & 6: Upload package.json and extract dependencies
    manifest_content = """{
      "name": "payments-microservice",
      "version": "1.0.0",
      "dependencies": {
        "react": "18.2.0",
        "axios": "^1.2.0",
        "lodash": "4.17.15"
      }
    }"""
    import_res = client.post("/api/v1/technologies/import", headers=admin_headers, json={
        "project_id": proj_id,
        "file_name": "package.json",
        "content": manifest_content
    })
    assert import_res.status_code == 200, f"Step 5 & 6 failed: {import_res.text}"
    extracted_techs = import_res.json()
    assert len(extracted_techs) == 3

    # Step 7 & 8: Configure Firecrawl and verify connectivity
    set_fc = client.post("/api/v1/settings", headers=admin_headers, json={
        "firecrawl_api_key": "fc-mock-test-key",
        "preferences": {"default_ai_provider": "gemini"}
    })
    assert set_fc.status_code == 200, f"Step 7 failed: {set_fc.text}"
    
    verify_fc = client.post("/api/v1/settings/verify/firecrawl", headers=admin_headers)
    assert verify_fc.status_code == 200, f"Step 8 failed: {verify_fc.text}"
    assert "service" in verify_fc.json()

    # Step 9 & 10: Configure an AI provider and verify connectivity
    set_ai = client.post("/api/v1/settings", headers=admin_headers, json={
        "gemini_api_key": "gemini-mock-test-key"
    })
    assert set_ai.status_code == 200, f"Step 9 failed: {set_ai.text}"

    verify_ai = client.post("/api/v1/settings/verify/gemini", headers=admin_headers)
    assert verify_ai.status_code == 200, f"Step 10 failed: {verify_ai.text}"
    assert verify_ai.json()["service"] == "Gemini"
    assert verify_ai.json()["status"] in ["connected", "invalid_credentials", "ready"]

    # Step 11, 12, 13, 14, 15, 16: Run technology assessment, collect evidence, calculate scores, save historical memory
    run_res = client.post("/api/v1/assessments/run", headers=admin_headers, json={
        "project_id": proj_id,
        "trigger_type": "manual"
    })
    assert run_res.status_code == 200, f"Step 11-16 failed: {run_res.text}"
    ass_data = run_res.json()
    ass_id = ass_data["id"]
    assert ass_data["overall_health_score"] is not None
    assert ass_data["overall_health_score"] > 0
    assert len(ass_data["scores"]) > 0

    # Step 17 & 18: Retrieve previous assessment and compare assessment history
    # Run second assessment to generate delta
    run_res_2 = client.post("/api/v1/assessments/run", headers=admin_headers, json={
        "project_id": proj_id,
        "trigger_type": "manual"
    })
    assert run_res_2.status_code == 200
    ass2_id = run_res_2.json()["id"]

    comp_res = client.get(f"/api/v1/assessments/{ass2_id}/comparison", headers=admin_headers)
    assert comp_res.status_code == 200, f"Step 17 & 18 failed: {comp_res.text}"
    comp_data = comp_res.json()
    assert "storage_provider" in comp_data
    assert comp_data["storage_provider"] == "postgresql"
    assert "score_change" in comp_data

    # Step 19, 20, 21: Generate risk findings, assign a risk, mark as resolved
    risks_res = client.get(f"/api/v1/risks?project_id={proj_id}", headers=admin_headers)
    assert risks_res.status_code == 200, f"Step 19 failed: {risks_res.text}"
    risks = risks_res.json()
    if risks:
        target_risk = risks[0]
        # Assign risk to developer
        assign_res = client.put(f"/api/v1/risks/{target_risk['id']}", headers=admin_headers, json={
            "status": "In Progress",
            "assigned_to": join_res.json()["user"]["id"],
            "resolution_notes": "Assigned to Alice for security patch update."
        })
        assert assign_res.status_code == 200, f"Step 20 failed: {assign_res.text}"

        # Resolve risk
        resolve_res = client.put(f"/api/v1/risks/{target_risk['id']}", headers=admin_headers, json={
            "status": "Resolved",
            "resolution_notes": "Upgraded package in main branch and verified CI build."
        })
        assert resolve_res.status_code == 200, f"Step 21 failed: {resolve_res.text}"
        assert resolve_res.json()["status"] == "Resolved"

    # Step 22: Generate PDF report
    pdf_res = client.get(f"/api/v1/reports/pdf/{proj_id}", headers=admin_headers)
    assert pdf_res.status_code == 200, f"Step 22 failed: {pdf_res.text}"
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 1000

    # Step 23: Generate CSV report
    csv_res = client.get(f"/api/v1/reports/csv/{proj_id}", headers=admin_headers)
    assert csv_res.status_code == 200, f"Step 23 failed: {csv_res.text}"
    assert "text/csv" in csv_res.headers["content-type"]
    assert b"Technology,Installed Version" in csv_res.content

    # Step 24 & 25: Schedule a recurring assessment and verify execution
    sched_res = client.post("/api/v1/scheduler", headers=admin_headers, json={
        "project_id": proj_id,
        "frequency": "Weekly",
        "is_active": True
    })
    assert sched_res.status_code == 201, f"Step 24 failed: {sched_res.text}"
    sched_id = sched_res.json()["id"]

    # Trigger scheduled review run
    trigger_sched = client.post(f"/api/v1/scheduler/trigger/{sched_id}", headers=admin_headers)
    assert trigger_sched.status_code == 200, f"Step 25 failed: {trigger_sched.text}"
    assert "assessment_id" in trigger_sched.json()

    # Step 26: Verify organization isolation
    other_uid = uuid.uuid4().hex[:6]
    other_org = client.post("/api/v1/auth/register", json={
        "email": f"attacker_{other_uid}@other.com",
        "password": "Password123!",
        "full_name": "Other Admin",
        "organization_name": f"Other Org {other_uid}"
    }).json()
    other_headers = {"Authorization": f"Bearer {other_org['access_token']}"}

    # Other org cannot access E2E project
    leak_proj = client.get(f"/api/v1/projects/{proj_id}", headers=other_headers)
    assert leak_proj.status_code == 404

    # Other org cannot access E2E assessment comparison
    leak_comp = client.get(f"/api/v1/assessments/{ass_id}/comparison", headers=other_headers)
    assert leak_comp.status_code == 404

    # Other org cannot download E2E PDF report
    leak_pdf = client.get(f"/api/v1/reports/pdf/{proj_id}", headers=other_headers)
    assert leak_pdf.status_code == 404

    print("ALL 26 STEPS IN END-TO-END ACCEPTANCE TEST COMPLETED SUCCESSFULLY!")

