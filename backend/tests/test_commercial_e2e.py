import io
import uuid
import zipfile
import asyncio
import pytest
from app.database import SessionLocal
from app.models.all_models import (
    Organization, User, Project, RepositoryConnection,
    Assessment, CodeFinding, Notification, UsageRecord
)
from app.services.repository_ingestion_service import RepositoryIngestionService
from app.services.scheduler_service import execute_project_review
from app.services.billing_service import BillingService
from app.services.auth_service import get_password_hash

def test_full_commercial_saas_lifecycle():
    """
    End-to-end commercial SaaS workflow:
    1. Organization & User Registration
    2. Repository ZIP ingestion with secure unpack & profiling
    3. Assessment execution with v2.0.0 10-dimension debt engine
    4. Code finding generation with remediation recipes
    5. Usage metering & In-App Notification verification
    """
    db = SessionLocal()
    try:
        # 1. Organization & User
        org = Organization(name=f"Enterprise Client {uuid.uuid4().hex[:6]}", slug=f"ent-client-{uuid.uuid4().hex[:6]}")
        db.add(org)
        db.commit()

        user = User(
            org_id=org.id,
            email=f"lead-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=get_password_hash("CommercialSecret123!"),
            full_name="Lead Architect",
            role="Administrator"
        )
        db.add(user)
        db.commit()

        # 2. Project
        project = Project(
            org_id=org.id,
            name=f"Core Microservice {uuid.uuid4().hex[:4]}",
            description="Production payments microservice"
        )
        db.add(project)
        db.commit()

        # 3. Create and Ingest Repository ZIP
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("src/service.py", """
import os

def process_payment(amount, token):
    if amount <= 0:
        return False
    # Dangerous eval
    eval("print('processing')")
    return True
""")
            zf.writestr("requirements.txt", "fastapi==0.100.0\nuvicorn==0.22.0\n")
            zf.writestr("tests/test_service.py", "def test_pay(): assert True\n")
        zip_bytes = bio.getvalue()

        ingest_res = RepositoryIngestionService.process_zip_upload(zip_bytes, project.id)
        repo_conn = RepositoryConnection(
            project_id=project.id,
            provider="local_upload",
            repo_url="payments.zip",
            branch="main",
            status="synced",
            file_count=ingest_res["file_count"],
            size_bytes=ingest_res["total_size_bytes"],
            local_path=ingest_res["extracted_path"]
        )
        db.add(repo_conn)
        db.commit()

        # 4. Execute Assessment
        assessment = asyncio.run(execute_project_review(
            project_id=project.id,
            trigger_type="manual",
            db_session=db
        ))

        assert assessment.status == "completed"
        assert assessment.scoring_version in ("v2.0.0", "v3.0.0", "v3.1.0")
        assert assessment.overall_health_score is not None
        assert 0.0 <= assessment.overall_health_score <= 100.0
        assert assessment.technical_debt_ratio is not None
        assert assessment.estimated_remediation_hours is not None
        assert assessment.lines_of_code > 0
        assert assessment.files_analyzed > 0

        # Verify all 10 dimensional scores
        assert assessment.code_maintainability_score is not None
        assert assessment.architecture_score is not None
        assert assessment.dependency_score is not None
        assert assessment.security_score is not None
        assert assessment.test_quality_score is not None
        assert assessment.documentation_score is not None
        assert assessment.reliability_score is not None
        assert assessment.performance_score is not None
        assert assessment.complexity_score is not None
        assert assessment.upgrade_risk_score is not None

        # 5. Verify Code Findings
        findings = db.query(CodeFinding).filter(CodeFinding.assessment_id == assessment.id).all()
        assert len(findings) > 0
        assert any("EVAL" in f.rule_id for f in findings)
        rule_finding = next(f for f in findings if "EVAL" in f.rule_id)
        assert rule_finding.estimated_remediation_hours > 0
        assert rule_finding.recommended_remediation != ""

        # 6. Verify Metered Usage
        usage = BillingService.get_monthly_usage(db, org.id)
        assert usage.get("monthly_assessments", 0) >= 1

        # 7. Verify Notification
        notifs = db.query(Notification).filter(Notification.org_id == org.id).all()
        assert len(notifs) >= 1
        assert "Assessment Complete" in notifs[0].title
    finally:
        db.close()

